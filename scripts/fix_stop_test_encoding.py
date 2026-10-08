from pathlib import Path
p=Path('scripts/update_stop_topology_tests.py');s=p.read_text(encoding='utf-8').replace('.read_text()',".read_text(encoding='utf-8')");p.write_text(s,encoding='utf-8')
p=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua');s=p.read_text(encoding='utf-8')
try:
 repaired=s.encode('gbk').decode('utf-8')
 if repaired!=s:
  print('restored UTF-8 source decoding')
  p.write_text(repaired,encoding='utf-8')
except UnicodeError: print('source has native UTF-8 content; no transcoding applied')
