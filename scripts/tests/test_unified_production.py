"""Production uses its observed four-facility layout and the joint executor."""
import copy, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from planning_pipeline_core import prepare_template
from hub_joint_prototype import compile_spec

class UnifiedProductionTests(unittest.TestCase):
    def test_default_production_has_city_roles_and_joint_roads(self):
        root=Path(__file__).resolve().parents[2]
        raw=json.loads((root/'config/planning_templates/production.json').read_text('utf8'))
        original=copy.deepcopy(raw)
        prepared=prepare_template(raw,'production')
        self.assertEqual(raw,original)
        self.assertEqual({f['role'] for f in prepared['facilities']},
                         {'heliport','warehouse','truck','road_maintenance'})
        self.assertEqual(prepare_template(prepared,'production'),prepared)
        spec=compile_spec(prepared)
        self.assertEqual(prepared['placementMode'],'joint')
        self.assertEqual(len(spec['facilities']),4)
        self.assertEqual(len(spec['roads']),5)
        self.assertEqual(set(spec['portBindings']),{'truck'})
        city=json.loads((root/'config/planning_templates/city.json').read_text('utf8'))
        self.assertEqual(len(city['facilities']),6)
        self.assertNotEqual(raw['sourceEvidence']['origin'],city['sourceEvidence']['origin'])
        self.assertEqual(raw['sourceEvidence']['facilities'],dict(heliport=77862,warehouse=77866,truck=79185,road_maintenance=79174))
        self.assertTrue(all(r['roadTemplate']=='country/country_new_medium' for r in raw['roads']))
        from build_joint_collection import code_for
        from lupa import LuaRuntime
        for build in (False,True):
            code=code_for(spec,dict(x=100,y=200,rotation=45),build)
            LuaRuntime().execute('assert(load(...))',code)
            self.assertEqual(code.count('api.cmd.sendCommand('),int(build))
        self.assertIsNone(raw['sitingPolicy']['minimumDistanceM'])
        self.assertIsNone(raw['sitingPolicy']['maximumDistanceM'])
        self.assertFalse(raw['sitingPolicy']['citySetbackApplies'])


if __name__=='__main__':unittest.main()
