from pathlib import Path
p=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua');s=p.read_text(encoding='utf-8');a=s.index('commands.create_line =');i=s.index('\t\tstops[#stops + 1] = stop',a)
s=s[:i]+'''		-- The GUI initializes these vectors; Line.Stop.new() leaves them empty.
		-- Empty load vectors produce "not configured to load any cargo", including passengers.
		local groupComp = getComponent(group, "STATION_GROUP")
		local stationComp = getComponent(listOf(groupComp.stations)[1], "STATION")
		local terminal = stationComp and listOf(stationComp.terminals)[1]
		local passengersOnly = terminal and terminal.passengersLoad and not terminal.cargoLoad
		local config = api.type.Line.StopConfig.new()
		local loads, maximum = {}, {}
		for id in pairs(api.res.cargoTypeRep.getAll(true)) do
			loads[id + 1] = not passengersOnly or id == 0
			maximum[id + 1] = 1
		end
		config.load, config.maxLoad, config.forceUnload = loads, maximum, false
		stop.stopConfig = config
'''+s[i:];i=s.index('\tline.stops = stops',a);s=s[:i]+s[i:].replace('\tline.stops = stops','\tline.stops = stops\n\tline.customFilters = true',1);tmp=p.with_suffix('.lua.tmp');tmp.write_text(s,encoding='utf-8');tmp.replace(p)
p=Path('server/tests/test_e2e.py');s=p.read_text(encoding='utf-8');i=s.index('        created = run(b.call("create_line"')
s=s[:i]+'''        game.lua.execute("""
            api.type.Line.StopConfig = {new=function()return {} end}
            api.res.cargoTypeRep = {getAll=function()return {[0]="PASSENGERS",[1]="LOGS"}end}
            components[210][api.type.ComponentType.STATION] = {terminals={{passengersLoad=true,cargoLoad=false}}}
            components[211][api.type.ComponentType.STATION] = {terminals={{passengersLoad=true,cargoLoad=false}}}
        """)
'''+s[i:];i=s.index('        assert',s.index('        created = run(b.call("create_line"'))
s=s[:i]+'''        for stop in game.lua.globals().components[created["line"]][3].stops.values():
            assert stop.stopConfig.load[1] is True
            assert stop.stopConfig.load[2] is False
            assert stop.stopConfig.maxLoad[1] == 1
'''+s[i:];p.write_text(s,encoding='utf-8')
