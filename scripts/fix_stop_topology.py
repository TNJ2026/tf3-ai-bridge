from pathlib import Path
p=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua');s=p.read_text(encoding='utf-8')
s=s.replace('\tedge.comp.laneConfigs = tpl.laneConfigs\n\tedge.comp.roadStyle = tpl.streetStyle\n\tpcall(function() edge.streetEdge', '\tpcall(function() edge.streetEdge',1)
a=s.index('\tlocal eo = api.type.SimpleStreetProposal.EdgeObject.new()',s.index('local function makeStopProposal'));b=s.index('\t-- Replacing a segment',a)
s=s[:a]+'''	-- Native edge-object IDs are reserved separately from new road/node IDs.
	-- Observed in the live engine: -400000000, -400000001, ... . Without these
	-- references the preview succeeds but no terminal network nodes are generated.
	local objects, refs = {}, {}
	local sides = model:find("_twosided", 1, true) and { false, true } or { left }
	for i, side in ipairs(sides) do
		local eo = api.type.SimpleStreetProposal.EdgeObject.new()
		eo.edgeEntity, eo.param, eo.oneWay, eo.left = -1, param, false, side
		eo.model, eo.playerEntity = model, api.engine.util.getPlayer()
		if name then eo.name = name end
		eo.params = { seed = 0, year = currentYear() or 1900 }
		objects[#objects + 1] = eo
		refs[#refs + 1] = { -400000000 - (i - 1), side and api.type.enum.EdgeObjectType.STOP_LEFT or api.type.enum.EdgeObjectType.STOP_RIGHT }
	end
	edge.comp.objects = refs
	local p = api.type.SimpleProposal.new()
	p.streetProposal.edgesToRemove = { edgeEntity }
	p.streetProposal.edgesToAdd = { edge }
	p.streetProposal.edgeObjectsToAdd = objects
'''+s[b:]
# Keep apply disabled until live verification; validate topology through the same proposal data.
a=s.index('\tlocal check = previewProposal(makeStopProposal(',s.index('commands.build_street_stop'));b=s.index('\tcheck.preview = true',a)
s=s[:a]+'''	local proposal = makeStopProposal(edgeEntity, be, tplName, tpl, param, left, model, name)
	local check = previewProposal(proposal)
	local ok, pd = pcall(api.engine.util.proposal.makeProposalData, proposal, nil)
	local tn = ok and pd and pd.entity2tn[-1] or nil
	local pedestrians, buses = {}, {}
	if tn then
		for _, e in ipairs(tn.edges) do
			for _, c in ipairs(e.conns) do
				if c.entity == -1 and c.index >= 0 and c.index < #tn.nodes then
					if e.transportModes[api.type.enum.TransportMode.BUS] then buses[c.index] = true end
					if e.transportModes[0] then pedestrians[c.index] = true end
				end
			end
		end
	end
	local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end
	local wanted = args.two_sided == true and 2 or 1
	check.topology = { nodes = tn and #tn.nodes or 0, pedestrianNodes = count(pedestrians), busNodes = count(buses), expectedSides = wanted }
	check.topology.valid = check.topology.pedestrianNodes >= wanted and check.topology.busNodes >= wanted
	check.geometryOk = check.ok
	check.ok = check.ok and check.topology.valid
	if not check.topology.valid then check.code = "street_stop_terminal_nodes_missing" end
'''+s[b:]
s=s.replace('check.hint = "Geometry preview only; native terminal creation is not validated."','check.hint = "Geometry and terminal network preview; native apply remains gated pending live verification."')
t=p.with_suffix('.lua.tmp');t.write_text(s,encoding='utf-8');t.replace(p)
