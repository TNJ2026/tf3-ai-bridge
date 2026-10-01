from pathlib import Path
import zipfile
for p in (Path('E:/SteamLibrary/steamapps/common/Transport Fever 3/base/content')).rglob('*.zip'):
 with zipfile.ZipFile(p) as z:
  for n in z.namelist():
   if n.endswith(('.lua','.tl')):
    data=z.read(n)
    if b'makeLineCreateCmd' in data:
     ss=data.decode('utf-8',errors='replace').splitlines();print(n)
     for i,l in enumerate(ss):
      if 'makeLineCreateCmd' in l:print('\n'.join(ss[max(0,i-18):i+7]))
