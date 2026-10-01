from pathlib import Path
p=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua');s=p.read_text(encoding='utf-8');i=s.index('commands.bulldoze = function')
code='''-- Failed native stop construction can leave an EDGE_OBJECT without a parent road
-- or STATION. Such an object must be removed on its own, never by replacing roads.
commands.repair_orphan_street_stop = function(args)
	local id = requireEntity(args, "entity", "EDGE_OBJECT")
	local object = api.engine.getComponent(id, api.type.ComponentType.EDGE_OBJECT)
	local resource = object.edgeObjectConstruction
	if type(resource) ~= "string" or not resource:find("/stations/street/small_stops/", 1, true) then
		error("entity is not a recognized roadside stop", 0)
	end
	local owner = api.engine.system.streetSystem.getEdgeForEdgeObject(id)
	if owner == nil or owner >= 0 then error("stop still has a road owner; orphan cleanup refused", 0) end
	if getComponent(id, "STATION") then error("stop has a station component; orphan cleanup refused", 0) end
	local proposal = api.type.SimpleProposal.new()
	proposal.streetProposal.edgeObjectsToRemove = { id }
	local check = previewProposal(proposal)
	check.entity, check.preview, check.removed, check.mutationAttempted = id, args.preview ~= false, false, false
	if args.preview ~= false or not check.ok or #check.collisions > 0 then return check end
	check.mutationAttempted = true
	local accepted = false
	local ok, err = pcall(function()
		api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal, nil, false, true), function(_, success) accepted = success end)
	end)
	check.removed = ok and accepted and not api.engine.entityExists(id)
	check.ok = check.removed
	if not check.removed then
		check.code = "orphan_cleanup_needs_reconciliation"
		check.error = not ok and tostring(err) or "removal was not confirmed; inspect before retrying"
	end
	return check
end
ENGINE_COMMANDS.repair_orphan_street_stop = true

'''
s=s[:i]+code+s[i:];t=p.with_suffix('.lua.tmp');t.write_text(s,encoding='utf-8');t.replace(p)
p=Path('server/src/tf3_mcp/server.py');s=p.read_text(encoding='utf-8');i=s.index('@mcp.tool()\nasync def build_street_stop');s=s[:i]+'''@mcp.tool()
async def repair_orphan_street_stop(entity: int, preview: bool = True) -> dict:
    """Remove a failed roadside stop only if it has neither a road owner nor a station.
    Defaults to preview. Refuses valid stops, other objects and collision overrides.
    Set preview=False to remove the one orphan, preserving roads and normal stations.
    """
    return await _call("repair_orphan_street_stop", _timeout=BUILD_TIMEOUT,
                       entity=entity, preview=preview)


'''+s[i:];p.write_text(s,encoding='utf-8')
