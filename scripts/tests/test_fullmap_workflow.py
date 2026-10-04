import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullmap_workflow import workflow, structure, geometry, job_changes, digest, facility_id
from fullmap_identity import unique_ids
from test_fullmap_prepare import snapshot, road


def inputs():
    s=snapshot();s['map']={'towns':[],'industries':[]};s['state']={'player':1}
    p={'cities':[],'industries':[],'session':{'player':1},'facilities':[],'roads':[road()]}
    m={'session':{'player':1,'towns':[],'industries':[]},'jobs':[{'id':'R','stage':'road','spec':road()}]}
    return p,s,m


def facility(name,x=0,y=0,angle=0):
    b={'min':{'x':x-40,'y':y-5},'max':{'x':x+40,'y':y+5}}
    return {'id':name,'position':{'x':x,'y':y},'rotation':angle,'footprint':b,'reserved':b}


class WorkflowTests(unittest.TestCase):
    def test_duplicate_and_unknown_reference_fail_early(self):
        p,s,m=inputs();p['facilities']=[facility('A'),facility('A')]
        with self.assertRaisesRegex(ValueError,'duplicate'):workflow(p,s,m)
        p['facilities']=[];p['roads'][0]['to_facility']='missing'
        with self.assertRaisesRegex(ValueError,'unknown road'):workflow(p,s,m)

    def test_shore_and_air_ids_stable_and_distinct(self):
        self.assertEqual(facility_id('P1','warehouse','shore'),facility_id('P1','warehouse','shore'))
        self.assertNotEqual(facility_id('P1','warehouse','shore'),facility_id('P1','warehouse','air'))
        self.assertNotEqual(facility_id('a/b','truck'),facility_id('a b','truck'))
        with self.assertRaises(ValueError):unique_ids([{'id':'x'},{'id':'x'}])

    def test_rotated_overlap_not_unrotated_false_negative(self):
        p,s,m=inputs();p['facilities']=[facility('A',angle=90),facility('B',y=30)]
        self.assertEqual(geometry(p,s)['footprint_conflicts'],[['A','B']])
        p['facilities'][0]['rotation']=0
        self.assertEqual(geometry(p,s)['footprint_conflicts'],[])

    def test_cached_polygon_is_not_trusted_after_move(self):
        p,s,m=inputs();f=facility('A');f['reserved_polygon']=[{'x':999,'y':999}]*4
        p['facilities']=[f,facility('B')]
        self.assertEqual(geometry(p,s)['reservation_conflicts'],[['A','B']])

    def test_input_unchanged_and_snapshot_cache_invalidated(self):
        p,s,m=inputs();before=copy.deepcopy((p,s,m));a=workflow(p,s,m)
        b=workflow(p,s,m,a)
        self.assertEqual(b['counters']['road_cache_hits'],1)
        self.assertEqual((p,s,m),before)
        self.assertFalse(b['changes']['affected']);self.assertTrue(b['native_preview_required'])
        s['grid']['water']=[True]*len(s['grid']['water']);c=workflow(p,s,m,b)
        self.assertEqual(c['counters']['road_cache_hits'],0)
        self.assertEqual(c['changes']['affected'],['R'])
        self.assertFalse(c['roads'][0]['candidates'])

    def test_local_road_edit_recomputes_only_that_road(self):
        p,s,m=inputs();r=copy.deepcopy(road());r['id']='R2'
        p['roads'].append(r);m['jobs'].append({'id':'R2','stage':'road','spec':copy.deepcopy(r)})
        a=workflow(p,s,m);p['roads'][0]['path'][1]['x']=140
        m['jobs'][0]['spec']=copy.deepcopy(p['roads'][0]);b=workflow(p,s,m,a)
        self.assertEqual(b['counters']['road_cache_hits'],1)
        self.assertEqual(b['changes']['affected'],['R'])

    def test_transitive_dependencies_and_removal(self):
        m={'jobs':[{'id':'A'},{'id':'B','depends_on':['A']},{'id':'C','depends_on':['B']},{'id':'D'}]}
        a=job_changes(m,None,'s');m['jobs'][0]['position']={'x':2,'y':3}
        b=job_changes(m,a,'s');self.assertEqual(b['affected'],['A','B','C'])
        m['jobs'].pop();self.assertEqual(job_changes(m,b,'s')['removed'],['D'])

    def test_wrong_map_manifest_and_stale_specs_rejected(self):
        p,s,m=inputs();m['session']['player']=2
        with self.assertRaisesRegex(ValueError,'manifest player'):workflow(p,s,m)
        m['session']['player']=1;m['jobs'][0]['spec']['path'][1]['x']=42
        with self.assertRaisesRegex(ValueError,'stale manifest'):workflow(p,s,m)

    def test_missing_legacy_fingerprint_reported_not_certified(self):
        p,s,m=inputs();del m['session']['industries'];r=workflow(p,s,m)
        self.assertEqual(r['missing_manifest_identity'],['manifest.session.industries'])
        self.assertTrue(r['requires_attention']);self.assertFalse(r['construction_authorized'])

    def test_missing_geometry_not_assumed_clear(self):
        p,s,m=inputs();p['facilities']=[{'id':'A','position':{'x':1,'y':1}}]
        m['jobs'].append({'id':'A','stage':'facility','position':{'x':1,'y':1}})
        self.assertEqual(workflow(p,s,m)['geometry']['missing_geometry'],['A'])

    def test_manifest_cannot_omit_planned_object(self):
        p,s,m=inputs();m['jobs']=[]
        with self.assertRaisesRegex(ValueError,'coverage'):workflow(p,s,m)


if __name__=='__main__':unittest.main()
