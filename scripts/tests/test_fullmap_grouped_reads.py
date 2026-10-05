import asyncio
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from lupa import LuaRuntime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fullmap_batch import Batch, StopBatch
from fullmap_road_reads import audit_source, run_road_reads, task_for
from fullmap_hub_sets import compile_hub_sets


class CombinedFacilityTests(unittest.TestCase):
    def test_context_and_reads_share_one_call_and_reject_truncated_reply(self):
        b = object.__new__(Batch)
        b.lua = 'local readIndex=nil\nlocal task=TASK\nlocal action=ACTION\nreturn B.json.encode({existing=false})'
        b.ledger = {}; b.accept_session = lambda s: self.assertEqual(s, {'correct':True})
        b.eval = AsyncMock(return_value={'session':{'correct':True}, 'results':[{'id':'A','result':{}}]})
        rows = asyncio.run(b.read_facilities([{'id':'A'}], 'verify', with_session=True))
        self.assertEqual(rows[0]['id'], 'A'); self.assertEqual(b.eval.await_count, 1)
        self.assertIn('get_map_info', b.eval.call_args.args[0])
        b.eval.return_value['results'] = []
        with self.assertRaises(StopBatch):
            asyncio.run(b.read_facilities([{'id':'A'}], 'verify', with_session=True))
        self.assertEqual(b.ledger['performance']['facility.batch_verify']['failures'], 1)

    def test_wrong_session_cannot_accept_facility_results(self):
        b = object.__new__(Batch);b.lua = 'local task=TASK\nlocal action=ACTION';b.ledger = {}
        def reject(s):raise StopBatch('changed map')
        b.accept_session = reject
        b.eval = AsyncMock(return_value={'session':{},'results':[{'id':'A','result':{}}]})
        with self.assertRaisesRegex(StopBatch, 'changed map'):
            asyncio.run(b.read_facilities([{'id':'A'}], 'verify', with_session=True))
        self.assertEqual(b.eval.await_count, 1)


def item():
    return {'attempts':1,'commit':{'built':True,'edges':[20],'from':1,'to':{'x':100,'y':0}},
            'resolved':{'anchor':{'id':1,'position':{'x':0,'y':0,'z':0}},'airport':30}}


class RoadLuaTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().decode = lambda s: self.lua.table_from(json.loads(s), recursive=True)
        self.lua.execute('''
        B={json={decode=decode,encode=function(v)return v end},commands={get_game_state=function()return {}end,get_map_info=function()return {}end}}
        api={type={ComponentType={BASE_EDGE=1,BASE_NODE=2,TRANSPORT_NETWORK=3,CONSTRUCTION=4,TP_NET_LINK=5},enum={TransportMode={CAR=1,TRUCK=2}}},engine={}}
        comps={};comps[1]={[2]={position={x=0,y=0,z=0}},[3]={}}
        for _,eid in ipairs({10,20})do
          comps[eid]={[1]={},[3]={edges={}}}
          comps[eid][3].edges={{transportModes={true,true},conns={{entity=eid},{entity=1}}},{transportModes={true,true},conns={{entity=1},{entity=eid}}}}
        end
        comps[30]={[4]={transf={cols=function()return {x=100,y=0,z=0}end}}}
        comps[40]={[5]={from={edgeId={entity=31}},to={edgeId={entity=20}}}}
        links={{40}}
        api.engine.getComponent=function(id,k)return comps[id]and comps[id][k]end
        api.engine.system={streetSystem={getNodeSegments=function()return {10,20}end},
          streetConnectorSystem={getConstructionEntityForSubconstruction=function(id)return id==31 and 30 or -1 end},
          tpNetLinkSystem={getEdgeId2linkEntities=function()return links end}}
        api.engine.util={pathfinding={findPathNodeToNode=function(a,b,m)return {{{entity=a[1].entity}},{{entity=b[1].entity}}}end}}
        ''')
        self.task = task_for({'id':'R','to_facility':'H'},item(),{'H':{'position':{'x':100,'y':0}}})

    def test_paths_and_real_auto_link_required(self):
        r = self.lua.execute(audit_source([self.task]))['results'][1]
        self.assertTrue(r['verified']);self.assertTrue(r['facilityRoadLink'])
        self.lua.execute('links={}')
        r = self.lua.execute(audit_source([self.task]))['results'][1]
        self.assertFalse(r['verified']);self.assertFalse(r['facilityRoadLink'])

    def test_missing_network_and_moved_endpoint_fail_before_pathfinding(self):
        self.lua.execute('api.engine.util.pathfinding.findPathNodeToNode=function()error("must not call")end; comps[1][2].position.x=5')
        r = self.lua.execute(audit_source([self.task]))['results'][1]
        self.assertFalse(r['verified'])
        self.lua.execute('comps[1][2].position.x=0;comps[20][3]=nil')
        self.assertFalse(self.lua.execute(audit_source([self.task]))['results'][1]['verified'])

    def test_extension_preserves_separate_junction_scope(self):
        row=item();row['extensions']=[{'edges':[21],'from':2}]
        t=task_for({'id':'R','to_facility':'H'},row,{'H':{'position':{'x':100,'y':0}}})
        self.assertEqual(t['nodes'],[1]);self.assertEqual(t['extensions'],[{'edges':[21],'nodes':[2]}])
        self.assertEqual(t['edges'],[20,21])

    def test_cannot_accept_only_one_end_of_a_two_ended_road(self):
        row=item();row['commit']['to']=2
        with self.assertRaisesRegex(StopBatch,'destination identity'):
            task_for({'id':'R','to_facility':'H'},row,{'H':{'position':{'x':100,'y':0}}})


class RoadHarness(Batch):
    def __init__(self, path, failure=None):
        self.path=path;self.a=SimpleNamespace(read_batch_size=8,road_ids=None,limit=0)
        self.p={'roads':[{'id':str(i),'to_facility':'H'}for i in range(17)]}
        self.ledger={'items':{str(i):item()for i in range(17)}};self.calls=0;self.sessions=0;self.failure=failure
    def tasks(self):return [{'id':'H','position':{'x':100,'y':0}}]
    def accept_session(self,s):self.sessions+=1
    async def eval(self,code):
        self.calls+=1
        if self.failure=='timeout':raise TimeoutError()
        start=(self.calls-1)*8
        return {'session':{},'results':[{'id':str(i),'verified':not(self.failure=='failed'and i==0)}for i in range(start,min(start+8,17))]}
    async def session(self):raise AssertionError('unexpected separate session')


class RoadBatchTests(unittest.TestCase):
    def test_17_roads_use_three_calls(self):
        with tempfile.TemporaryDirectory()as d:
            b=RoadHarness(Path(d)/'l.json');asyncio.run(run_road_reads(b))
            self.assertEqual((b.calls,b.sessions),(3,3))
            self.assertTrue(all(v['status']=='connection_verified'for v in b.ledger['items'].values()))
    def test_failure_and_timeout_stop_without_repair_or_retry(self):
        for failure in ('failed','timeout'):
            with tempfile.TemporaryDirectory()as d:
                b=RoadHarness(Path(d)/'l.json',failure)
                with self.assertRaises((StopBatch,TimeoutError)):asyncio.run(run_road_reads(b))
                self.assertEqual(b.calls,1)


class HubSetTests(unittest.TestCase):
    def plan(self):
        return {'facilities':[{'id':'H','kind':'heliport'},{'id':'W','kind':'warehouse'},{'id':'T','kind':'truck'}],
                'hubs':[{'owner':'A','facilities':{'heliport':'H','warehouse':'W','truck':'T'}},
                        {'owner':'B','facilities':{'heliport':'H','warehouse':'W','truck':'T'}}],
                'roads':[{'id':'RH','to_facility':'H'},{'id':'RT','to_facility':'T'}]}
    def test_shared_hubs_deduplicated_and_bounded_without_construction_permission(self):
        p=self.plan();before=copy.deepcopy(p)
        r=compile_hub_sets(p,[{'id':x,'candidates':[{}]*4}for x in ('RH','RT')],{})
        self.assertEqual(len(r),1);self.assertEqual(r[0]['owners'],['A','B'])
        self.assertFalse(r[0]['constructionReady']);self.assertEqual(len(r[0]['previewQueue'][0]['candidateIndexes']),3)
        self.assertEqual(p,before)
    def test_missing_road_or_conflict_prevents_preview_queue(self):
        p=self.plan();p['roads']=p['roads'][:1]
        r=compile_hub_sets(p,[{'id':'RH','candidates':[{}]}],{'footprint_conflicts':[['H','X']]})[0]
        self.assertEqual(r['status'],'needs_design');self.assertFalse(r['previewQueue'])
        self.assertIn('missing_access_road',[v['kind']for v in r['issues']])
        self.assertIn('footprint_conflicts',[v['kind']for v in r['issues']])


if __name__=='__main__':unittest.main()
