import zipfile
from pathlib import Path
root=Path('E:/SteamLibrary/steamapps/common/Transport Fever 3')
for p in (root/'base/content').rglob('*.zip'):
 with zipfile.ZipFile(p) as z:
  for n in z.namelist():
   if n.endswith(('.lua','.tl')):
    b=z.read(n)
    if b'edgeObjectsToAdd' in b or b'CalcNodeIndex' in b:
     print(str(p),n)
     text=b.decode('utf-8',errors='replace').splitlines()
     for i,l in enumerate(text):
      if 'edgeObjectsToAdd' in l: print('\n'.join(text[max(0,i-6):i+12]))
