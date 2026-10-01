import zipfile
with zipfile.ZipFile('E:/SteamLibrary/steamapps/common/Transport Fever 3/base/content/gui.zip') as z:
 s=z.read('gui/line_vehicle_mgmt/line_util.tl').decode('utf-8').splitlines()
 for i,l in enumerate(s):
  if 'makeIdvector' in l and i<120: print('\n'.join(s[max(0,i-2):i+14]))
