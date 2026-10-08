"""Bounded, read-only road acceptance. No repairs, commits or cached native handles."""
from fullmap_batch import ROOT, StopBatch, quote


def task_for(spec, item, facilities):
    commit = item.get('commit', {})
    if not commit.get('built') or not commit.get('edges'):
        raise StopBatch(spec['id'] + ': missing successful commit; inspect actual world')
    resolved = item.get('resolved', {})
    if resolved.get('anchor', {}).get('id') != commit.get('from'):
        raise StopBatch(spec['id'] + ': commit/anchor identity mismatch')
    if isinstance(commit.get('to'), int) and resolved.get('port', {}).get('id') != commit['to']:
        raise StopBatch(spec['id'] + ': commit/destination identity mismatch')
    nodes = []
    for key in ('anchor', 'port'):
        node = resolved.get(key, {})
        if isinstance(node.get('id'), int):
            nodes.append({'id': node['id'], 'position': node['position']})
    if not nodes:
        raise StopBatch(spec['id'] + ': missing recorded endpoint geometry')
    extensions = item.get('extensions', [])
    edges = list(commit['edges'])
    for ext in extensions:
        edges.extend(ext['edges'])
    task = dict(id=spec['id'], edges=list(dict.fromkeys(edges)),
                nodes=[n['id'] for n in nodes], expectedNodes=nodes,
                extensions=[dict(edges=e['edges'], nodes=[e['from']]) for e in extensions])
    if not isinstance(commit.get('to'), int):
        target = resolved.get('airport')
        facility = facilities.get(spec.get('to_facility'))
        if not isinstance(target, int) or not facility:
            raise StopBatch(spec['id'] + ': automatic access requires explicit facility identity')
        task.update(facility=target, facilityPosition=facility['position'])
    return task


def audit_source(tasks):
    source = (ROOT/'scripts/fullmap_road_audit.lua').read_text('utf-8-sig')
    source = source.replace('local task=B.json.decode(TASKJSON)', '').replace('return B.json.encode(out)', 'return out')
    return ('local session={state=B.commands.get_game_state({}),world=B.commands.get_map_info({})};\n'
            'local function inspect(task)\n'+source+'\nend\n'+r'''
local tasks=B.json.decode(TASKS);local CT=api.type.ComponentType;local links={};local seen={}
local needLinks=false;for _,t in ipairs(tasks)do if t.facility then needLinks=true end end
if needLinks then
 for _,ids in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities())do
  for _,id in ipairs(ids)do if not seen[id]then seen[id]=true
   local l=api.engine.getComponent(id,CT.TP_NET_LINK);links[#links+1]={l.from.edgeId.entity,l.to.edgeId.entity}
  end end
 end
end
local function available(t)
 for _,id in ipairs(t.edges)do
  if not api.engine.getComponent(id,CT.BASE_EDGE)or not api.engine.getComponent(id,CT.TRANSPORT_NETWORK)then return false end
 end
 for _,id in ipairs(t.nodes)do
  if not api.engine.getComponent(id,CT.BASE_NODE)or not api.engine.getComponent(id,CT.TRANSPORT_NETWORK)then return false end
 end
 return true
end
local out={}
for _,t in ipairs(tasks)do
 local valid=available(t)
 for _,n in ipairs(t.expectedNodes)do
  local c=api.engine.getComponent(n.id,CT.BASE_NODE)
  if not c or math.abs(c.position.x-n.position.x)>.2 or math.abs(c.position.y-n.position.y)>.2 or math.abs(c.position.z-n.position.z)>.2 then valid=false end
 end
 if t.facility then
  local c=api.engine.getComponent(t.facility,CT.CONSTRUCTION)
  if not c then valid=false else local p=c.transf:cols(3);local q=t.facilityPosition
   if math.abs(p.x-q.x)>.2 or math.abs(p.y-q.y)>.2 then valid=false end
  end
 end
 for _,ext in ipairs(t.extensions)do if not available(ext)then valid=false end end
 local r={id=t.id,verified=false,reason='missing_or_changed_native_components'}
 if valid then
  r=inspect(t);r.id=t.id;r.extensions={}
  for _,ext in ipairs(t.extensions)do local e=inspect(ext);r.extensions[#r.extensions+1]=e;r.verified=r.verified and e.verified end
  if t.facility then
   local es={};for _,id in ipairs(t.edges)do es[id]=true end
   local function belongs(id)return id==t.facility or api.engine.system.streetConnectorSystem.getConstructionEntityForSubconstruction(id)==t.facility end
   local linked=false
   for _,l in ipairs(links)do if(es[l[1]]and belongs(l[2]))or(es[l[2]]and belongs(l[1]))then linked=true end end
   r.facilityRoadLink=linked;r.verified=r.verified and linked
  end
 end
 out[#out+1]=r
end
return B.json.encode({session=session,results=out})
'''.replace('TASKS', quote(tasks)))


async def run_road_reads(batch):
    size = getattr(batch.a, 'read_batch_size', 8)
    if not 1 <= size <= 16:
        raise ValueError('read_batch_size must be 1..16')
    specs = batch.p['roads']
    ids = getattr(batch.a, 'road_ids', None)
    if ids:
        wanted = set(ids.split(','))
        if wanted - {s['id'] for s in specs}:
            raise ValueError('Unknown road IDs')
        specs = [s for s in specs if s['id'] in wanted]
    if batch.a.limit:
        specs = specs[:batch.a.limit]
    facilities = {f['id']: f for f in batch.tasks()}
    for offset in range(0, len(specs), size):
        chunk = specs[offset:offset+size]
        tasks = [task_for(s, batch.ledger['items'][s['id']], facilities) for s in chunk
                 if batch.ledger['items'].get(s['id'], {}).get('attempts')]
        if tasks:
            import time
            started = time.perf_counter();failed = True
            try:
                reply = await batch.eval(audit_source(tasks))
                batch.accept_session(reply['session'])
                rows = reply['results']
                if not isinstance(rows, list) or [r.get('id') for r in rows] != [t['id'] for t in tasks]:
                    raise StopBatch('Incomplete/mismatched road read batch')
                for row in rows:
                    item = batch.ledger['items'][row['id']]
                    item.update(audit=row, status='connection_verified' if row.get('verified') is True else 'needs_reconciliation')
                failed = False
            finally:
                batch.record_timing('road.batch_verify', started, failed);batch.flush()
            if any(r.get('verified') is not True for r in rows):
                raise StopBatch('Road batch requires reconciliation; no repair submitted')
        else:
            await batch.session()
        for spec in chunk:
            item = batch.ledger['items'].setdefault(spec['id'], {'kind':'connection', 'attempts':0})
            if not item.get('attempts'):
                item['verification'] = 'not_built'  # Preserve rejection evidence/status.
            print(spec['id']+': '+item.get('status', 'not_built'), flush=True)
        batch.flush()
