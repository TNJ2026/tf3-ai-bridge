from pathlib import Path
import zipfile
with zipfile.ZipFile('E:/SteamLibrary/steamapps/common/Transport Fever 3/base/content/gui.zip') as z:
 for n in z.namelist():
  if n.endswith('.tl') and ('line_util' in n or 'line_react' in n):
   ss=z.read(n).decode('utf-8').splitlines()
   for i,l in enumerate(ss):
    if 'stopConfig' in l or 'maxLoad =' in l: print(n, '\n'.join(ss[max(0,i-5):i+9]))
