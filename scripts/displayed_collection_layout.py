"""Offline geometry for displayed collection copies; no historical executors required."""
from hub_trial import transform
from fullmap_batch import StopBatch

def layout(template, origin, anchor):
 nodes={}
 for road in template['roads']:
  for i in (0,1):
   name=road['node'+str(i)];point=road['position'+str(i)]
   if name in nodes and nodes[name]!=point:raise StopBatch('Inconsistent template road node')
   nodes[name]=point
 if set(template.get('rolePortNodes',{}))!={'bus','truck'}:raise StopBatch('Template needs passenger and cargo ports')
 degrees={n:sum(n in (r['node0'],r['node1'])for r in template['roads'])for n in nodes}
 ends=[n for n,d in degrees.items()if d==1]
 if len(ends)!=2 or any(d>2 for d in degrees.values()) or len(template['roads'])!=len(nodes)-1:raise StopBatch('Only one frontage chain is supported')
 connected={ends[0]}
 while True:
  expanded=connected|{n for r in template['roads']if r['node0']in connected or r['node1']in connected for n in (r['node0'],r['node1'])}
  if expanded==connected:break
  connected=expanded
 if connected!=set(nodes):raise StopBatch('Disconnected template roads')
 for role in ('bus','truck'):
  if len(template['rolePortNodes'][role])!=1 or template['rolePortNodes'][role][0]not in nodes:raise StopBatch('Ambiguous template port')
 ordered=sorted(nodes,key=lambda n:nodes[n]['x'])
 bus=template['rolePortNodes']['bus'][0];truck=template['rolePortNodes']['truck'][0]
 if not nodes[ordered[0]]['x']<nodes[bus]['x']<nodes[truck]['x']<nodes[ordered[-1]]['x']:raise StopBatch('Unsupported frontage role order')
 return {'front':transform(template,origin,nodes[ordered[0]]),'end':transform(template,origin,nodes[ordered[-1]]),'anchor':anchor,
         'corridor':[transform(template,origin,nodes[n])for n in (ordered[0],bus,truck,ordered[-1])],
         'roadType':'country/country_new_small','sourceRoadTypePreserved':False}
