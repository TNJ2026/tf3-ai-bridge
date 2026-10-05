import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullmap_hub_template import compile_template

def fixture():
    fs=[]
    for role,id,x in [('heliport',1,100),('truck',2,130),('warehouse',3,150)]:
        fs.append(dict(role=role,entity=id,resource=role,position=dict(x=x,y=100,z=5),transform=[dict(x=0,y=1)],
                       params={'modules':{'7':{'name':'module','variant':0}}},slots=[],compatible_modules=[],
                       frozen_edges=[10]if role=='truck'else[],frozen_nodes=[20]if role=='truck'else[]))
    def edge(id,a,b,owner):
        return dict(id=id,node0=a,node1=b,construction=owner,node0Degree=2,node1Degree=2,
                    position0=dict(x=120,y=90,z=5),position1=dict(x=120,y=110,z=6),
                    tangent0=dict(x=0,y=20,z=1),tangent1=dict(x=0,y=20,z=1),roadTemplate='road',roadStyle='style')
    return dict(facilities=fs,edges=[edge(10,20,21,2),edge(11,21,22,-1),edge(12,22,23,99),edge(13,30,31,-1)],
                stockLists=[dict(stockList=50,construction=3)],catchment=[dict(construction=i,catchables=[50])for i in (1,2)],state={})

class TemplateTests(unittest.TestCase):
    def test_city_depot_preserved_with_shared_port_and_explicit_road_boundary(self):
        c=fixture();d=copy.deepcopy(c['facilities'][1]);d.update(role='road_depot',entity=4,frozen_edges=[14],frozen_nodes=[40]);c['facilities'].append(d)
        e=copy.deepcopy(c['edges'][0]);e.update(id=14,node0=40,node1=21,construction=4);c['edges'].append(e)
        c['edges'][2]['construction']=-1;c['internalRoadEdgeIds']=[11]
        t=compile_template(c)
        self.assertEqual(len(t['facilities']),4)
        self.assertEqual(t['rolePortNodes']['road_depot'],t['rolePortNodes']['truck'])
        self.assertEqual(len(t['roads']),1)
        self.assertTrue(t['sourceRoadConnected']['road_depot'])
        self.assertTrue(t['externalBoundaries'])
    def test_two_production_pads_are_preserved(self):
        from hub_joint_prototype import compile_spec
        c=fixture();c['facilities'][0]['role']='helipad'
        second=copy.deepcopy(c['facilities'][0]);second.update(role='helipad2',entity=4)
        second['position']['x']+=39;c['facilities'].append(second)
        c['catchment'].append(dict(construction=4,catchables=[50]))
        t=compile_template(c);s=compile_spec(t)
        self.assertEqual(len(s['facilities']),4)
        self.assertTrue(t['sourceCoverage']['helipad2'])
        self.assertEqual(set(s['portBindings']),{'truck'})
    def test_production_helipad_template(self):
        from hub_joint_prototype import compile_spec
        c=fixture();c['facilities'][0]['role']='helipad'
        t=compile_template(c);s=compile_spec(t)
        self.assertEqual(t['anchorRole'],'helipad')
        self.assertTrue(t['sourceCoverage']['helipad'])
        self.assertEqual(set(s['portBindings']),{'truck'})
        self.assertEqual(len(s['facilities']),3)
        self.assertFalse(s['commitEnabled'])
    def test_preserve_modules_without_copying_foreign_or_disconnected_roads(self):
        c=fixture();before=copy.deepcopy(c);t=compile_template(c)
        self.assertEqual(c,before);self.assertEqual(len(t['roads']),1)
        self.assertEqual(t['facilities'][0]['params'],c['facilities'][0]['params'])
        self.assertTrue(t['sourceCoverage']['truck']);self.assertFalse(t['nativeJointPreviewPassed'])
        self.assertTrue(any(b['externalConstructionEvidence']==[99]for b in t['externalBoundaries']))
    def test_relative_positions_and_tangents_rotate_but_vectors_do_not_translate(self):
        t=compile_template(fixture());truck=next(f for f in t['facilities']if f['role']=='truck')
        self.assertAlmostEqual(truck['localPosition']['x'],0);self.assertAlmostEqual(truck['localPosition']['y'],-30)
        self.assertAlmostEqual(t['roads'][0]['tangent0']['x'],20)
        self.assertAlmostEqual(t['roads'][0]['tangent0']['z'],1)
    def test_missing_coverage_is_not_passed(self):
        c=fixture();c['catchment']=[];self.assertFalse(compile_template(c)['sourceCoverage']['heliport'])
    def test_missing_role_fails(self):
        c=fixture();c['facilities'].pop()
        with self.assertRaises(ValueError):compile_template(c)
    def test_optional_bus_preserves_modules_and_reports_disconnected_port(self):
        c=fixture();bus=copy.deepcopy(c['facilities'][1]);bus.update(role='bus',entity=4,frozen_edges=[14],frozen_nodes=[40])
        bus['params']={'modules':{'8':{'name':'passenger_platform.module'}}}
        c['facilities'].append(bus)
        e=copy.deepcopy(c['edges'][0]);e.update(id=14,node0=40,node1=41,construction=4)
        c['edges'].append(e);t=compile_template(c)
        self.assertEqual(len(t['facilities']),4)
        self.assertFalse(t['sourceRoadConnected']['bus'])
        self.assertTrue(t['rolePortNodes']['bus'])
        self.assertEqual(len(t['roads']),1)

if __name__=='__main__':unittest.main()
