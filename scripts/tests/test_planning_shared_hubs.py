import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planning_shared_hubs import select_shared_hubs,hub_owner,same_hub

def p(x,y=0):return dict(x=x,y=y,z=0)
def edge(a,b,x,y):
    return dict(kind='BASE_EDGE',node0=a,node1=b,position0=p(x),position1=p(y),tangent0=p(y-x),tangent1=p(y-x))

class SharingTests(unittest.TestCase):
    def fixture(self,x=2999):
        s=dict(map=dict(towns=[dict(id=1,position=p(0))],industries=[dict(id=2,position=p(x),fileName='farm')]),obstacles=[edge(10,11,600,x)])
        h=[dict(owner='T1',entity=1,kind='city',node=10,position=p(600))]
        return s,h
    def test_strict_threshold(self):
        s,h=self.fixture();self.assertEqual(select_shared_hubs(s,h)['2']['hub_owner'],'T1')
        s,h=self.fixture(3000);self.assertEqual(select_shared_hubs(s,h),{})
    def test_disconnected(self):
        s,h=self.fixture();s['obstacles']=[edge(10,12,600,700),edge(11,13,2999,3100)]
        self.assertEqual(select_shared_hubs(s,h),{})
    def test_offshore_and_retained(self):
        s,h=self.fixture();s['map']['industries'][0]['fileName']='oil_platform'
        self.assertEqual(select_shared_hubs(s,h),{})
        s,h=self.fixture();h.append(dict(entity=2,owner='I2',kind='production'))
        self.assertEqual(select_shared_hubs(s,h),{})
    def test_detour(self):
        s,h=self.fixture();s['obstacles']=[edge(10,12,600,-10000),edge(12,11,-10000,2999)]
        self.assertEqual(select_shared_hubs(s,h),{})
    def test_alias_and_self_loop_detection(self):
        aliases={'2':{'hub_owner':'T1'}}
        self.assertEqual(hub_owner(2,True,aliases),hub_owner(1,False,aliases))
        self.assertEqual(hub_owner(3,True,aliases),'I3')
        self.assertTrue(same_hub({'owner':'T1'},{'owner':'T1'}))
        self.assertFalse(same_hub(None,{'owner':'T1'}))

if __name__=='__main__':unittest.main()
