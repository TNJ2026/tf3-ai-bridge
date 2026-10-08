import zipfile
from pathlib import Path
for p in Path('E:/SteamLibrary/steamapps/common/Transport Fever 3/base/content').rglob('*.zip'):
 with zipfile.ZipFile(p) as z:
  for n in z.namelist():
   if n.endswith(('.lua','.tl')) and ('vehicle_util' in n or 'buy_vehicle' in n):
    s=z.read(n).decode('utf-8',errors='replace')
    if 'makePart' in s or 'compartment2loadConfig' in s:
     print(p,n)
     Path('scripts/native_vehicle_util.txt').write_text(s,encoding='utf-8')
     lines=s.splitlines()
     for i,l in enumerate(lines):
      if 'function vehicle_util.makePart' in l or 'function vehicleUtil.makePart' in l or 'compartment2loadConfig' in l: print('\n'.join(lines[max(0,i-12):i+28]))
