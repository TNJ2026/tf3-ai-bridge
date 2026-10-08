"""One resumable entry point for the authorized Chongqing collection extension.

Roads belong to the collection but resolve actual native ports after placement.
No multi-construction native proposal and no automatic rollback/retry.
"""
import argparse, asyncio, hashlib, json, math, time
from types import SimpleNamespace
from hub_trial_roads import TrialRoads, CurrentRoads
from hub_trial import OUT
from fullmap_batch import StopBatch, batch_lock, quote, unfinished
from batch_warehouses import write_json

ANCHOR = {'x': -2711.4489746094, 'y': 2022.1325683594}

def descriptor():
    angle = math.radians(-60.947926299660516)
    outward = (math.sin(angle), -math.cos(angle))
    position = dict(x=ANCHOR['x']+60*outward[0], y=ANCHOR['y']+60*outward[1])
    return {'schema': 1, 'roles': {'bus': {
        'id': 'TRIAL_bus', 'kind': 'bus', 'command': 'build_station',
        'status': 'planned', 'position': position,
        'rotation': math.degrees(angle)+180,
        'args': {'cargo': False, 'size': 1}}},
        'roads': [{'id': 'TRIAL_bus_access', 'from_position': ANCHOR,
                   'to_facility': 'TRIAL_bus', 'path': [ANCHOR, position],
                   'street_type': 'country/country_new_small'}],
        'dependencies': ['existing_cargo_collection', 'bus', 'bus_access', 'acceptance']}

class Collection(TrialRoads):
    def __init__(self, args):
        super().__init__(args)
        self.extension = descriptor()
        self.p['roads'] += self.extension['roads']
        digest = hashlib.sha256(json.dumps(self.extension, sort_keys=True).encode()).hexdigest()
        previous = self.ledger.get('collectionExtensionDigest')
        if previous and previous != digest:
            if any(self.ledger['items'].get(k, {}).get('attempts') for k in ['TRIAL_bus', 'TRIAL_bus_access']):
                raise StopBatch('Extension changed after submission; reconcile before proceeding')
            self.ledger.setdefault('extensionRevisions', []).append({
                'previousDigest': previous, 'newDigest': digest,
                'rejectedPreview': self.ledger['items'].get('TRIAL_bus', {}).get('preview')})
        self.ledger['collectionExtensionDigest'] = digest
    def tasks(self):
        return super().tasks() + list(self.extension['roles'].values())
    async def resolve(self, spec):
        if spec.get('to_facility') == 'TRIAL_bus':
            return await CurrentRoads.resolve(self, spec)
        return await super().resolve(spec)
    async def passenger_audit(self, entities):
        code = '''local f=B.json.decode(ENTITIES);local CT=api.type.ComponentType
local mode=api.type.enum.TransportMode.PERSON
local function nodes(id)
 local out={};local c=api.engine.getComponent(id,CT.CONSTRUCTION)
 for _,st in ipairs(c.stations)do
  local net=api.engine.getComponent(st,CT.TRANSPORT_NETWORK)
  if net then for _,e in ipairs(net.edges)do if e.transportModes[mode]then
   out[#out+1]=e.conns[1];out[#out+1]=e.conns[2]
  end end end
 end
 return out
end
local a,b=nodes(f.bus),nodes(f.heliport)
local out={busNodes=#a,airportNodes=#b,paths={},verified=#a>0 and #b>0}
for _,pair in ipairs({{a,b},{b,a}})do
 local path=api.engine.util.pathfinding.findPathNodeToNode(pair[1],pair[2],{mode})
 local row={steps={},verified=#path>0}
 for _,step in ipairs(path)do row.steps[#row.steps+1]=step[1].entity end
 out.paths[#out.paths+1]=row;out.verified=out.verified and row.verified
end
return B.json.encode(out)'''.replace('ENTITIES', quote(entities))
        return await self.eval(code)
    async def accept(self):
        rows = await self.read_facilities(self.tasks(), 'verify', with_session=True)
        entities = {}
        for task, row in zip(self.tasks(), rows):
            audit = row['result'].get('audit', {})
            if not audit.get('staticVerified'):
                raise StopBatch('Facility audit failed: '+task['id'])
            entities[task['kind']] = audit['entity']
        roads = {}
        for spec in self.p['roads']:
            item = self.ledger['items'].get(spec['id'], {})
            audit = await self.audit_road(item) if item.get('commit') else {'verified': False}
            item['audit'] = audit
            roads[spec['id']] = audit['verified']
        walking = await self.passenger_audit(entities)
        result = {'entities': entities, 'roads': roads, 'walking': walking,
                  'staticAccepted': all(roads.values()) and walking['verified'],
                  'operationalAccepted': False, 'linesCreated': 0, 'vehiclesPurchased': 0}
        self.ledger['collectionAcceptance'] = result
        write_json(OUT/'collection_result.json', result)
        self.flush()
        if not result['staticAccepted']:
            raise StopBatch('Collection walking/road audit requires diagnosis')
        return result
    async def execute(self):
        await self.session()
        write_json(OUT/'collection_extension.json', self.extension)
        if self.a.action == 'verify':
            print(json.dumps(await self.accept())); return
        if unfinished(self.ledger):
            raise StopBatch('Unreconciled submission; no further writes')
        # Verify all original roles in one read before adding the passenger role.
        rows = await self.read_facilities(super().tasks(), 'verify', with_session=True)
        if not all(r['result'].get('audit', {}).get('staticVerified') for r in rows):
            raise StopBatch('Original collection changed or missing')
        task = self.extension['roles']['bus']
        item = self.ledger['items'].setdefault(task['id'], {'attempts': 0})
        if item['attempts']:
            result = await self.facility(task, 'verify')
        else:
            result = await self.facility(task, 'preview')
            item['preview'] = result; self.flush()
            if not result.get('existing') and not result.get('previewPassed'):
                raise StopBatch('Bus placement blocked; nothing submitted')
            if self.a.action == 'preview':
                print(json.dumps(result)); return
            await self.save('collection_before')
            await self.session()
            item.update(attempts=1, status='commit_started', intentTime=time.time()); self.flush()
            result = await self.facility(task, 'build')
            item['commit'] = result; self.flush()
            result = await self.facility(task, 'verify')
        item['audit'] = result.get('audit', {})
        item['status'] = 'static_verified' if item['audit'].get('staticVerified') else 'needs_reconciliation'
        self.flush()
        if item['status'] != 'static_verified':
            raise StopBatch('Bus readback failed; do not replay')
        # Same operation owns every internal and external road; existing work is read back.
        await CurrentRoads.run(self)
        result = await self.accept()
        await self.save('collection_complete')
        result['save'] = self.ledger['events'][-1]
        write_json(OUT/'collection_result.json', result)
        print(json.dumps(result))

async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preview', 'build', 'verify'], default='preview', nargs='?')
    args = parser.parse_args()
    args.plan=OUT/'plan.json'; args.output=OUT/'execution'
    args.ids=None; args.road_ids=None; args.limit=0
    batch = Collection(args)
    try:
        with batch_lock(batch.b.dir):
            await batch.execute()
    finally:
        batch.flush()

if __name__ == '__main__':
    asyncio.run(main())
