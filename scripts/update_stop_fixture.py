from pathlib import Path
p=Path('server/tests/mock_construction.lua');s=p.read_text(encoding='utf-8');s=s.replace('local STOP_CON = {', 'local STOP_CON = { ["::/stations/street/small_stops/small_old_twosided.con"] = { yearFrom = 0, yearTo = 1920 },');p.write_text(s,encoding='utf-8')
