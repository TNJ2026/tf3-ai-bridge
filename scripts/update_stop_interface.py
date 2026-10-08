from pathlib import Path
p=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua')
s=p.read_text(encoding='utf-8')
a=s.index('\treturn p\nend\n\ncommands.build_street_stop',s.index('local function makeStopProposal'))
s=s[:a]+'''\t-- Replacing a segment also replaces every endpoint reference to it, including crosswalks.
	local configs, removed = {}, {}
	for _, node in ipairs({ be.node0, be.node1 }) do
		local old = getComponent(node, "BASE_NODE_CONFIG")
		if old == nil then error("street stop preview requires endpoint lane configuration", 0) end
		local cfg = api.type.BaseNodeLaneConnectionAndEntity.new()
		cfg.entity = node
		cfg.comp = old
		local lanes, walks = {}, {}
		for _, l in ipairs(old.laneConnections) do
			local v = api.type.LaneConnection.new()
			v.segment0 = l.segment0 == edgeEntity and -1 or l.segment0
			v.segment1 = l.segment1 == edgeEntity and -1 or l.segment1
			v.lane0, v.lane1 = l.lane0, l.lane1
			v.withRoad, v.withTram = l.withRoad, l.withTram
			lanes[#lanes + 1] = v
		end
		for _, e in ipairs(old.crosswalks) do walks[#walks + 1] = e == edgeEntity and -1 or e end
		cfg.comp.laneConnections, cfg.comp.crosswalks = lanes, walks
		configs[#configs + 1], removed[#removed + 1] = cfg, node
	end
	p.streetProposal.nodeConfigsToAdd, p.streetProposal.nodeConfigsToRemove = configs, removed
'''+s[a:]
a=s.index('\tif args.experimental ~= true then',s.index('commands.build_street_stop'))
b=s.index('\tlocal edgeEntity',a)
s=s[:a]+'''	-- Preview success does not validate terminal topology. Native apply can partially mutate
	-- the world before CalcNodeIndex asserts; experimental flags must not bypass this gate.
	if args.preview == false or args.experimental == true then
		return { built = false, supported = false, mutationAttempted = false,
			code = "street_stop_apply_unavailable",
			hint = "Native terminal topology is unverified (CalcNodeIndex). Use preview or place stops in the game UI." }
	end
	if args.kind ~= nil and args.kind ~= "auto" and args.kind ~= "old" and args.kind ~= "mid" and args.kind ~= "new" then error("invalid stop kind", 0) end
	if args.side ~= nil and args.side ~= "left" and args.side ~= "right" then error("side must be left or right", 0) end
'''+s[b:]
a=s.index('\tlocal params = {}',s.index('commands.build_street_stop'))
b=s.index('\nend\nENGINE_COMMANDS.build_street_stop',a)
s=s[:a]+'''	param = param or 0.5
	if param ~= param or param < 0.15 or param > 0.85 then error("param must be between 0.15 and 0.85", 0) end
	local left = args.side == "left"
	local check = previewProposal(makeStopProposal(edgeEntity, be, tplName, tpl, param, left, model, name))
	check.preview = true
	check.built = false
	check.applySupported = false
	check.mutationAttempted = false
	check.edge, check.model, check.param = edgeEntity, model, param
	check.position = roundPos(hermite(be, param))
	check.side = left and "left" or "right"
	check.twoSided = args.two_sided == true
	check.hint = "Geometry preview only; native terminal creation is not validated."
	return check'''+s[b:]
tmp=p.with_suffix('.lua.tmp');tmp.write_text(s,encoding='utf-8');tmp.replace(p)
p=Path('server/src/tf3_mcp/server.py');s=p.read_text(encoding='utf-8');i=s.index('@mcp.tool()\nasync def build_depot')
s=s[:i]+'''@mcp.tool()
async def build_street_stop(
    edge: int | None = None,
    x: float | None = None,
    y: float | None = None,
    param: float | None = None,
    radius: float = 50,
    two_sided: bool = True,
    side: str = "right",
    kind: str = "auto",
    name: str | None = None,
    preview: bool = True,
) -> dict:
    """Preview a roadside bus stop on an edge or near (x,y), including cost and collisions.
    two_sided previews both directions. param is 0.15..0.85 along the street.
    Actual construction is unavailable: the native terminal builder can partially mutate
    roads before failing. preview=False returns a blocked result without any mutation.
    A successful preview does not mean a station can safely be constructed.
    """
    args = {"edge": edge, "x": x, "y": y, "param": param, "radius": radius,
            "two_sided": two_sided, "side": side, "kind": kind, "name": name, "preview": preview}
    return await _call("build_street_stop", _timeout=BUILD_TIMEOUT,
                       **{k: v for k, v in args.items() if v is not None})


'''+s[i:];p.write_text(s,encoding='utf-8')
