from pathlib import Path
p=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua');s=p.read_text(encoding='utf-8');a=s.index('\t-- Preview success does not validate terminal topology.',s.index('commands.build_street_stop'));b=s.index('\tif args.kind',a)
s=s[:a]+'''	-- Legacy experimental mode never bypasses validation.
	if args.experimental == true then
		return { built = false, supported = false, mutationAttempted = false,
			code = "street_stop_apply_unavailable", hint = "Use preview=false with mandatory topology validation; experimental bypass is disabled." }
	end
'''+s[b:]
s=s.replace('\tcheck.applySupported = false','\tcheck.applySupported = true',1)
a=s.index('\tcheck.hint = "Geometry and terminal',s.index('commands.build_street_stop'));b=s.index('\n\treturn check',a)
s=s[:a]+'''	check.hint = "Terminal topology checked; preview=false submits one strict proposal."
	if args.preview == false then
		check.preview = false
		-- Never allow collision overrides for stop replacement, even when requested.
		if not check.ok or #check.collisions > 0 then return check end
		check.mutationAttempted = true
		local accepted = false
		local ok, err = pcall(function()
			api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal, nil, false, true), function(_, success) accepted = success end)
		end)
		check.stations, check.stationGroups = {}, {}
		local groups = {}
		local verified = true
		for _, id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(be.node0))) do
			local road = getComponent(id, "BASE_EDGE")
			if id ~= edgeEntity and road and ((road.node0 == be.node0 and road.node1 == be.node1) or (road.node1 == be.node0 and road.node0 == be.node1)) then
				check.newEdge = id
				local network = getComponent(id, "TRANSPORT_NETWORK")
				for _, ref in ipairs(road.objects) do
					local st = getComponent(ref[1], "STATION")
					local valid = st ~= nil and network ~= nil and #st.terminals > 0
					if valid then
						for _, term in ipairs(st.terminals) do
							local v = term.vehicleNodeId
							valid = valid and v.entity == id and v.index >= 0 and v.index < #network.nodes and #term.personNodes > 0
							for _, n in ipairs(term.personNodes) do valid = valid and n.entity == id and n.index >= 0 and n.index < #network.nodes end
						end
					end
					verified = verified and valid
					check.stations[#check.stations + 1] = { id = ref[1], side = ref[2], verified = valid }
					local g = stationGroupOfStation(ref[1]); if g then groups[g] = true end
				end
			end
		end
		for g in pairs(groups) do check.stationGroups[#check.stationGroups + 1] = g end
		check.built = ok and accepted and check.newEdge ~= nil and #check.stations == wanted and verified
		check.verified = check.built
		check.ok = check.built
		if not check.built then
			check.code = "street_stop_needs_reconciliation"
			check.error = not ok and tostring(err) or "Apply or post-build verification failed"
			check.hint = "World may be partially changed. Inspect newEdge/stations before any retry."
		end
	end'''+s[b:]
t=p.with_suffix('.lua.tmp');t.write_text(s,encoding='utf-8');t.replace(p)
p=Path('server/src/tf3_mcp/server.py');s=p.read_text(encoding='utf-8');s=s.replace('Actual construction is unavailable: the native terminal builder can partially mutate\n    roads before failing. preview=False returns a blocked result without any mutation.\n    A successful preview does not mean a station can safely be constructed.', 'Set preview=False to construct once after collision and terminal-node checks.\n    Returns both station IDs, groups, and post-build verification. A failed apply may\n    partially change the world: inspect the result before retrying. Collision overrides\n    and legacy experimental bypasses are not supported.');p.write_text(s,encoding='utf-8')
p=Path('server/tests/test_e2e.py');s=p.read_text(encoding='utf-8').replace('for args in ({"preview": False}, {"experimental": True},','for args in ({"experimental": True},').replace('r["applySupported"] is False','r["applySupported"] is True');p.write_text(s,encoding='utf-8')
