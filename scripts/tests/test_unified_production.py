"""The new production default uses the complete city collection and executor."""
import copy, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from planning_pipeline_core import prepare_template
from hub_joint_prototype import compile_spec
from road_first_collection import stage_spec

class UnifiedProductionTests(unittest.TestCase):
    def test_default_production_has_city_roles_and_both_road_phases(self):
        root=Path(__file__).resolve().parents[2]
        raw=json.loads((root/'config/planning_templates/production.json').read_text('utf8'))
        original=copy.deepcopy(raw)
        prepared=prepare_template(raw,'production')
        self.assertEqual(raw,original)
        self.assertEqual({f['role'] for f in prepared['facilities']},
                         {'heliport','warehouse','truck','bus','road_depot','road_maintenance'})
        self.assertEqual(prepare_template(prepared,'production'),prepared)
        spec=compile_spec(prepared)
        self.assertTrue(stage_spec(spec,'roads')['roads'])
        nodes={str(n['name']):10000+k for k,n in enumerate(spec['nodes'])}
        facilities=stage_spec(spec,'facilities',nodes,[12000])
        self.assertEqual(len(facilities['facilities']),6)
        self.assertTrue(facilities['roads'])

if __name__=='__main__':unittest.main()
