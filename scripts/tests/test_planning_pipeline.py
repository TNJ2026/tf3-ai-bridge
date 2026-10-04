import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planning_pipeline_core import prepare_template,validate_inputs,layout_key,strip_native_evidence,select_preview_rows
from planning_clock import update

ROOT=Path(__file__).resolve().parents[2]

class PipelineTests(unittest.TestCase):
    def test_captured_city_adaptation_is_idempotent_and_retains_all_roles(self):
        # Preserve the captured shared-port topology without requiring local exports.
        raw={'facilities':[{'role':r,'localPosition':{'x':0,'y':0},'relativeRotation':0}
                           for r in ['heliport','warehouse','truck','bus','road_depot']],
             'roads':[{'node0':10,'node1':11,'position0':{'x':0,'y':20},'position1':{'x':30,'y':20}}],
             'rolePortNodes':{'road_depot':[10],'truck':[10]}}
        before=copy.deepcopy(raw)
        adapted=prepare_template(raw,'city')
        self.assertEqual(raw,before)
        self.assertEqual(len(adapted['facilities']),5)
        self.assertEqual(len(adapted['planningLinks']),1)
        self.assertEqual(prepare_template(adapted,'city'),adapted)
        self.assertFalse(adapted['planningAdaptation']['nativeVerifiedHere'])

    def test_missing_second_pad_rejected_before_any_game_call(self):
        t={'facilities':[{'role':r}for r in ['helipad','truck','warehouse']],'roads':[{}]}
        with self.assertRaisesRegex(ValueError,'Incomplete'):prepare_template(t,'production')

    def inputs(self):
        s={'state':{'player':1},'map':{'towns':[{'id':1}],'industries':[{'id':2,'fileName':'farm','position':{'x':0,'y':0}}]},'grid':{},'obstacles':[]}
        d={'state':{'player':1},'industries':[{'id':2,'construction':3,'resource':'farm','position':{'x':0,'y':0}}],'buildings':[{'id':4,'town':1,'demands':{'1':1}}],'frozenNodes':[5]}
        c={'industries':[{'id':2,'outputs':{'1':10}}]}
        return s,d,c

    def test_new_resource_requires_fresh_inventory(self):
        s,d,c=self.inputs();validate_inputs(s,d,c);c['industries'].append({'id':9})
        with self.assertRaisesRegex(ValueError,'inventory'):validate_inputs(s,d,c)

    def test_geometry_cache_excludes_rates_but_tracks_ids_and_terrain(self):
        s,d,c=self.inputs();key=layout_key(s,d,{})
        d['buildings'][0]['demands']['1']=10
        self.assertEqual(key,layout_key(s,d,{}))
        d['frozenNodes'].append(6)
        self.assertNotEqual(key,layout_key(s,d,{}))
        s['grid']['heights']=[1]
        self.assertNotEqual(key,layout_key(s,d,{}))

    def test_reused_layout_never_keeps_native_tokens(self):
        out=strip_native_evidence({'native_verified':True,'native_preview':{'preview_token':'secret'},'children':[{'status':'native_single_placement_preview_passed','preview_token':'stale'}]})
        self.assertFalse(out['native_verified']);self.assertNotIn('native_preview',out)
        self.assertNotIn('preview_token',out['children'][0])
        self.assertEqual(out['children'][0]['status'],'candidate_requires_fresh_native_preview')

    def test_affected_owner_includes_depot_link_without_other_city(self):
        p={'facilities':[{'id':'a','owner':'T1'},{'id':'b','owner':'T2'}],
           'hubs':[{'owner':'T1','facilities':{'truck':'a'},'roads':['r1']},{'owner':'T2','facilities':{'truck':'b'},'roads':['r2']}],
           'roads':[{'id':'r1','to_facility':'a'},{'id':'r2','to_facility':'b'},{'id':'depot','from_facility':'a'}]}
        self.assertEqual([r['id']for r in select_preview_rows(p,'roads',['T1'])],['r1','depot'])
        with self.assertRaisesRegex(ValueError,'Unknown owner'):select_preview_rows(p,'groups',['T3'])
        with self.assertRaisesRegex(ValueError,'Unknown preview'):select_preview_rows(p,'roads',ids=['typo'])

    def test_clock_excludes_only_explicit_wait_and_rejects_restarts(self):
        d=update(None,'start',100);d=update(d,'wait-start',120)
        with self.assertRaises(ValueError):update(d,'wait-start',121)
        d=update(d,'wait-end',140);d=update(d,'finish',200)
        self.assertEqual((d['wallSeconds'],d['exclusiveWaitSeconds'],d['planningSeconds']),(100,20,80))
        with self.assertRaises(ValueError):update(d,'start',201)
        with self.assertRaises(ValueError):update(d,'finish',201)

if __name__=='__main__':unittest.main()
