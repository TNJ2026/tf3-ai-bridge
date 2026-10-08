def transport(sup,dem,cost):
 a=list(sup);b=list(dem);N=2+len(a)+len(b);src=N-2;sink=N-1;graph=[[]for _ in range(N)]
 def edge(u,v,cap,w):graph[u].append([v,len(graph[v]),cap,w]);graph[v].append([u,len(graph[u])-1,0,-w]);return graph[u][-1]
 for i,k in enumerate(a):edge(src,i,sup[k],0)
 for j,k in enumerate(b):edge(len(a)+j,sink,dem[k],0)
 refs={}
 for i,x in enumerate(a):
  for j,y in enumerate(b):refs[x,y]=edge(i,len(a)+j,1e8,cost(x,y))
 while True:
  ds=[1e50]*N;ds[src]=0;prev={}
  for _ in range(N):
   changed=False
   for u in range(N):
    for k,e in enumerate(graph[u]):
     v,rv,cap,w=e
     if cap>1e-7 and ds[u]+w<ds[v]-1e-8:ds[v]=ds[u]+w;prev[v]=(u,k);changed=True
   if not changed:break
  if sink not in prev:break
  amount=1e50;v=sink
  while v!=src:u,k=prev[v];amount=min(amount,graph[u][k][2]);v=u
  v=sink
  while v!=src:u,k=prev[v];e=graph[u][k];e[2]-=amount;graph[v][e[1]][2]+=amount;v=u
 return [(x,y,1e8-e[2])for (x,y),e in refs.items()if 1e8-e[2]>1e-5]
