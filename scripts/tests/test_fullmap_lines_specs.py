import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fullmap_lines import Lines
from fullmap_batch import Batch

class ModernLineSpecs(unittest.TestCase):
    def test_distinct_native_terminals_and_destination_unloading(self):
        runner=Lines.__new__(Lines)
        runner.a=SimpleNamespace(line_ids=None)
        runner.ledger={'items':{}}
        runner.p={'industries':[],'city_stops':[], 'line_specs':[
            dict(id='A',mode='HELICOPTER',source='start',destination='finish',
                 load_at_source=[6],source_terminal_index=0,destination_terminal_index=1)]}
        with patch.object(Batch,'tasks',return_value=[dict(id=k,position={'x':i,'y':0}) for i,k in enumerate(['start','finish'])]):
            result=runner.specs()[0]
        self.assertEqual([e['terminal_index'] for e in result['endpoints']],[0,1])
        self.assertEqual([e['loads'] for e in result['endpoints']],[[6],[]])

    def test_city_multistop_aliases_and_no_air_terminal_constraint_on_trucks(self):
        runner=Lines.__new__(Lines);runner.a=SimpleNamespace(line_ids='B');runner.ledger={'items':{'s2':{'alias':'s1'}}}
        runner.p={'industries':[{'id':5,'position':{'x':1,'y':2}}],
            'city_stops':[{'id':'s1','position':{'x':3,'y':4}}],
            'line_specs':[dict(id='B',mode='TRUCK',source={'existing_industry':5},
                destination={'town':10,'unload_stops':['s1','s2']},load_at_source=[7],
                source_terminal_index=0,destination_terminal_index=0)]}
        with patch.object(Batch,'tasks',return_value=[]):result=runner.specs()[0]
        self.assertEqual(len(result['endpoints']),2)
        self.assertEqual(result['endpoints'][0]['id'],'industry_5')
        self.assertEqual(result['endpoints'][1]['loads'],[])
        self.assertTrue(all('terminal_index' not in e for e in result['endpoints']))

if __name__=='__main__':unittest.main()
