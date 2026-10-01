-- Construction and engine-routing extension of the mock. The world gets a few street
-- nodes/edges, a "house" that makes proposals collide, and build commands that mutate
-- the component table the way the engine would.
local CT = api.type.ComponentType
for i, name in ipairs({ "BASE_NODE", "BASE_EDGE", "STATION", "EDGE_OBJECT", "BOUNDING_VOLUME", "TOWN_BUILDING" }) do
  CT[name] = 100 + i
end
local enum = api.type.enum
enum.BaseEdgeType = { NORMAL = 0, BRIDGE = 1, TUNNEL = 2 }
enum.RoadType = { TRACK = 0, STREET = 1 }
local TPL = "::/infrastructure/street/town/town_old_small.street_template"

local function vec3(x, y, z) return { x = x, y = y, z = z } end
api.type.Vec3f.new = vec3
api.type.Vec2f = { new = function(x, y) return { x = x, y = y } end }
api.type.Vec4f = { new = function(x, y, z, w) return { x = x, y = y, z = z, w = w } end }
api.type.Mat4f = { new = function(c1, c2, c3, c4)
  return { cols = { c1, c2, c3, c4 }, getTransl = function(self) return vec3(c4.x, c4.y, c4.z) end }
end }
api.type.SimpleProposal = {
  new = function() return { streetProposal = {}, constructionsToAdd = {}, constructionsToRemove = {} } end,
  ConstructionEntity = { new = function() return {} end },
}
api.type.SimpleStreetProposal = { EdgeObject = { new = function() return {} end } }
api.type.NodeAndEntity = { new = function() return { comp = {} } end }
api.type.SegmentAndEntity = { new = function() return { comp = {} } end }
api.type.Context = { new = function() return {} end }

-- a straight town street along y = 0 from x = 0 to x = 200, split at x = 100
local nextId = 5000
local function newEntity(comps) nextId = nextId + 1; components[nextId] = comps; return nextId end
local function addNode(x, y) return newEntity({ [CT.BASE_NODE] = { position = vec3(x, y, 2) } }) end
local function addEdge(n0, n1)
  local p0, p1 = components[n0][CT.BASE_NODE].position, components[n1][CT.BASE_NODE].position
  local t = vec3(p1.x - p0.x, p1.y - p0.y, 0)
  return newEntity({ [CT.BASE_EDGE] = { node0 = n0, node1 = n1, position0 = p0, position1 = p1,
    tangent0 = t, tangent1 = t, type = enum.BaseEdgeType.NORMAL, roadTemplate = TPL, roadType = enum.RoadType.STREET, objects = {} } })
end
STREET_A = addNode(0, 0); STREET_B = addNode(100, 0); STREET_C = addNode(200, 0)
EDGE_AB = addEdge(STREET_A, STREET_B); EDGE_BC = addEdge(STREET_B, STREET_C)
-- a house right next to the street at x = 50 on the right side (y < 0)
HOUSES = { { x = 50, y = -6 } }
HOUSE = newEntity({ [CT.CONSTRUCTION] = { fileName = "::/towns/house.con", townBuildings = { 1 },
  transf = { getTransl = function() return vec3(50, -6, 2) end } } })
frozen = {}  -- node/edge entity -> construction entity

local function positionOf(e)
  local c = components[e]
  if not c then return nil end
  if c[CT.BASE_NODE] then return c[CT.BASE_NODE].position end
  if c[CT.BASE_EDGE] then
    local be = c[CT.BASE_EDGE]
    return vec3((be.position0.x + be.position1.x) / 2, (be.position0.y + be.position1.y) / 2, 0)
  end
  if c[CT.BOUNDING_VOLUME] then return c[CT.BOUNDING_VOLUME].center end
  if c[CT.CONSTRUCTION] and c[CT.CONSTRUCTION].transf and c[CT.CONSTRUCTION].transf.getTransl then
    return c[CT.CONSTRUCTION].transf:getTransl()
  end
  return nil
end

api.engine.terrain = {
  getHeightAt = function(v) return 2 end,
  isOnWater = function(v) return false end,
  isValidCoordinate = function(v) return true end,
}
api.engine.util.octree = { findEntitiesInCircle = function(center, radius, ct)
  local out = {}
  for e, c in pairs(components) do
    if c[ct] then
      local p = positionOf(e)
      if p and math.sqrt((p.x - center.x) ^ 2 + (p.y - center.y) ^ 2) <= radius then out[#out + 1] = e end
    end
  end
  table.sort(out)
  return out
end }
api.engine.system.streetSystem = { getNodeSegments = function(node)
  local out = {}
  for e, c in pairs(components) do
    local be = c[CT.BASE_EDGE]
    if be and (be.node0 == node or be.node1 == node) then out[#out + 1] = e end
  end
  table.sort(out)
  return out
end }
local sc = api.engine.system.streetConnectorSystem
sc.getConstructionEntityForNode = function(n) return frozen[n] or -1 end
sc.getConstructionEntityForEdge = function(e) return frozen[e] or -1 end
local oldDepotLookup = sc.getConstructionEntityForDepot
local oldStationLookup = sc.getConstructionEntityForStation
sc.getConstructionEntityForStation = function(st)
  for con, c in pairs(components) do
    if c[CT.CONSTRUCTION] and c[CT.CONSTRUCTION].stations and c[CT.CONSTRUCTION].stations[1] == st then return con end
  end
  return oldStationLookup(st)
end
sc.getConstructionEntityForDepot = function(d)
  for con, c in pairs(components) do
    if c[CT.CONSTRUCTION] and c[CT.CONSTRUCTION].depots and c[CT.CONSTRUCTION].depots[1] == d then return con end
  end
  return oldDepotLookup(d)
end

api.res.streetTemplateRep = {
  find = function(n) return n == TPL and 1 or (n == TPL:gsub("old_small", "old_medium") and 2 or -1) end,
  get = function(id) return { laneConfigs = {}, streetStyle = "style" } end,
  getAll = function() return { TPL, "::/infrastructure/street/airport/runway.street_template" } end,
}
local STOP_CON = { ["::/stations/street/small_stops/small_old_twosided.con"] = { yearFrom = 0, yearTo = 1920 }, ["::/stations/street/small_stops/small_old.con"] = { yearFrom = 0, yearTo = 1920 },
  ["::/stations/street/small_stops/small_new.con"] = { yearFrom = 1990, yearTo = 0 } }
local conNames = {}
for name in pairs(STOP_CON) do conNames[#conNames + 1] = name end
table.sort(conNames)
api.res.moduleRep = {
  find = function(n) return (n:find("%.module$") or n:find("/trainstation___/", 1, true)) and 1 or -1 end,
  get = function(id) return { metadata = {}, updateScript = { fileName = "modules.script@fn", params = {} } } end,
}
api.res.constructionRep = {
  find = function(n) for i, v in ipairs(conNames) do if v == n then return i end end return -1 end,
  get = function(id) return { availability = STOP_CON[conNames[id]] } end,
}

-- where a proposal would put things, for collision checks against HOUSES
local function along(be, t)
  local p0, p1 = be.position0, be.position1
  return vec3(p0.x + (p1.x - p0.x) * t, p0.y + (p1.y - p0.y) * t, 0)
end
local function proposalPoints(p)
  local pts = {}
  for _, eo in ipairs(p.streetProposal.edgeObjectsToAdd or {}) do
    for _, e in ipairs(p.streetProposal.edgesToAdd or {}) do
      if e.entity == eo.edgeEntity then
        local pos = along(e.comp, eo.param)
        pts[#pts + 1] = vec3(pos.x, pos.y + (eo.left and 6 or -6), 0)
      end
    end
  end
  for _, n in ipairs(p.streetProposal.nodesToAdd or {}) do pts[#pts + 1] = n.comp.position end
  for _, ce in ipairs(p.constructionsToAdd or {}) do pts[#pts + 1] = ce.transf:getTransl() end
  return pts
end
local function evaluate(p)
  local messages, hits = {}, {}
  for _, pt in ipairs(proposalPoints(p)) do
    for _, h in ipairs(HOUSES) do
      if math.sqrt((pt.x - h.x) ^ 2 + (pt.y - h.y) ^ 2) < 4 then messages[1] = "collision"; hits[1] = HOUSE end
    end
  end
  local cost = #(p.streetProposal.edgesToAdd or {}) * 1000 + #(p.constructionsToAdd or {}) * 50000
    + #(p.streetProposal.edgeObjectsToAdd or {}) * 30000
  return messages, cost, hits
end
api.engine.util.proposal = { makeProposalData = function(p, ctx)
  if p.streetProposal.edgesToRemove then error("assertion: preview of removals is not supported") end
  local messages, cost, hits = evaluate(p)
  local entities = {}
  for _, e in ipairs(hits) do entities[#entities + 1] = { entity = e } end
  return { errorState = { critical = false, messages = messages, warnings = {} }, costs = cost,
           collisionInfo = { collisionEntities = entities } }
end,
  createProposalRemove = function(entity, ctx)
    return { streetProposal = {}, constructionsToAdd = {}, constructionsToRemove = { entity } }
  end,
  makeSegmentsRemoveProposal = function(edges)
    return { streetProposal = { edgesToRemove = edges }, constructionsToAdd = {}, constructionsToRemove = {} }
  end,
}

api.engine.util.proposal.replaceSegment = function(entity, template)
  local old = components[entity][CT.BASE_EDGE]
  local comp = {}
  for k,v in pairs(old) do comp[k] = v end
  comp.roadTemplate = template or old.roadTemplate
  local segment = {entity = -1, comp = comp}
  return { proposal = {addedSegments = {segment}, removedSegments = {{entity = entity}}},
    toRemove = {}, toAdd = {},
    streetProposal = {edgesToRemove = {entity}, edgesToAdd = {segment}}, constructionsToAdd = {} }
end

api.cmd.makeWorldBuildProposalCmd = function(p, ctx, ignoreErrors, playerInitiated)
  return { kind = "build", proposal = p, ignoreErrors = ignoreErrors }
end
api.cmd.makeScriptingSendEventCmd = function(src, id, name, param)
  return { kind = "scriptEvent", src = src, id = id, name = name, param = param }
end

local function applyBuild(cmd)
  local p = cmd.proposal
  local messages = evaluate(p)
  if #messages > 0 and not cmd.ignoreErrors then return false, {} end
  local map, results = {}, {}
  local added = { addedSegments = {}, addedNodes = {} }
  for _, n in ipairs(p.streetProposal.nodeConfigsToRemove or {}) do components[n][107] = nil end
  for _, e in ipairs(p.streetProposal.edgesToRemove or {}) do components[e] = nil end
  for _, e in ipairs(p.constructionsToRemove or {}) do
    -- removing a construction also removes what it owns (depots, entrance nodes)
    local con = components[e] and components[e][CT.CONSTRUCTION]
    for _, owned in ipairs(con and con.depots or {}) do components[owned] = nil end
    for _, owned in ipairs(con and con.stations or {}) do
      for g, gc in pairs(components) do
        if gc[CT.STATION_GROUP] and gc[CT.STATION_GROUP].stations[1] == owned then components[g] = nil end
      end
      components[owned] = nil
    end
    for _, owned in ipairs(con and con.frozenNodes or {}) do components[owned] = nil; frozen[owned] = nil end
    for _, owned in ipairs(con and con.frozenEdges or {}) do components[owned] = nil; frozen[owned] = nil end
    components[e] = nil
  end
  for _, n in ipairs(p.streetProposal.nodesToAdd or {}) do
    local id = newEntity({ [CT.BASE_NODE] = { position = n.comp.position } })
    map[n.entity] = id
    added.addedNodes[#added.addedNodes + 1] = { entity = id }
  end
  for _, e in ipairs(p.streetProposal.edgesToAdd or {}) do
    local c = e.comp
    local id = newEntity({ [CT.BASE_EDGE] = { node0 = map[c.node0] or c.node0, node1 = map[c.node1] or c.node1,
      position0 = c.position0, position1 = c.position1, tangent0 = c.tangent0, tangent1 = c.tangent1,
      roadTemplate = c.roadTemplate, roadType = c.roadType, type = c.type, objects = c.objects or {} } })
    map[e.entity] = id
    added.addedSegments[#added.addedSegments + 1] = { entity = id }
  end
  for _, eo in ipairs(p.streetProposal.edgeObjectsToAdd or {}) do
    local edge = components[map[eo.edgeEntity]][CT.BASE_EDGE]
    local pos = along(edge, eo.param)
    local station = newEntity({ [CT.STATION] = {}, [CT.EDGE_OBJECT] = { edgeObjectConstruction = eo.model },
      [CT.BOUNDING_VOLUME] = { center = pos } })
    edge.objects[#edge.objects + 1] = { station, eo.left and 0 or 1 }
    newEntity({ [CT.STATION_GROUP] = { stations = { station } }, [CT.NAME] = { name = eo.name or "New Stop" },
      [CT.PLAYER_OWNED] = { player = api.engine.util.getPlayer() } })
  end
  for _, ce in ipairs(p.constructionsToAdd or {}) do
    local t = ce.transf
    local c, s = t.cols[1].x, t.cols[1].y
    local pos = t:getTransl()
    -- entrance along local -y: 20.26 m for the road depot, 15 m for the street terminal (measured in game)
    local rail = ce.fileName:find("/stations/rail/", 1, true) ~= nil
    local terminal = ce.fileName:find("modular_terminal", 1, true) ~= nil
    local offset = terminal and 15 or 20.26
    -- like the game: a 15 m entrance stub (owned by the construction) from a frozen inner node
    -- to a free outer node, which is where streets connect
    local entrance = addNode(pos.x + offset * s, pos.y - offset * c)
    local outer = addNode(pos.x + (offset + 15) * s, pos.y - (offset + 15) * c)
    local stub = addEdge(entrance, outer)
    local depots, stations = {}, {}
    if terminal or rail then
      local station = newEntity({ [CT.STATION] = {}, [CT.BOUNDING_VOLUME] = { center = pos } })
      stations[1] = station
      newEntity({ [CT.STATION_GROUP] = { stations = { station } }, [CT.NAME] = { name = ce.name or "Terminal" },
        [CT.PLAYER_OWNED] = { player = api.engine.util.getPlayer() } })
    else
      depots[1] = newEntity({ [CT.VEHICLE_DEPOT] = { transportModes = { [3] = true } },
        [CT.PLAYER_OWNED] = { player = api.engine.util.getPlayer() } })
    end
    local con = newEntity({ [CT.CONSTRUCTION] = { fileName = ce.fileName, transf = t, frozenNodes = { entrance },
      frozenEdges = { stub }, depots = depots, stations = stations, params = ce.params } })
    if rail then
      local inner, outerRail = addNode(pos.x+10,pos.y), addNode(pos.x+10,pos.y+80)
      local railEdge = addEdge(inner,outerRail)
      components[railEdge][CT.BASE_EDGE].roadType = enum.RoadType.TRACK
      local c = components[con][CT.CONSTRUCTION]
      c.frozenNodes[#c.frozenNodes+1] = inner
      c.frozenEdges[#c.frozenEdges+1] = railEdge
      frozen[inner] = con; frozen[railEdge] = con
    end
    frozen[entrance] = con
    frozen[stub] = con
    results[#results + 1] = { con, 1 }
  end
  return true, results, added
end

engineState = { data = nil, subs = {} }
function engineState:get() return self.data end
function engineState:set(v) self.data = v end
function engineState:hasEventSubscriptions() return next(self.subs) ~= nil end
function engineState:subscribeToEvent(n) self.subs[n] = true end
builds = 0

local baseSend = api.cmd.sendCommand
api.cmd.sendCommand = function(cmd, cb)
  if cmd.kind == "scriptEvent" then
    -- delivered to the engine script (only if it subscribed), like the real broadcast
    if engineState.subs[cmd.name] then
      bridge_script.handleEvent(nil, engineState, cmd.src, cmd.id, cmd.name, cmd.param)
    end
    if cb then cb(cmd, true, {}) end
  elseif cmd.kind == "build" then
    builds = builds + 1
    local ok, results, added = applyBuild(cmd)
    if cb then cb({ proposal = { proposal = added or {} } }, ok, results) end
  else
    baseSend(cmd, cb)
  end
end
