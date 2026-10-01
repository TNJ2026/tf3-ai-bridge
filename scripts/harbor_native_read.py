from pathlib import Path
import zipfile
root=Path('E:/SteamLibrary/steamapps/common/Transport Fever 3/base/content')
for archive, names in [('stations/water.zip',['water/small_pier.module.lua','water/passenger_dock_25_25.module.lua','water/pedestrian_entrance.module.lua']),('industries/fishing_grounds.zip',[])]:
 with zipfile.ZipFile(root/archive) as z:
  if not names: names=[n for n in z.namelist() if n.endswith(('.lua','.tl'))]
  for n in names:
   print('\nFILE',n,'\n',z.read(n).decode('utf-8'))
