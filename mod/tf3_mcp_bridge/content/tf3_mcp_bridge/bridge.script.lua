-- TF3 MCP Bridge: game script side.
--
-- Game scripts have neither sockets nor the io library, so we talk to the external
-- MCP server through the game's own userdata files (app.saveUserdata/loadUserdata,
-- available in the GUI state), stored in <userdata>/local/tf3_mcp/:
--   request.lua    written by the server: {"id": "...", "cmd": "...", "args": {...}}
--   response.lua   written by us:         {"id": "...", "ok": true, "result": ..., "error": "..."}
--   heartbeat.lua  written by us periodically, with environment probe results
-- Each file holds a table { hex = "<hex-encoded JSON>" }, so neither side depends on
-- how the game escapes strings. One request is in flight at a time.

local BRIDGE_VERSION = "0.12.20"
local USERDATA_DIR = "tf3_mcp"
local POLL_INTERVAL = 0.1       -- seconds (wall clock) between request polls
local HEARTBEAT_INTERVAL = 1.0  -- seconds (wall clock) between heartbeats
local MAX_LIST = 2000
-- Diagnostic installer may pin one audited legacy rejection; never caller supplied.
local NETWORK_REJECTION_MIGRATION = nil

------------------------------------------------------------------------------
-- logging
------------------------------------------------------------------------------

local function log(...)
	local parts = { "[tf3_mcp_bridge]" }
	for i = 1, select("#", ...) do
		parts[#parts + 1] = tostring((select(i, ...)))
	end
	local msg = table.concat(parts, " ")
	if debugPrint then
		pcall(debugPrint, msg)
	else
		print(msg)
	end
end

------------------------------------------------------------------------------
-- JSON (minimal, Lua 5.2 compatible)
------------------------------------------------------------------------------

local json = {}
-- Keep codec helpers scoped; resource loading also needs local-variable headroom.
do

local escapes = {
	['"'] = '\\"', ["\\"] = "\\\\", ["\b"] = "\\b", ["\f"] = "\\f",
	["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t",
}

local function encodeString(s)
	return '"' .. s:gsub('[%c"\\]', function(c)
		return escapes[c] or string.format("\\u%04x", c:byte())
	end) .. '"'
end

local function encodeNumber(n)
	if n ~= n or n == math.huge or n == -math.huge then
		return "null"
	end
	if n == math.floor(n) and n > -1e15 and n < 1e15 then
		return string.format("%.0f", n)
	end
	return string.format("%.14g", n)
end

local function isArray(t)
	local n = 0
	for k in pairs(t) do
		if type(k) ~= "number" or k <= 0 or k ~= math.floor(k) then
			return false
		end
		n = n + 1
	end
	for i = 1, n do
		if t[i] == nil then return false end
	end
	return true, n
end

-- Empty tables encode as [] (lists are far more common in our results);
-- wrap a table with json.object() to force {} when empty.
local OBJECT_MT = {}
function json.object(t)
	return setmetatable(t or {}, OBJECT_MT)
end

local function encodeValue(v, depth, seen)
	local tv = type(v)
	if v == nil then
		return "null"
	elseif tv == "boolean" then
		return v and "true" or "false"
	elseif tv == "number" then
		return encodeNumber(v)
	elseif tv == "string" then
		return encodeString(v)
	elseif tv == "table" then
		if seen[v] then return '"<cycle>"' end
		if depth > 12 then return '"<max depth>"' end
		if next(v) == nil then
			return getmetatable(v) == OBJECT_MT and "{}" or "[]"
		end
		seen[v] = true
		local out = {}
		local arr, n = isArray(v)
		if arr then
			for i = 1, n do
				out[i] = encodeValue(v[i], depth + 1, seen)
			end
			seen[v] = nil
			return "[" .. table.concat(out, ",") .. "]"
		end
		for k, val in pairs(v) do
			out[#out + 1] = encodeString(tostring(k)) .. ":" .. encodeValue(val, depth + 1, seen)
		end
		seen[v] = nil
		return "{" .. table.concat(out, ",") .. "}"
	else
		-- userdata / function / thread: not representable, describe it
		return encodeString(tostring(v))
	end
end

function json.encode(v)
	return encodeValue(v, 0, {})
end

local function decodeError(str, pos, msg)
	error(string.format("json decode error at %d: %s", pos, msg), 0)
end

local function skipWs(str, pos)
	return (str:find("[^ \t\r\n]", pos)) or (#str + 1)
end

local decodeValue

local function codepointToUtf8(cp)
	if cp < 0x80 then
		return string.char(cp)
	elseif cp < 0x800 then
		return string.char(0xC0 + math.floor(cp / 0x40), 0x80 + cp % 0x40)
	elseif cp < 0x10000 then
		return string.char(0xE0 + math.floor(cp / 0x1000), 0x80 + math.floor(cp / 0x40) % 0x40, 0x80 + cp % 0x40)
	else
		return string.char(0xF0 + math.floor(cp / 0x40000), 0x80 + math.floor(cp / 0x1000) % 0x40,
			0x80 + math.floor(cp / 0x40) % 0x40, 0x80 + cp % 0x40)
	end
end

local function decodeString(str, pos)
	local buf = {}
	local i = pos + 1
	while true do
		local c = str:sub(i, i)
		if c == "" then decodeError(str, i, "unterminated string") end
		if c == '"' then
			return table.concat(buf), i + 1
		elseif c == "\\" then
			local e = str:sub(i + 1, i + 1)
			local map = { b = "\b", f = "\f", n = "\n", r = "\r", t = "\t", ['"'] = '"', ["\\"] = "\\", ["/"] = "/" }
			if map[e] then
				buf[#buf + 1] = map[e]
				i = i + 2
			elseif e == "u" then
				local hex = str:sub(i + 2, i + 5)
				local cp = tonumber(hex, 16)
				if not cp then decodeError(str, i, "bad unicode escape") end
				i = i + 6
				-- surrogate pair
				if cp >= 0xD800 and cp <= 0xDBFF and str:sub(i, i + 1) == "\\u" then
					local lo = tonumber(str:sub(i + 2, i + 5), 16)
					if lo and lo >= 0xDC00 and lo <= 0xDFFF then
						cp = 0x10000 + (cp - 0xD800) * 0x400 + (lo - 0xDC00)
						i = i + 6
					end
				end
				buf[#buf + 1] = codepointToUtf8(cp)
			else
				decodeError(str, i, "bad escape")
			end
		else
			local j = str:find('["\\]', i)
			if not j then decodeError(str, i, "unterminated string") end
			buf[#buf + 1] = str:sub(i, j - 1)
			i = j
		end
	end
end

decodeValue = function(str, pos)
	pos = skipWs(str, pos)
	local c = str:sub(pos, pos)
	if c == "{" then
		local obj = {}
		pos = skipWs(str, pos + 1)
		if str:sub(pos, pos) == "}" then return obj, pos + 1 end
		while true do
			pos = skipWs(str, pos)
			if str:sub(pos, pos) ~= '"' then decodeError(str, pos, "expected key") end
			local key
			key, pos = decodeString(str, pos)
			pos = skipWs(str, pos)
			if str:sub(pos, pos) ~= ":" then decodeError(str, pos, "expected ':'") end
			local val
			val, pos = decodeValue(str, pos + 1)
			obj[key] = val
			pos = skipWs(str, pos)
			local d = str:sub(pos, pos)
			if d == "}" then return obj, pos + 1 end
			if d ~= "," then decodeError(str, pos, "expected ',' or '}'") end
			pos = pos + 1
		end
	elseif c == "[" then
		local arr = {}
		pos = skipWs(str, pos + 1)
		if str:sub(pos, pos) == "]" then return arr, pos + 1 end
		while true do
			local val
			val, pos = decodeValue(str, pos)
			arr[#arr + 1] = val
			pos = skipWs(str, pos)
			local d = str:sub(pos, pos)
			if d == "]" then return arr, pos + 1 end
			if d ~= "," then decodeError(str, pos, "expected ',' or ']'") end
			pos = pos + 1
		end
	elseif c == '"' then
		return decodeString(str, pos)
	elseif str:sub(pos, pos + 3) == "true" then
		return true, pos + 4
	elseif str:sub(pos, pos + 4) == "false" then
		return false, pos + 5
	elseif str:sub(pos, pos + 3) == "null" then
		return nil, pos + 4
	else
		local numStr = str:match("^-?%d+%.?%d*[eE]?[-+]?%d*", pos)
		local n = numStr and tonumber(numStr)
		if not n then decodeError(str, pos, "unexpected character '" .. c .. "'") end
		return n, pos + #numStr
	end
end

function json.decode(str)
	local ok, val = pcall(function()
		local v, pos = decodeValue(str, 1)
		pos = skipWs(str, pos)
		if pos <= #str then decodeError(str, pos, "trailing garbage") end
		return v
	end)
	if ok then return val end
	return nil, val
end

end -- JSON private helpers

------------------------------------------------------------------------------
-- environment probe
------------------------------------------------------------------------------

local function probeEnv()
	-- Inspect only: do not load native libraries, clear resource caches, or invoke
	-- undocumented functions while discovering a possible non-UI transport.
	local function memberTypes(value)
		local result = {}
		if type(value) == "table" then
			for key, member in next, value do
				if type(key) == "string" then result[key] = type(member) end
			end
		end
		return result
	end
	local p = {
		bridgeVersion = BRIDGE_VERSION,
		luaVersion = _VERSION,
		io = type(io),
		io_open = type(io) == "table" and type(io.open) or "nil",
		os = type(os),
		os_clock = type(os) == "table" and type(os.clock) or "nil",
		os_time = type(os) == "table" and type(os.time) or "nil",
		os_getenv = type(os) == "table" and type(os.getenv) or "nil",
		os_rename = type(os) == "table" and type(os.rename) or "nil",
		os_remove = type(os) == "table" and type(os.remove) or "nil",
		load = type(load),
		transportDiscoveryVersion = 1,
		loadfile = type(loadfile),
		dofile = type(dofile),
		require = type(require),
		ug_require = type(ug_require),
		ug_require_cleanup = type(ug_require_cleanup),
		ug_members = memberTypes(ug),
		package_members = memberTypes(package),
		resolveutil_members = memberTypes(resolveutil),
		debugPrint = type(debugPrint),
		api = type(api),
		game = type(game),
		app = type(app),
		app_saveUserdata = type(app) == "table" and type(app.saveUserdata) or "nil",
		app_loadUserdata = type(app) == "table" and type(app.loadUserdata) or "nil",
	}
	if type(getBuildVersion) == "function" then
		local ok, v = pcall(getBuildVersion)
		p.buildVersion = ok and tostring(v) or nil
	end
	return p
end

local probe = probeEnv()

local function wallClock()
	if type(os) == "table" and type(os.clock) == "function" then
		local ok, v = pcall(os.clock)
		if ok and type(v) == "number" then return v end
	end
	return nil
end

------------------------------------------------------------------------------
-- transport: userdata files holding hex-encoded JSON
------------------------------------------------------------------------------

local function hexEncode(s)
	return (s:gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

local function hexDecode(h)
	return (h:gsub("%x%x", function(pair) return string.char(tonumber(pair, 16)) end))
end

-- Engine-bound functions show up as tables (type "table") whose metatable may be hidden,
-- so we don't type-check them: we just call them under pcall.
local function isCallable(f)
	return f ~= nil and f ~= false
end

local function transportAvailable()
	return type(app) == "table" and isCallable(app.saveUserdata) and isCallable(app.loadUserdata)
end

local function describe(f)
	local mt = nil
	pcall(function() mt = getmetatable(f) end)
	return type(f) .. " mt=" .. type(mt) .. " call=" .. tostring(type(mt) == "table" and type(mt.__call) or nil)
end

local function writeMessage(name, text)
	local ok, err = pcall(app.saveUserdata, USERDATA_DIR, name, { hex = hexEncode(text) })
	if ok then return true end
	return false, tostring(err)
end

local function messageExists(name)
	local ok, names = pcall(app.getAllUserdata, USERDATA_DIR)
	if not ok or type(names) ~= "table" then return true end -- can't tell; just try
	for _, n in ipairs(names) do
		if n == name then return true end
	end
	return false
end

local function readMessage(name)
	if not messageExists(name) then return nil end
	local ok, t = pcall(app.loadUserdata, USERDATA_DIR, name)
	if ok and type(t) == "table" and type(t.hex) == "string" then
		return hexDecode(t.hex)
	end
	return nil
end

local function removeMessage(name)
	if isCallable(app.removeUserdata) then
		pcall(app.removeUserdata, USERDATA_DIR, name)
	end
end

local function userdataFolder()
	if type(app) ~= "table" or not isCallable(app.getUserDataFolder) then return nil end
	local ok, v = pcall(app.getUserDataFolder)
	if ok then return tostring(v) end
	return nil
end

------------------------------------------------------------------------------
-- helpers for game data
------------------------------------------------------------------------------

local CT = nil
local function componentTypes()
	if CT == nil then CT = api.type.ComponentType end
	return CT
end

local function getComponent(entity, ctName)
	local ctype = componentTypes()[ctName]
	if ctype == nil then return nil end
	local ok, comp = pcall(api.engine.getComponent, entity, ctype)
	if ok then return comp end
	return nil
end

local function entityName(entity)
	local comp = getComponent(entity, "NAME")
	if comp ~= nil then
		local ok, name = pcall(function() return comp.name end)
		if ok then return name end
	end
	return nil
end

local function vec3(v)
	if v == nil then return nil end
	local ok, res = pcall(function() return { v.x, v.y, v.z } end)
	if ok then return res end
	return nil
end

-- Public component fields from the bundled game API (build 40408).
-- Engine component userdata cannot generally be iterated with pairs().
local COMPONENT_FIELDS = {
	ASSET_GROUP = {},
	WATER_MESH = { "waterLevel", "vertices", "depths", "indices", "contours", "pos" },
	TERRAIN_TILE = { "terrainEntity", "position" },
	TERRAIN_TILE_HEIGHTMAP = { "vertices" },
	TERRAIN_TILE_BRUSH = { "materialIndexBrush", "forceAboveBit" },
	STATION = { "tag", "terminals", "catchmentAreas", "pool" },
	NAME = { "name" },
	TOWN = { "initialLandUseCapacities", "capacityScalingFactor", "levelToCapacityDistributionWeights", "sizeFactors", "cargoNeeds", "developmentActive", "noise", "pollution" },
	INDUSTRY = { "stockList", "level", "closureTimeStamp", "upgradeProgress", "manualDevelopment", "construction", "maxLevel" },
	TOWN_BUILDING = { "personCapacity", "stockList", "construction", "level", "parcels", "depth", "height", "town", "timeBuilt", "blockedDevelopment" },
	CONSTRUCTION = { "fileName", "params", "transf", "timeBuilt", "frozenNodes", "frozenEdges", "depots", "stations", "industries", "townBuildings", "subconstructions", "persistentMetadata", "slots", "slotConfig", "dependentSlots", "tag2modelInstance", "entityAndIndex2labelTexts", "tag2segments" },
	BASE_NODE = { "position" },
	BASE_EDGE = { "type", "typeIndex", "objects", "laneConfigs", "roadDevelopmentLocked", "node0", "node1", "position0", "position1", "tangent0", "tangent1", "laneConfig", "edgeDecorations", "distance", "roadType", "roadTemplate", "roadStyle" },
	STATION_GROUP = { "stations" },
	VEHICLE_DEPOT = { "carrier", "transportModes", "inNodes", "outNodes", "state", "doors", "stateTime", "catchmentArea", "maintenancePool", "maxPoolUsage", "averagePoolUsage", "poolUsageTicks", "filterTags" },
	TRANSPORT_VEHICLE = { "carrier", "transportVehicleConfig", "config", "state", "userStopped", "depot", "sellOnArrival", "line", "stopIndex", "arrivalStationTerminal", "arrivalStationTerminalLocked", "lineStopDepartures", "lastLineStopDeparture", "sectionTimes", "lineStop2cargo2available", "loadState", "timeUntilNextScheduledDeparture", "loadSpeedModifiers", "timeUntilCloseDoors", "timeUntilDeparture", "timeUntilNextLoad", "timeUntilNextUnload", "lastStationStockIndex", "doorsTime", "daysInDepot", "daysAtTerminal", "doorsOpen", "noPath", "autoDeparture", "maintenanceStation", "modifiers", "unloadPendingIncome", "closestTown", "visitedStops" },
	LINE = { "stops", "vehicleInfo", "customFilters", "reservationPriority" },
	PLAYER_OWNED = { "player" },
	ACCOUNT = { "balance", "loan" },
	GAME_TIME = { "gameTime", "gameTime0", "dates", "timeOfDaySec", "tickCount", "updateCount" },
	GAME_SPEED = { "speedup", "millisPerDay" },
	TERRAIN = { "size", "baseLevels", "baseResolution", "highLevels", "offsetZ", "waterLevel", "dataMaps" },
	BOUNDING_VOLUME = { "bbox" },
	STOCK_LIST = { "stocks", "rules", "stockDatas", "ruleDatas", "cargoData", "thrownAwayCargo", "modifiers" },
	SIM_PERSON = { "cargoType", "destinations", "moveModes", "travelTimes", "targetOrAtEntity", "lastNonResType", "lastMoveMode", "walkSpeed", "modelIdPerson", "colorConfigPerson", "modelIdCar", "colorConfigCar", "lastDestinationUpdate", "landUse2ReachableWalkDrive", "landUse2ReachableLines", "pickupTime", "happiness" },
	SIM_CARGO = { "cargoType", "targetOrPickupEntity", "sourceEntity", "pickupPoints", "speed", "startTime", "pickupTime", "deliveryExtensionDuration" },
	PERSON_CAPACITY = { "type", "capacity", "personNodes", "vehicleNodes", "pathfindingPreference" },
	MODEL_INSTANCE_LIST = { "fatInstances", "thinInstances", "dynamic" },
	TRANSPORT_NETWORK = { "nodes", "edges", "turnaroundEdges" },
	EDGE_OBJECT = { "param", "transf", "edgeObjectConstruction", "params" },
}

-- BEGIN GENERATED COMPONENT SCHEMAS
local COMPONENT_RECORDS = { ["ASSET_GROUP"] = "Engine.Component.AssetGroup", ["WATER_MESH"] = "Engine.Component.WaterMesh", ["TERRAIN_TILE"] = "Engine.Component.TerrainTile", ["TERRAIN_TILE_HEIGHTMAP"] = "Engine.Component.TerrainTileHeightmap", ["TERRAIN_TILE_BRUSH"] = "Engine.Component.TerrainTileBrush", ["STATION"] = "Station", ["NAME"] = "Engine.Component.Name", ["TOWN"] = "Engine.Component.Town", ["INDUSTRY"] = "Engine.Component.Industry", ["TOWN_BUILDING"] = "Engine.Component.TownBuilding", ["CONSTRUCTION"] = "Engine.Component.Construction", ["BASE_NODE"] = "Engine.Component.BaseNode", ["BASE_EDGE"] = "Engine.Component.BaseEdge", ["STATION_GROUP"] = "Engine.Component.StationGroup", ["VEHICLE_DEPOT"] = "Engine.Component.VehicleDepot", ["TRANSPORT_VEHICLE"] = "Engine.Component.TransportVehicle", ["LINE"] = "Engine.Component.Line", ["PLAYER_OWNED"] = "Engine.Component.PlayerOwned", ["ACCOUNT"] = "Engine.Component.Account", ["GAME_TIME"] = "Engine.Component.GameTime", ["GAME_SPEED"] = "Engine.Component.GameSpeed", ["TERRAIN"] = "Engine.Component.Terrain", ["BOUNDING_VOLUME"] = "Engine.Component.BoundingVolume", ["STOCK_LIST"] = "Engine.Component.StockList", ["SIM_PERSON"] = "Engine.Component.SimPerson", ["SIM_CARGO"] = "Engine.Component.SimCargo", ["PERSON_CAPACITY"] = "Engine.Component.PersonCapacity", ["MODEL_INSTANCE_LIST"] = "Engine.Component.ModelInstanceList", ["TRANSPORT_NETWORK"] = "Engine.Component.TransportNetwork", ["EDGE_OBJECT"] = "Engine.Component.EdgeObject" }
local RECORD_SCHEMAS = {
	["Box3f"] = { ["min"] = "Vec3f", ["max"] = "Vec3f" },
	["CargoTypeSet"] = { ["cargoClassesIncluded"] = { ["element"] = "" }, ["cargoClassesExcluded"] = { ["element"] = "" }, ["cargoTypesIncluded"] = { ["element"] = "" }, ["cargoTypesExcluded"] = { ["element"] = "" } },
	["CatchmentArea"] = { ["position"] = "Vec3f", ["radius"] = "" },
	["ConstructionInstanceMetadata"] = {  },
	["Edge"] = { ["conns"] = { ["element"] = "NodeId" }, ["geometry"] = "EdgeGeometry", ["transportModes"] = { ["element"] = "" }, ["speedLimit"] = "", ["curveSpeedLimit"] = "", ["curSpeed"] = "", ["linkable"] = "", ["pedestrianWalkPenalty"] = "", ["precedence"] = "", ["noiseModifier"] = "", ["pollutionModifier"] = "", ["needsReservation"] = "", ["forwardOnly"] = "" },
	["EdgeGeometry"] = { ["type"] = "", ["arc"] = "EdgeGeometry.Arc", ["straight"] = "EdgeGeometry.Straight", ["cubicSpline"] = "EdgeGeometry.CubicSpline", ["cubicOffsetSpline"] = "EdgeGeometry.CubicOffsetSpline", ["tangent"] = "Vec2f", ["height"] = "Vec2f", ["length"] = "", ["width"] = "" },
	["EdgeGeometry.Arc"] = { ["center"] = "Vec2f", ["radius"] = "", ["startAngle"] = "", ["angle"] = "" },
	["EdgeGeometry.CubicOffsetSpline"] = { ["pos"] = { ["element"] = "Vec2f" }, ["tangent"] = { ["element"] = "Vec2f" }, ["offset"] = "" },
	["EdgeGeometry.CubicSpline"] = { ["pos"] = { ["element"] = "Vec2f" }, ["tangent"] = { ["element"] = "Vec2f" } },
	["EdgeGeometry.Straight"] = { ["pos"] = { ["element"] = "Vec2f" } },
	["EdgeId"] = { ["entity"] = "", ["index"] = "" },
	["EdgePos"] = { ["edgeId"] = "EdgeId", ["param"] = "" },
	["Engine.Component.Account"] = { ["balance"] = "", ["loan"] = "" },
	["Engine.Component.AssetGroup"] = {  },
	["Engine.Component.BaseEdge"] = { ["type"] = "", ["typeIndex"] = "", ["objects"] = { ["element"] = "" }, ["laneConfigs"] = { ["element"] = "LaneConfig" }, ["roadDevelopmentLocked"] = "", ["node0"] = "", ["node1"] = "", ["position0"] = "Vec3f", ["position1"] = "Vec3f", ["tangent0"] = "Vec3f", ["tangent1"] = "Vec3f", ["laneConfig"] = { ["element"] = "LaneConfig" }, ["edgeDecorations"] = { ["element"] = "" }, ["distance"] = "", ["roadType"] = "", ["roadTemplate"] = "", ["roadStyle"] = "" },
	["Engine.Component.BaseNode"] = { ["position"] = "Vec3f" },
	["Engine.Component.BoundingVolume"] = { ["bbox"] = "Box3f" },
	["Engine.Component.Construction"] = { ["fileName"] = "", ["params"] = "Engine.Component.Construction.ConstructionParams", ["transf"] = "Mat4f", ["timeBuilt"] = "", ["frozenNodes"] = { ["element"] = "" }, ["frozenEdges"] = { ["element"] = "" }, ["depots"] = { ["element"] = "" }, ["stations"] = { ["element"] = "" }, ["industries"] = { ["element"] = "" }, ["townBuildings"] = { ["element"] = "" }, ["subconstructions"] = { ["element"] = "" }, ["persistentMetadata"] = "ConstructionInstanceMetadata", ["slots"] = { ["element"] = "Slot" }, ["slotConfig"] = { ["element"] = "SlotConfig" }, ["dependentSlots"] = "", ["tag2modelInstance"] = "", ["entityAndIndex2labelTexts"] = "", ["tag2segments"] = "" },
	["Engine.Component.Construction.ConstructionParams"] = { ["seed"] = "", ["year"] = "", ["modules"] = { ["element"] = "" } },
	["Engine.Component.EdgeObject"] = { ["param"] = "", ["transf"] = "Mat4f", ["edgeObjectConstruction"] = "", ["params"] = "" },
	["Engine.Component.GameSpeed"] = { ["speedup"] = "", ["millisPerDay"] = "" },
	["Engine.Component.GameTime"] = { ["gameTime"] = "", ["gameTime0"] = "", ["dates"] = { ["element"] = "" }, ["timeOfDaySec"] = "", ["tickCount"] = "", ["updateCount"] = "" },
	["Engine.Component.Industry"] = { ["stockList"] = "", ["level"] = "", ["closureTimeStamp"] = "", ["upgradeProgress"] = "", ["manualDevelopment"] = "", ["construction"] = "", ["maxLevel"] = "" },
	["Engine.Component.Line"] = { ["stops"] = { ["element"] = "Engine.Component.Line.Stop" }, ["vehicleInfo"] = "LineVehicleInfo", ["customFilters"] = "", ["reservationPriority"] = "" },
	["Engine.Component.Line.Stop"] = { ["stationGroup"] = "", ["station"] = "", ["terminal"] = "", ["alternativeTerminals"] = { ["element"] = "StationTerminal" }, ["loadMode"] = "", ["minWaitingTime"] = "", ["maxWaitingTime"] = "", ["maxAdditionalWaitingTime"] = "", ["waypoints"] = { ["element"] = "Waypoint" }, ["stopConfig"] = "Engine.Component.Line.StopConfig" },
	["Engine.Component.Line.StopConfig"] = { ["load"] = { ["element"] = "" }, ["maxLoad"] = { ["element"] = "" }, ["forceUnload"] = "", ["destroyForConfigChange"] = "", ["destroyForRefresh"] = "" },
	["Engine.Component.ModelInstanceList"] = { ["fatInstances"] = { ["element"] = "ModelInstance" }, ["thinInstances"] = { ["element"] = "ThinModelInstance" }, ["dynamic"] = "" },
	["Engine.Component.Name"] = { ["name"] = "" },
	["Engine.Component.PersonCapacity"] = { ["type"] = "", ["capacity"] = "", ["personNodes"] = { ["element"] = "NodeId" }, ["vehicleNodes"] = { ["element"] = "NodeId" }, ["pathfindingPreference"] = "Engine.Component.PersonCapacity.PathfindingPreference" },
	["Engine.Component.PersonCapacity.PathfindingPreference"] = { ["destinationWeight"] = "", ["disallowedMoveModes"] = { ["element"] = "" } },
	["Engine.Component.PlayerOwned"] = { ["player"] = "" },
	["Engine.Component.SimCargo"] = { ["cargoType"] = "", ["targetOrPickupEntity"] = "", ["sourceEntity"] = "", ["pickupPoints"] = { ["element"] = "Engine.Component.SimCargo.PickupPoint" }, ["speed"] = "", ["startTime"] = "", ["pickupTime"] = "", ["deliveryExtensionDuration"] = "" },
	["Engine.Component.SimCargo.PickupPoint"] = { ["vehicle"] = "", ["line"] = "", ["position"] = "Vec3f", ["carrier"] = "" },
	["Engine.Component.SimPerson"] = { ["cargoType"] = "", ["destinations"] = { ["element"] = "" }, ["moveModes"] = { ["element"] = "" }, ["travelTimes"] = { ["element"] = "" }, ["targetOrAtEntity"] = "", ["lastNonResType"] = "", ["lastMoveMode"] = "", ["walkSpeed"] = "", ["modelIdPerson"] = "", ["colorConfigPerson"] = "", ["modelIdCar"] = "", ["colorConfigCar"] = "", ["lastDestinationUpdate"] = "", ["landUse2ReachableWalkDrive"] = "", ["landUse2ReachableLines"] = "", ["pickupTime"] = "", ["happiness"] = "" },
	["Engine.Component.StationGroup"] = { ["stations"] = { ["element"] = "" } },
	["Engine.Component.StockList"] = { ["stocks"] = { ["element"] = "Engine.Component.StockList.Stock" }, ["rules"] = { ["element"] = "Engine.Component.StockList.Rule" }, ["stockDatas"] = { ["element"] = "Engine.Component.StockList.StockData" }, ["ruleDatas"] = { ["element"] = "Engine.Component.StockList.RuleData" }, ["cargoData"] = { ["element"] = "Engine.Component.StockList.CargoData" }, ["thrownAwayCargo"] = "", ["modifiers"] = "Engine.Component.StockList.Modifiers" },
	["Engine.Component.StockList.CargoData"] = { ["produceFrequency"] = "" },
	["Engine.Component.StockList.Modifiers"] = { ["productivity"] = "" },
	["Engine.Component.StockList.Rule"] = { ["input"] = { ["element"] = { ["element"] = "" } }, ["output"] = { ["element"] = "" }, ["capacity"] = "", ["consumptionFactor"] = "", ["booster"] = "", ["boostFactor"] = "", ["priority"] = "", ["slot"] = "" },
	["Engine.Component.StockList.RuleData"] = { ["applyHistory"] = { ["element"] = "Engine.Component.StockList.RuleData.ApplyInfo" }, ["lastApplyDecayFactor"] = "" },
	["Engine.Component.StockList.RuleData.ApplyInfo"] = { ["time"] = "", ["interval"] = "", ["consumedCargo"] = { ["element"] = "" }, ["producedCargo"] = { ["element"] = "" } },
	["Engine.Component.StockList.Stock"] = { ["type"] = "", ["cargoType"] = "", ["cargoTypes"] = "CargoTypeSet", ["mixedTypes"] = "", ["capacity"] = "", ["loadSpeedModifier"] = "", ["loadIndicatorModelInstanceIndices"] = { ["element"] = "" }, ["tag"] = "" },
	["Engine.Component.StockList.StockData"] = { ["consumeFrequency"] = "" },
	["Engine.Component.Terrain"] = { ["size"] = "Vec2i", ["baseLevels"] = "", ["baseResolution"] = "Vec3f", ["highLevels"] = "", ["offsetZ"] = "", ["waterLevel"] = "", ["dataMaps"] = "" },
	["Engine.Component.TerrainTile"] = { ["terrainEntity"] = "", ["position"] = "Vec2i" },
	["Engine.Component.TerrainTileBrush"] = { ["materialIndexBrush"] = { ["element"] = "" }, ["forceAboveBit"] = { ["element"] = "" } },
	["Engine.Component.TerrainTileHeightmap"] = { ["vertices"] = { ["element"] = "" } },
	["Engine.Component.Town"] = { ["initialLandUseCapacities"] = { ["element"] = "" }, ["capacityScalingFactor"] = "", ["levelToCapacityDistributionWeights"] = { ["element"] = { ["element"] = "" } }, ["sizeFactors"] = { ["element"] = "" }, ["cargoNeeds"] = { ["element"] = { ["element"] = "" } }, ["developmentActive"] = "", ["noise"] = "", ["pollution"] = "" },
	["Engine.Component.TownBuilding"] = { ["personCapacity"] = "", ["stockList"] = "", ["construction"] = "", ["level"] = "", ["parcels"] = { ["element"] = "" }, ["depth"] = "", ["height"] = "", ["town"] = "", ["timeBuilt"] = "", ["blockedDevelopment"] = "" },
	["Engine.Component.TransportNetwork"] = { ["nodes"] = { ["element"] = "Node" }, ["edges"] = { ["element"] = "Edge" }, ["turnaroundEdges"] = { ["element"] = "" } },
	["Engine.Component.TransportVehicle"] = { ["carrier"] = "", ["transportVehicleConfig"] = "TransportVehicleConfig", ["config"] = "Engine.Component.TransportVehicle.Config", ["state"] = "", ["userStopped"] = "", ["depot"] = "", ["sellOnArrival"] = "", ["line"] = "", ["stopIndex"] = "", ["arrivalStationTerminal"] = "StationTerminal", ["arrivalStationTerminalLocked"] = "", ["lineStopDepartures"] = { ["element"] = "" }, ["lastLineStopDeparture"] = "", ["sectionTimes"] = { ["element"] = "" }, ["lineStop2cargo2available"] = { ["element"] = { ["element"] = "" } }, ["loadState"] = "", ["timeUntilNextScheduledDeparture"] = "", ["loadSpeedModifiers"] = { ["element"] = "Engine.Component.TransportVehicle.LoadSpeedModifiers" }, ["timeUntilCloseDoors"] = "", ["timeUntilDeparture"] = "", ["timeUntilNextLoad"] = { ["element"] = "" }, ["timeUntilNextUnload"] = { ["element"] = "" }, ["lastStationStockIndex"] = "", ["doorsTime"] = "", ["daysInDepot"] = "", ["daysAtTerminal"] = "", ["doorsOpen"] = "", ["noPath"] = "", ["autoDeparture"] = "", ["maintenanceStation"] = "", ["modifiers"] = "Engine.Component.TransportVehicle.Modifiers", ["unloadPendingIncome"] = "Engine.Component.TransportVehicle.PendingIncomeParams", ["closestTown"] = "", ["visitedStops"] = { ["element"] = "" } },
	["Engine.Component.TransportVehicle.Config"] = { ["transportModes"] = { ["element"] = "" }, ["allCaps"] = { ["element"] = "" }, ["capacities"] = { ["element"] = "" }, ["loadSpeeds"] = { ["element"] = "" }, ["reversible"] = "" },
	["Engine.Component.TransportVehicle.LoadSpeedModifiers"] = { ["vehicleOverlength"] = "", ["stockCompatibility"] = "", ["vehicleCompatibility"] = "", ["vehicleIncompatibility"] = "" },
	["Engine.Component.TransportVehicle.Modifiers"] = { ["topSpeedScale"] = "", ["noiseScale"] = "", ["pollutionScale"] = "", ["comfortScale"] = "" },
	["Engine.Component.TransportVehicle.PendingIncomeParams"] = { ["amount"] = "", ["carrier"] = "", ["vehicleEntity"] = "", ["lineEntity"] = "" },
	["Engine.Component.VehicleDepot"] = { ["carrier"] = "", ["transportModes"] = { ["element"] = "" }, ["inNodes"] = { ["element"] = "NodeId" }, ["outNodes"] = { ["element"] = "NodeId" }, ["state"] = "", ["doors"] = "", ["stateTime"] = "", ["catchmentArea"] = "CatchmentArea", ["maintenancePool"] = "", ["maxPoolUsage"] = "", ["averagePoolUsage"] = "", ["poolUsageTicks"] = "", ["filterTags"] = { ["element"] = "" } },
	["Engine.Component.WaterMesh"] = { ["waterLevel"] = "", ["vertices"] = { ["element"] = "Vec2f" }, ["depths"] = { ["element"] = "" }, ["indices"] = { ["element"] = "" }, ["contours"] = { ["element"] = "Engine.Component.WaterMesh.Contour" }, ["pos"] = "Vec2i" },
	["Engine.Component.WaterMesh.Contour"] = { ["vertices"] = { ["element"] = "Vec2f" }, ["normals"] = { ["element"] = "Vec2f" } },
	["LaneConfig"] = { ["speed"] = "", ["width"] = "", ["height"] = "", ["forward"] = "", ["transportModes"] = { ["element"] = "" }, ["offset"] = "" },
	["LineVehicleInfo"] = { ["transportModes"] = { ["element"] = "" } },
	["LoadConfig"] = { ["loadConfigIndex"] = "", ["cargoTypeId"] = "" },
	["Mat4f"] = {  },
	["ModelInstance"] = { ["modelId"] = "", ["transf0"] = "Mat4f", ["transf"] = "Mat4f", ["transformator"] = "" },
	["Node"] = {  },
	["NodeId"] = { ["entity"] = "", ["index"] = "" },
	["Slot"] = { ["autoFill"] = "", ["id"] = "", ["type"] = "", ["transf"] = "Mat4f", ["spacing"] = "Vec4f", ["height"] = "", ["shape"] = "", ["alignToTerrain"] = "", ["replaceable"] = "" },
	["SlotConfig"] = { ["maxModules"] = "", ["message"] = "", ["skipCollisionCheck"] = "" },
	["Station"] = { ["tag"] = "", ["terminals"] = { ["element"] = "Terminal" }, ["catchmentAreas"] = { ["element"] = "CatchmentArea" }, ["pool"] = "Station.Pool" },
	["Station.Pool"] = { ["edges"] = { ["element"] = "EdgeId" }, ["capacity"] = "" },
	["StationTerminal"] = { ["station"] = "", ["terminal"] = "" },
	["Terminal"] = { ["vehicleNodeId"] = "NodeId", ["personNodes"] = { ["element"] = "NodeId" }, ["personEdges"] = { ["element"] = "EdgeId" }, ["vehicleEdges"] = { ["element"] = "EdgePos" }, ["tag"] = "", ["cargoLoad"] = "", ["passengersLoad"] = "", ["cargoUnload"] = "", ["passengersUnload"] = "", ["transportModes"] = { ["element"] = "" }, ["cargoTransferSpeeds"] = { ["element"] = "Terminal.TerminalCargoTransferSpeed" }, ["comfortFactor"] = "", ["capacity"] = "", ["terminalAssignmentWeight"] = "" },
	["Terminal.TerminalCargoTransferSpeed"] = { ["cargoTypeSet"] = "CargoTypeSet", ["loadSpeedModifier"] = "", ["length"] = "" },
	["ThinModelInstance"] = { ["modelId"] = "", ["pos"] = "Vec3f", ["rot"] = "", ["scale"] = "" },
	["TransportVehicleConfig"] = { ["vehicles"] = { ["element"] = "TransportVehiclePart" }, ["vehicleGroups"] = { ["element"] = "" }, ["muFileNames"] = { ["element"] = "" } },
	["TransportVehiclePart"] = { ["part"] = "VehiclePart", ["purchaseTime"] = "", ["maintenanceChange"] = "", ["maintenanceState"] = "", ["autoLoadConfig"] = { ["element"] = "" } },
	["Vec2f"] = { ["x"] = "", ["y"] = "" },
	["Vec2i"] = { ["x"] = "", ["y"] = "" },
	["Vec3f"] = { ["x"] = "", ["y"] = "", ["z"] = "" },
	["Vec4f"] = { ["x"] = "", ["y"] = "", ["z"] = "", ["w"] = "" },
	["VehiclePart"] = { ["modelId"] = "", ["reversed"] = "", ["compartment2loadConfig"] = { ["element"] = "LoadConfig" }, ["color"] = "Vec3f" },
	["Waypoint"] = { ["edgePos"] = "EdgePos", ["pos"] = "Vec3f", ["tag"] = "" },
}
-- END GENERATED COMPONENT SCHEMAS

-- Use the verified plural laneConfigs field. Build 40420 does not expose the
-- documented singular laneConfig alias (see headless_frontage_signature reads).
RECORD_SCHEMAS["Network.BaseEdge"] = {}
for key,hint in pairs(RECORD_SCHEMAS["Engine.Component.BaseEdge"]) do
 if key~="laneConfig" then RECORD_SCHEMAS["Network.BaseEdge"][key]=hint end
end
-- Supplemental native node records used by network identity guards.
RECORD_SCHEMAS["Engine.Component.BaseNodeConfig"] = {
 laneConnections={element="LaneConnection"},crosswalks={element=""},
 trafficLightPreference="",trafficLightConfig="Engine.Component.TrafficLightConfig",
 doubleSlipSwitch="",userModifiedLaneConnections="",userModifiedTrafficLightStates=""
}
RECORD_SCHEMAS["LaneConnection"] = {segment0="",segment1="",lane0="",lane1="",withRoad="",withTram=""}
RECORD_SCHEMAS["Engine.Component.TrafficLightConfig"] = {states={element="Engine.Component.TrafficLightState"},trafficLightType=""}
RECORD_SCHEMAS["Engine.Component.TrafficLightState"] = {lockedLanes={element=""},duration="",minDuration="",canSkip=""}
COMPONENT_RECORDS.BASE_NODE_CONFIG="Engine.Component.BaseNodeConfig"
-- Build 40420 does not expose this documented flag (native nodes 37168/35712,
-- resume7/01). Retain every actual lane/phase/crosswalk field in signatures.
RECORD_SCHEMAS["Network.BaseNodeConfig"]={}
for key,hint in pairs(RECORD_SCHEMAS["Engine.Component.BaseNodeConfig"]) do
 if key~="userModifiedLaneConnections" then RECORD_SCHEMAS["Network.BaseNodeConfig"][key]=hint end
end



local function readField(v, key)
	local ok, value = pcall(function() return v[key] end)
	if ok then return value end
end

-- Convert an arbitrary value (possibly engine userdata) into plain JSON-able data.
local function toPlain(v, depth, fields, hint)
	depth = depth or 0
	local schema = type(hint) == "string" and RECORD_SCHEMAS[hint] or nil
	local elementHint = type(hint) == "table" and hint.element or nil
	if fields == nil and schema and next(schema) ~= nil then
		fields = {}
		for key in pairs(schema) do fields[#fields+1] = key end
		table.sort(fields)
	end
	local tv = type(v)
	if tv == "nil" or tv == "boolean" or tv == "number" or tv == "string" then
		return v
	end
	if depth > 10 then return { _truncated = "max_depth" } end
	if tv == "table" then
		local out = {}
		local count = 0
		for k, val in pairs(v) do
			count = count + 1
			if count > MAX_LIST then out["..."] = "truncated"; break end
			out[k] = toPlain(val, depth + 1, nil, elementHint or (schema and schema[k]))
		end
		return out
	end
	if tv == "userdata" then
		-- Read coordinates independently: Vec2 throws on .z.
		local x, y = readField(v, "x"), readField(v, "y")
		if type(x) == "number" and type(y) == "number" then
			return { x = x, y = y, z = readField(v, "z"), w = readField(v, "w") }
		end
		if fields then
			local out = json.object()
			local missing = {}
			for _, key in ipairs(fields) do
				local value = readField(v, key)
				if value ~= nil then out[key] = toPlain(value, depth + 1, nil, schema and schema[key])
				else missing[#missing + 1] = key end
			end
			if hint == "ModelInstance" or hint == "ThinModelInstance" then
				local okName, name = pcall(function() return api.res.modelRep.getName(out.modelId) end)
				if okName then out.modelName = name end
			end
			if #missing > 0 then out._unavailableFields = missing end
			return out
		end
		local low, high = readField(v, "min"), readField(v, "max")
		if low ~= nil and high ~= nil then
			return { min = toPlain(low, depth + 1), max = toPlain(high, depth + 1) }
		end
		local cols = readField(v, "cols")
		if cols ~= nil then
			local okM, matrix = pcall(function()
				local columns = {}
				-- Runtime Mat4f uses 0..3 despite the API documentation saying 1..4.
				local okZero, zero = pcall(function() return v:cols(0) end)
				local first = okZero and zero ~= nil and 0 or 1
				for i = 0, 3 do
					local column = v:cols(first + i)
					assert(column ~= nil, "matrix column is unavailable")
					columns[i+1] = toPlain(column, depth + 1)
				end
				return { columns = columns }
			end)
			if okM then return matrix end
		end
		-- engine collections are often iterable with pairs
		local okP, res = pcall(function()
			local out = {}
			local count = 0
			for k, val in pairs(v) do
				count = count + 1
				if count > MAX_LIST then out["..."] = "truncated"; break end
				out[k] = toPlain(val, depth + 1, nil, elementHint or (schema and schema[k]))
			end
			return out
		end)
		if okP then return res end
		return { _unavailable = "opaque_userdata", description = tostring(v) }
	end
	return tostring(v)
end

local function collectEntities(ctName, limit)
	local ctype = componentTypes()[ctName]
	if ctype == nil then error("unknown component type " .. ctName, 0) end
	local list = {}
	api.engine.forEachEntityWithComponent(function(entity)
		if #list < limit then list[#list + 1] = entity end
	end, ctype)
	return list
end

local function tryField(fn)
	local ok, v = pcall(fn)
	if ok then return v end
	return nil
end

-- Reverse lookup of an engine enum value, e.g. enumName("Carrier", 1) -> "RAIL".
-- Engine enum tables can't be iterated with pairs, so we probe known member names.
local ENUM_MEMBERS = {
	Carrier = { "ROAD", "RAIL", "TRAM", "AIR", "WATER", "OTHER" },
	TransportVehicleState = { "IN_DEPOT", "EN_ROUTE", "AT_TERMINAL", "GOING_TO_DEPOT" },
	TransportMode = { "PERSON", "CARGO", "CAR", "BUS", "TRUCK", "TRAM", "ELECTRIC_TRAM", "TRAIN",
		"ELECTRIC_TRAIN", "AIRCRAFT", "SHIP", "SMALL_AIRCRAFT", "SMALL_SHIP", "HELICOPTER" },
}

local MODE_TO_CARRIER = {
	CAR = "ROAD", BUS = "ROAD", TRUCK = "ROAD",
	TRAM = "TRAM", ELECTRIC_TRAM = "TRAM",
	TRAIN = "RAIL", ELECTRIC_TRAIN = "RAIL",
	SHIP = "WATER", SMALL_SHIP = "WATER",
	AIRCRAFT = "AIR", SMALL_AIRCRAFT = "AIR", HELICOPTER = "AIR",
}
local enumCache = {}
local function enumName(enumType, value)
	if value == nil then return nil end
	local map = enumCache[enumType]
	if map == nil then
		map = {}
		for _, name in ipairs(ENUM_MEMBERS[enumType] or {}) do
			local ok, v = pcall(function() return api.type.enum[enumType][name] end)
			if ok and v ~= nil then map[#map + 1] = { name, v } end
		end
		enumCache[enumType] = map
	end
	for _, kv in ipairs(map) do
		if kv[2] == value then return kv[1] end
	end
	return tostring(value)
end

local function enumValue(enumType, name)
	local ok, v = pcall(function() return api.type.enum[enumType][name] end)
	if ok then return v end
	return nil
end

local function listOf(v)
	local out = {}
	pcall(function()
		for _, e in pairs(v) do out[#out + 1] = e end
	end)
	return out
end

local function constructionPosition(constructionEntity)
	if constructionEntity == nil or constructionEntity < 0 then return nil end
	local con = getComponent(constructionEntity, "CONSTRUCTION")
	if con == nil then return nil end
	return tryField(function()
		local p = con.transf:getTransl()
		return { x = p.x, y = p.y, z = p.z }
	end)
end

-- Center of an entity's bounding box (works for stations, edge objects, most models).
local function entityPosition(entity)
	local bv = getComponent(entity, "BOUNDING_VOLUME")
	if bv == nil then return nil end
	return tryField(function()
		local lo, hi = bv.bbox.min, bv.bbox.max
		return { x = (lo.x + hi.x) / 2, y = (lo.y + hi.y) / 2, z = (lo.z + hi.z) / 2 }
	end)
end

local function stationGroupPosition(groupEntity)
	local group = getComponent(groupEntity, "STATION_GROUP")
	if group == nil then return nil end
	local sx, sy, sz, n = 0, 0, 0, 0
	for _, station in ipairs(listOf(group.stations)) do
		local pos = entityPosition(station)
		if pos == nil then
			local con = tryField(function()
				return api.engine.system.streetConnectorSystem.getConstructionEntityForStation(station)
			end)
			pos = constructionPosition(con)
		end
		if pos then
			sx, sy, sz, n = sx + pos.x, sy + pos.y, sz + pos.z, n + 1
		end
	end
	if n == 0 then return nil end
	return { x = sx / n, y = sy / n, z = sz / n }
end

local function requireEntity(args, key, componentName)
	local entity = tonumber(args[key])
	if entity == nil then error("missing numeric '" .. key .. "'", 0) end
	if not api.engine.entityExists(entity) then error(key .. " " .. entity .. " does not exist", 0) end
	if componentName and getComponent(entity, componentName) == nil then
		error(key .. " " .. entity .. " is not a " .. componentName, 0)
	end
	return entity
end

local function currentYear()
	local gt = getComponent(api.engine.util.getWorld(), "GAME_TIME")
	return tryField(function() return api.engine.util.getCalendarDate(gt.gameTime).year end)
end

local function modelInfo(modelId)
	local model = api.res.modelRep.get(modelId)
	local md = model.metadata
	local tv = md.transportVehicle
	if tv == nil then return nil end
	local info = {
		id = modelId,
		model = api.res.modelRep.getName(modelId),
		name = tryField(function() return md.description.name end),
		carrier = enumName("Carrier", tv.carrier),
		yearFrom = tryField(function() return md.availability.yearFrom end),
		yearTo = tryField(function() return md.availability.yearTo end),
		price = tryField(function() return md.cost.price end),
		topSpeed = tryField(function()
			local mv = md.landVehicle or md.waterVehicle or md.airVehicle
			return mv and mv.topSpeed
		end),
	}
	local capacity = 0
	pcall(function()
		for _, comp in ipairs(listOf(tv.compartments)) do
			local lc = listOf(comp.loadConfigs)[1]
			if lc then capacity = capacity + (lc.cargoEntry.capacity or 0) end
		end
	end)
	info.capacity = capacity
	return info
end

-- Same as the GUI's vehicle_util.makePart: one model, all compartments on load config 0.
local function makeVehicleConfig(modelId)
	local part = api.type.TransportVehiclePart.new()
	part.part.modelId = modelId
	local tv = api.res.modelRep.get(modelId).metadata.transportVehicle
	local loadConfigs = {}
	for _ in ipairs(listOf(tv.compartments)) do
		local lc = api.type.LoadConfig.new()
		lc.loadConfigIndex = 0
		loadConfigs[#loadConfigs + 1] = lc
	end
	part.part.reversed = false
	part.part.compartment2loadConfig = loadConfigs
	local gt = getComponent(api.engine.util.getWorld(), "GAME_TIME")
	pcall(function() part.purchaseTime = gt.gameTime end)
	pcall(function()
		local auto = {}
		for i = 1, #loadConfigs do auto[i] = true end
		part.autoLoadConfig = auto
	end)
	local config = api.type.TransportVehicleConfig.new()
	config.vehicles = { part }
	config.vehicleGroups = { 1 } -- not a multiple unit
	config.muFileNames = {}
	return config
end

local function resolveModel(ref)
	local id = tonumber(ref)
	if id == nil and type(ref) == "string" then id = api.res.modelRep.find(ref) end
	if id == nil or id < 0 then error("unknown vehicle model: " .. tostring(ref), 0) end
	if tryField(function() return api.res.modelRep.get(id).metadata.transportVehicle end) == nil then
		error("model " .. tostring(ref) .. " is not a transport vehicle", 0)
	end
	return id
end

local function colorFrom(v)
	if type(v) == "table" and #v >= 3 then
		return api.type.Vec3f.new(v[1], v[2], v[3])
	end
	-- random light color by default
	local h = math.random()
	return api.type.Vec3f.new(0.3 + 0.7 * h, 0.3 + 0.7 * (1 - h), 0.5)
end

------------------------------------------------------------------------------
-- commands
------------------------------------------------------------------------------

-- Each handler gets (args, reply). It either returns a result synchronously
-- (reply is ignored), or returns the sentinel ASYNC and calls reply(ok, result|error) later.
local ASYNC = {}

-- In the engine state the callback runs synchronously; `results` is a list of
-- {entity, revision} pairs for entities the command created.
local function sendGameCommand(cmd, reply, resultFn)
	api.cmd.sendCommand(cmd, function(res, success, results)
		if success then
			local ok, out = pcall(function()
				return resultFn and resultFn(res, results) or { success = true }
			end)
			if ok then reply(true, out) else reply(false, "command succeeded but reading its result failed: " .. tostring(out)) end
		else
			reply(false, "game rejected the command")
		end
	end)
	return ASYNC
end

-- Sends several commands and replies once all callbacks have fired.
-- makeCmd(i) builds the i-th command; onResult(i, success, res, results) collects results;
-- finish() returns the reply payload.
local function sendMany(n, makeCmd, onResult, finish, reply)
	local pending = n
	if n == 0 then reply(true, finish()) return ASYNC end
	for i = 1, n do
		local okMake, cmd = pcall(makeCmd, i)
		if not okMake then
			onResult(i, false, nil, nil, tostring(cmd))
			pending = pending - 1
		else
			api.cmd.sendCommand(cmd, function(res, success, results)
				local okR, err = pcall(onResult, i, success, res, results)
				if not okR then log("result handler error:", err) end
				pending = pending - 1
				if pending == 0 then reply(true, finish()) end
			end)
		end
	end
	if pending == 0 then reply(true, finish()) end
	return ASYNC
end

local commands = {}

commands.ping = function(args)
	return {
		pong = true,
		echo = args and args.echo,
		probe = probe,
		userdataFolder = userdataFolder(),
	}
end

commands.get_game_state = function()
	local world = api.engine.util.getWorld()
	local player = api.engine.util.getPlayer()
	local gameTime = getComponent(world, "GAME_TIME")
	local gameSpeed = getComponent(world, "GAME_SPEED")
	local account = getComponent(player, "ACCOUNT")
	local state = {
		world = world,
		player = player,
		gameTime = tryField(function() return gameTime.gameTime end),
		timeOfDaySec = tryField(function() return gameTime.timeOfDaySec end),
		tickCount = tryField(function() return gameTime.tickCount end),
		speedup = tryField(function() return gameSpeed.speedup end),
		millisPerDay = tryField(function() return gameSpeed.millisPerDay end),
		balance = tryField(function() return api.engine.util.finance.getPlayersBalance(player) end),
		accountBalance = tryField(function() return account.balance end),
		loan = tryField(function() return account.loan end),
	}
	if state.gameTime ~= nil then
		local date = tryField(function() return api.engine.util.getCalendarDate(state.gameTime) end)
		if date ~= nil then
			state.date = {
				year = tryField(function() return date.year end),
				month = tryField(function() return date.month end),
				day = tryField(function() return date.day end),
			}
		end
	end
	return state
end

commands.list_towns = function(args)
	local limit = (args and tonumber(args.limit)) or 500
	local towns = {}
	for _, entity in ipairs(collectEntities("TOWN", limit)) do
		towns[#towns + 1] = { id = entity, name = entityName(entity) }
	end
	return { count = #towns, towns = towns }
end

local function ownerOf(entity)
	local po = getComponent(entity, "PLAYER_OWNED")
	return po and tryField(function() return po.player end) or nil
end

-- Entities with the component, optionally only those owned by the local player.
local function ownedEntities(ctName, args)
	local limit = tonumber(args.limit) or 500
	local mineOnly = args.mine_only ~= false
	local player = api.engine.util.getPlayer()
	local out = {}
	for _, e in ipairs(collectEntities(ctName, MAX_LIST)) do
		if #out >= limit then break end
		if not mineOnly or ownerOf(e) == player then out[#out + 1] = e end
	end
	return out
end

local function lineStops(lineComp)
	local stops = {}
	for i, stop in ipairs(listOf(lineComp.stops)) do
		stops[i] = {
			stationGroup = tryField(function() return stop.stationGroup end),
			station = tryField(function() return stop.station end),
			terminal = tryField(function() return stop.terminal end),
			name = entityName(tryField(function() return stop.stationGroup end) or -1),
		}
	end
	return stops
end

local function lineEntities(args)
	local limit = tonumber(args.limit) or 500
	local sys = api.engine.system.lineSystem
	local all
	if args.mine_only ~= false then
		all = listOf(sys.getLinesForPlayer(api.engine.util.getPlayer()))
	else
		all = listOf(sys.getLines())
	end
	local out = {}
	for i = 1, math.min(limit, #all) do out[i] = all[i] end
	return out
end

commands.list_lines = function(args)
	local lines = {}
	for _, entity in ipairs(lineEntities(args)) do
		local comp = getComponent(entity, "LINE")
		local vehicles = tryField(function()
			return listOf(api.engine.system.transportVehicleSystem.getLineVehicles(entity))
		end) or {}
		lines[#lines + 1] = {
			id = entity,
			name = entityName(entity),
			stops = comp and lineStops(comp) or {},
			vehicleCount = #vehicles,
			vehicles = vehicles,
		}
	end
	return { count = #lines, lines = lines }
end

commands.list_stations = function(args)
	local stations = {}
	for _, entity in ipairs(ownedEntities("STATION_GROUP", args)) do
		local group = getComponent(entity, "STATION_GROUP")
		stations[#stations + 1] = {
			id = entity,
			name = entityName(entity),
			stations = group and listOf(group.stations) or {},
			position = stationGroupPosition(entity),
		}
	end
	return { count = #stations, stationGroups = stations }
end

commands.list_depots = function(args)
	local depots = {}
	for _, entity in ipairs(ownedEntities("VEHICLE_DEPOT", args)) do
		local depot = getComponent(entity, "VEHICLE_DEPOT")
		local con = tryField(function()
			return api.engine.system.streetConnectorSystem.getConstructionEntityForDepot(entity)
		end)
		local modes = {}
		pcall(function()
			for mode, enabled in pairs(depot.transportModes) do
				if enabled then modes[#modes + 1] = enumName("TransportMode", mode) end
			end
		end)
		table.sort(modes)
		local carrier = depot and tryField(function() return enumName("Carrier", depot.carrier) end)
		for _, m in ipairs(modes) do carrier = carrier or MODE_TO_CARRIER[m] end
		depots[#depots + 1] = {
			id = entity,
			name = entityName(entity) or entityName(con or -1),
			carrier = carrier,
			transportModes = modes,
			construction = con,
			maintenancePool = tryField(function() return depot.maintenancePool end),
			maintenanceCatchment = tryField(function() local a=depot.catchmentArea; return {radius=a.radius,position={x=a.position.x,y=a.position.y,z=a.position.z}} end),
			position = constructionPosition(con) or entityPosition(entity),
			vehiclesInDepot = tryField(function()
				return listOf(api.engine.system.transportVehicleSystem.getDepotVehicles(entity))
			end),
		}
	end
	return { count = #depots, depots = depots }
end

local function vehicleSummary(entity)
	local tv = getComponent(entity, "TRANSPORT_VEHICLE")
	if tv == nil then return { id = entity, error = "not a transport vehicle" } end
	return {
		id = entity,
		name = entityName(entity),
		carrier = enumName("Carrier", tryField(function() return tv.carrier end)),
		state = enumName("TransportVehicleState", tryField(function() return tv.state end)),
		line = tryField(function() return tv.line end),
		stopIndex = tryField(function() return tv.stopIndex end),
		depot = tryField(function() return tv.depot end),
		userStopped = tryField(function() return tv.userStopped end),
		noPath = tryField(function() return tv.noPath end),
		daysInDepot = tryField(function() return tv.daysInDepot end),
	}
end

commands.list_vehicles = function(args)
	local entities
	if args.line ~= nil then
		local line = requireEntity(args, "line", "LINE")
		entities = listOf(api.engine.system.transportVehicleSystem.getLineVehicles(line))
	else
		entities = ownedEntities("TRANSPORT_VEHICLE", args)
	end
	local vehicles = {}
	for _, e in ipairs(entities) do vehicles[#vehicles + 1] = vehicleSummary(e) end
	return { count = #vehicles, vehicles = vehicles }
end

commands.list_vehicle_models = function(args)
	local year = tonumber(args.year) or currentYear()
	local carrier = args.carrier and string.upper(args.carrier) or nil
	local limit = tonumber(args.limit) or 200
	local models = {}
	api.res.modelRep.forEachModelWithMetadata("transportVehicle", function(resName)
		local info = tryField(function() return modelInfo(api.res.modelRep.find(resName)) end)
		if info == nil or resName:find("/placeholders/", 1, true) then return end
		if carrier and info.carrier ~= carrier then return end
		if year and not args.include_unavailable then
			if (info.yearFrom or 0) > year then return end
			if (info.yearTo or 0) ~= 0 and info.yearTo < year then return end
		end
		models[#models + 1] = info
	end)
	-- newest first, then truncate, so `limit` keeps the most modern models
	table.sort(models, function(a, b) return (a.yearFrom or 0) > (b.yearFrom or 0) end)
	local total = #models
	for i = total, limit + 1, -1 do models[i] = nil end
	return { year = year, total = total, count = #models, models = models }
end

commands.create_line = function(args, reply)
	local groups = args.station_groups
	if type(groups) ~= "table" or #groups < 2 then
		error("'station_groups' must list at least 2 station group ids, in stop order", 0)
	end
	local line = api.type.Line.new()
	local stops = {}
	for i, g in ipairs(groups) do
		local group = tonumber(g)
		if group == nil or getComponent(group, "STATION_GROUP") == nil then
			error("stop " .. i .. ": " .. tostring(g) .. " is not a station group", 0)
		end
		local stop = api.type.Line.Stop.new()
		stop.stationGroup = group
		stop.station = 0
		stop.terminal = 0
		-- The GUI initializes these vectors; Line.Stop.new() leaves them empty.
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
		stops[#stops + 1] = stop
	end
	line.stops = stops
	line.customFilters = true
	local name = type(args.name) == "string" and args.name or "Line"
	local cmd = api.cmd.makeLineCreateCmd(name, colorFrom(args.color), api.engine.util.getPlayer(), line)
	return sendGameCommand(cmd, reply, function(_, results)
		local lineEntity = tryField(function() return results[1][1] end)
		return { line = lineEntity, name = name, stops = #stops }
	end)
end

commands.delete_line = function(args, reply)
	local line = requireEntity(args, "line", "LINE")
	return sendGameCommand(api.cmd.makeLineDestroyCmd(line), reply, function()
		return { deleted = line }
	end)
end

commands.buy_vehicles = function(args, reply)
	local depot = requireEntity(args, "depot", "VEHICLE_DEPOT")
	local modelId = resolveModel(args.model)
	local count = math.max(1, math.min(50, math.floor(tonumber(args.count) or 1)))
	local line = args.line ~= nil and requireEntity(args, "line", "LINE") or nil
	local bought, failures = {}, {}
	local player = api.engine.util.getPlayer()

	local function assign(vehicle)
		if line == nil or vehicle == nil then return end
		api.cmd.sendCommand(api.cmd.makeVehicleSetLineCmd(vehicle, line, 0), function(_, ok)
			if not ok then failures[#failures + 1] = "vehicle " .. vehicle .. " bought but could not be assigned to line" end
		end)
	end

	return sendMany(count,
		function() return api.cmd.makeVehicleBuyCmd(player, depot, makeVehicleConfig(modelId)) end,
		function(i, success, res, _, err)
			if not success then
				failures[#failures + 1] = err or ("purchase " .. i .. " rejected (not enough money, or model incompatible with depot?)")
				return
			end
			local vehicle = tryField(function() return res.resultVehicleEntity end)
			bought[#bought + 1] = vehicle
			assign(vehicle)
		end,
		function()
			return { bought = bought, failures = failures, model = api.res.modelRep.getName(modelId), line = line }
		end,
		reply)
end

commands.assign_vehicles = function(args, reply)
	local line = requireEntity(args, "line", "LINE")
	local vehicles = args.vehicles
	if type(vehicles) ~= "table" or #vehicles == 0 then error("'vehicles' must be a non-empty list of ids", 0) end
	local stopIndex = math.floor(tonumber(args.stop_index) or 0)
	local assigned, failures = {}, {}
	return sendMany(#vehicles,
		function(i) return api.cmd.makeVehicleSetLineCmd(tonumber(vehicles[i]), line, stopIndex) end,
		function(i, success, _, _, err)
			if success then assigned[#assigned + 1] = vehicles[i]
			else failures[#failures + 1] = err or ("vehicle " .. tostring(vehicles[i]) .. " rejected") end
		end,
		function() return { line = line, assigned = assigned, failures = failures } end,
		reply)
end

commands.sell_vehicles = function(args, reply)
	local vehicles = args.vehicles
	if type(vehicles) ~= "table" or #vehicles == 0 then error("'vehicles' must be a non-empty list of ids", 0) end
	local ids = {}
	for i, v in ipairs(vehicles) do ids[i] = tonumber(v) end
	return sendGameCommand(api.cmd.makeVehicleSellCmd(ids), reply, function()
		return { sold = ids }
	end)
end

commands.send_to_depot = function(args, reply)
	local vehicle = requireEntity(args, "vehicle", "TRANSPORT_VEHICLE")
	local sell = args.sell_on_arrival == true
	return sendGameCommand(api.cmd.makeVehicleSendToDepotCmd(vehicle, sell), reply, function()
		return { vehicle = vehicle, sellOnArrival = sell }
	end)
end

commands.set_vehicle_stopped = function(args, reply)
	local vehicle = requireEntity(args, "vehicle", "TRANSPORT_VEHICLE")
	local stopped = args.stopped ~= false
	return sendGameCommand(api.cmd.makeVehicleSetStoppedByUserCmd(vehicle, stopped), reply, function()
		return { vehicle = vehicle, stopped = stopped }
	end)
end

-- Bounded scalar motion diagnostics; never computes a path or sends a command.
commands.get_vehicle_motion = function(args)
 local vehicle=requireEntity(args,"vehicle","TRANSPORT_VEHICLE")
 local function scalars(value,keys)
  local out=json.object()
  if value then for _,key in ipairs(keys) do
   local v=readField(value,key)
   if type(v)=="number" or type(v)=="boolean" or type(v)=="string" then out[key]=v end
  end end
  return out
 end
 local ground=getComponent(vehicle,"MOVE_PATH")
 local air=getComponent(vehicle,"MOVE_PATH_AIRCRAFT")
 local result={vehicle=vehicle,groundAvailable=ground~=nil,aircraftAvailable=air~=nil}
 -- Position is read only for a vehicle with a live motion component. In-depot
 -- vehicles have none; do not call native position helpers for those entities.
 if ground or air then
  local pos=api.engine.util.vehicle.getPosition(vehicle)
  result.position=scalars(pos,{"x","y","z"})
 end
 local function pathSnapshot(path,pathPos)
  local out={position=scalars(pathPos,{"edgeIndex","pos","pos01"})}
  if not path then return out end
  local edges=readField(path,"edges")
  if not edges then return out end
  local count=#edges;out.edgeCount=count
  out.endOffset=readField(path,"endOffset")
  out.terminalDecisionOffset=readField(path,"terminalDecisionOffset")
  local index=pathPos and readField(pathPos,"edgeIndex")
  if type(index)~="number" or index%1~=0 or index<0 or index>=count then
   out.currentEdgeAvailable=false;return out
  end
  out.currentEdgeAvailable=true;out.samples={}
  local seen={}
  for _,i in ipairs({index,math.min(index+1,count-1),count-1}) do
   if not seen[i] then
    seen[i]=true
    -- PathPos.edgeIndex is zero-based; the native Lua sequence is one-based.
    local item=edges[i+1]
    -- Native tuple slots may be zero-based even though the surrounding vector
    -- is one-based. Validate the edge/direction pair instead of guessing IDs.
    local edge,forward,tupleBase
    for _,layout in ipairs({{0,1,0},{1,2,1},{"first","second","named"},{"edgeId","dir","edgeId_dir"}}) do
     local candidate=readField(item,layout[1]);local direction=readField(item,layout[2])
     local entity=candidate and readField(candidate,"entity")
     local lane=candidate and readField(candidate,"index")
     if type(entity)=="number" and entity%1==0 and entity>=0 and
      type(lane)=="number" and lane%1==0 and lane>=0 and type(direction)=="boolean" then
      edge=candidate;forward=direction;tupleBase=layout[3];break
     end
    end
    -- Native Path vectors can return opaque pairs without Lua tuple access.
    -- Resolve only on explicit opt-in through documented transport ports, then
    -- cross-check BOTH ports against the same current network edge. No search.
    local portEvidence
    if not edge and args.resolve_native_path==true then
     local transport=api.engine.util.transport
     assert(transport and transport.getStartPort and transport.getEndPort,"Native transport port API unavailable")
     local a,b=transport.getStartPort(item),transport.getEndPort(item)
     -- Current native builds may expose packed numeric ports despite the
     -- shipped PortId record declaration. Preserve that evidence, but never
     -- guess bit layouts or pass the scalar into node/edge native APIs.
     local function recordPort(p)return type(p)=="table" or type(p)=="userdata" end
     if not recordPort(a) or not recordPort(b) then
      local function summary(p)
       local v={type=type(p)}
       if type(p)=="number" and p==p and p~=math.huge and p~=-math.huge then v.value=p end
       return v
      end
      portEvidence={start=summary(a),finish=summary(b),nativePathQueries=0,
       status="unsupported_native_port_representation"}
     else
     local function validPort(p)
      assert(recordPort(p) and p.nodeId and type(p.nodeId.entity)=="number" and p.nodeId.entity>=0
       and p.nodeId.entity%1==0 and type(p.nodeId.index)=="number" and p.nodeId.index>=0
       and p.nodeId.index%1==0 and type(p.port)=="number" and p.port>=0 and p.port%1==0,"Invalid native path port")
      assert(api.engine.entityExists(p.nodeId.entity),"Native path port entity removed")
     end
     validPort(a);validPort(b)
     local data=api.engine.system.transportNetworkSystem.getTpNetData()
     local function portEdge(p)
      local node=data:getNodeData(p.nodeId)
      assert(node and node.ports and p.port<#node.ports,"Native path port index outside node")
      local e=node.ports[p.port+1].edgeId
      assert(e and type(e.entity)=="number" and e.entity>=0 and e.entity%1==0
       and type(e.index)=="number" and e.index>=0 and e.index%1==0,"Invalid native path edge")
      return e
     end
     local ea,eb=portEdge(a),portEdge(b)
     assert(ea.entity==eb.entity and ea.index==eb.index,"Native path endpoint edges disagree")
     local net=assert(getComponent(ea.entity,"TRANSPORT_NETWORK"),"Native path edge network removed")
     assert(ea.index<#net.edges,"Native path edge index outside network")
     local ports=data:getEdgeData(ea).ports
     assert(ports and #ports==2,"Native path edge must have two ports")
     local function same(p,q)return p.nodeId.entity==q.nodeId.entity and p.nodeId.index==q.nodeId.index and p.port==q.port end
     validPort(ports[1]);validPort(ports[2]);assert(not same(ports[1],ports[2]),"Ambiguous native path edge ports")
     if same(a,ports[1]) and same(b,ports[2]) then forward=true
     elseif same(a,ports[2]) and same(b,ports[1]) then forward=false
     else error("Native path direction disagrees with edge ports",0) end
     edge=ea;tupleBase="native_ports"
     portEvidence={start={node=scalars(a.nodeId,{"entity","index"}),port=a.port},
      finish={node=scalars(b.nodeId,{"entity","index"}),port=b.port},nativePathQueries=0}
     end
    end
    local sample={pathIndex=i,available=edge~=nil,portEvidence=portEvidence}
    if edge then
     sample.edge=scalars(edge,{"entity","index"});sample.forward=forward;sample.tupleBase=tupleBase
     sample.entityExists=api.engine.entityExists(edge.entity)
     local be=sample.entityExists and getComponent(edge.entity,"BASE_EDGE")
     if be then sample.baseEdge=scalars(be,{"node0","node1","roadType"}) end
     local net=sample.entityExists and getComponent(edge.entity,"TRANSPORT_NETWORK")
     if net and edge.index<#net.edges then
      local lane=net.edges[edge.index+1]
      local conns=readField(lane,"conns")
      if conns then sample.connections={scalars(conns[1],{"entity","index"}),scalars(conns[2],{"entity","index"})} end
     end
    else
     out.currentEdgeAvailable=false;sample.reason=portEvidence and portEvidence.status or "Unrecognized native edge/direction tuple"
     sample.tupleType=type(item);sample.slots={}
     for _,key in ipairs({0,1,2,"entity","index","first","second","edgeId","dir"}) do
      local value=readField(item,key);local row={key=tostring(key),type=type(value)}
      if type(value)=="number" or type(value)=="boolean" then row.value=value end
      sample.slots[#sample.slots+1]=row
     end
    end
    out.samples[#out.samples+1]=sample
   end
  end
  return out
 end
 if ground then
  result.ground=scalars(ground,{"state","blocked","reverse","endPos","servedFrom","servedTo"})
  local dyn=readField(ground,"dyn")
  result.ground.dyn=scalars(dyn,{"speed","accel","timeStanding","timeUntilAccel","approachingStation"})
  result.ground.path=pathSnapshot(readField(ground,"path"),dyn and readField(dyn,"pathPos"))
 end
 if air then
  result.aircraft=scalars(air,{"state","pathState","speed","speed0","brakeDecel"})
  result.aircraft.flight=scalars(readField(air,"aircraftState"),{"flightState","cruiseAlt","waitingDistance","waitingPriority","gear"})
  result.aircraft.ship=scalars(readField(air,"shipState"),{"waitingDist","clearToLand"})
  result.aircraft.pathPosition=scalars(readField(air,"pathPos"),{"edgeIndex","pos","pos01"})
 end
 return result
end

commands.get_finances = function()
	local player = api.engine.util.getPlayer()
	local account = getComponent(player, "ACCOUNT")
	return {
		balance = tryField(function() return api.engine.util.finance.getPlayersBalance(player) end),
		loan = tryField(function() return account.loan end),
		infiniteMoney = tryField(function() return api.engine.util.finance.getPlayersBalance(player) == nil end),
	}
end

commands.get_entity = function(args)
	local entity = tonumber(args and args.id)
	if entity == nil then error("missing numeric 'id'", 0) end
	if not api.engine.entityExists(entity) then error("entity does not exist: " .. entity, 0) end
	local components = json.object()
	local wanted = args.components
	if type(wanted) ~= "table" then
		wanted = { "NAME", "TOWN", "LINE", "STATION", "STATION_GROUP", "INDUSTRY", "TRANSPORT_VEHICLE",
			"CONSTRUCTION", "PLAYER_OWNED", "ACCOUNT", "VEHICLE_DEPOT", "BASE_NODE", "BASE_EDGE", "BASE_NODE_CONFIG" }
	end
	for _, ctName in ipairs(wanted) do
		local comp = getComponent(entity, ctName)
		if comp ~= nil then components[ctName] = toPlain(comp, 0, COMPONENT_FIELDS[ctName], COMPONENT_RECORDS[ctName]) end
	end
	return { id = entity, name = entityName(entity), components = components }
end

-- Whole-map queries use explicit pagination, independently of MAX_LIST.
local function pageInteger(value, default, minimum, maximum, name)
	if value == nil then return default end
	local n = tonumber(value)
	if not n or n ~= math.floor(n) or n < minimum or n > maximum then
		error(name .. " must be an integer between " .. minimum .. " and " .. maximum, 0)
	end
	return n
end

-- Bounded, ephemeral ID snapshots; component values remain live.
local mapSnapshots = {}
local mapSnapshotSerial = 0
local mapSnapshotSession = tostring({})
local MAP_SNAPSHOT_TTL = 300

commands.release_map_snapshot = function(args)
	local token=args.snapshot
	if type(token) ~= "string" then error("snapshot is required",0) end
	local existed=mapSnapshots[token]~=nil
	mapSnapshots[token]=nil
	return {released=existed}
end

commands.list_map_entities = function(args)
	local kind = args.kind or "CONSTRUCTION"
	local supported = { TOWN=true, INDUSTRY=true, CONSTRUCTION=true, TOWN_BUILDING=true,
		BASE_NODE=true, BASE_EDGE=true, STATION=true, STATION_GROUP=true, VEHICLE_DEPOT=true,
		TRANSPORT_VEHICLE=true, SIM_PERSON=true, LINE=true, WATER_MESH=true, MODEL_INSTANCE_LIST=true, ASSET_GROUP=true, SIM_CARGO=true, STOCK_LIST=true, TERRAIN_TILE_BRUSH=true }
	if not supported[kind] then error("unsupported map entity kind: " .. tostring(kind), 0) end
	local offset = pageInteger(args.offset, 0, 0, 2147483647, "offset")
	local limit = pageInteger(args.limit, 100, 1, 500, "limit")
	local token = args.snapshot
	if token ~= nil and type(token) ~= "string" then error("snapshot must be a string",0) end
	local now = wallClock() or 0
	for key, entry in pairs(mapSnapshots) do
		if now-entry.created > MAP_SNAPSHOT_TTL then mapSnapshots[key]=nil end
	end
	local cached = token and token ~= "new" and mapSnapshots[token] or nil
	if token and token ~= "new" and not cached then error("snapshot expired or unknown; start a new traversal",0) end
	if cached and cached.kind ~= kind then error("snapshot kind does not match",0) end
	if token == "new" and offset ~= 0 then error("a new snapshot must start at offset 0",0) end
	local ids, seen = cached and cached.ids or {}, {}
	local function add(id)
		if not seen[id] then seen[id] = true; ids[#ids+1] = id end
	end
	if not cached then
	if kind == "BASE_NODE" or kind == "BASE_EDGE" then
		for node, segments in pairs(api.engine.system.streetSystem.getNode2SegmentMap()) do
			if kind == "BASE_NODE" then add(node)
			else for _, edge in pairs(segments) do add(edge) end end
		end
	elseif kind == "WATER_MESH" then
		local b = api.engine.terrain.getBoundingBox()
		local low = api.type.Vec2i.new(math.floor(b.min.x/256), math.floor(b.min.y/256))
		local high = api.type.Vec2i.new(math.ceil(b.max.x/256)-1, math.ceil(b.max.y/256)-1)
		for _, id in pairs(api.engine.system.riverSystem.getWaterMeshEntities(low, high)) do add(id) end
	elseif kind == "MODEL_INSTANCE_LIST" then
		local b = api.engine.terrain.getBoundingBox()
		local center = api.type.Vec2f.new((b.min.x+b.max.x)/2, (b.min.y+b.max.y)/2)
		local radius = math.sqrt((b.max.x-b.min.x)^2+(b.max.y-b.min.y)^2)/2+1
		for _, id in pairs(api.engine.util.octree.findEntitiesInCircle(center, radius, componentTypes()[kind])) do add(id) end
	elseif kind == "ASSET_GROUP" or kind == "SIM_CARGO" or kind == "STOCK_LIST" or kind == "TERRAIN_TILE_BRUSH" then
		-- These component types reject forEachEntityWithComponent; the complete
		-- entity index still allows reading their components individually.
		api.engine.forEachEntity(function(id)
			if api.engine.getComponent(id, componentTypes()[kind]) ~= nil then add(id) end
		end)
	elseif kind == "LINE" then
		for _, id in pairs(api.engine.system.lineSystem.getLines()) do add(id) end
	else
		api.engine.forEachEntityWithComponent(add, componentTypes()[kind])
	end
	table.sort(ids)
	end
	if token == "new" then
		if #ids > 250000 then error("snapshot exceeds 250000 entities; use live pagination",0) end
		local count, oldestKey, oldest = 0,nil,math.huge
		for key, entry in pairs(mapSnapshots) do
			count=count+1
			if entry.serial < oldest then oldestKey,oldest=key,entry.serial end
		end
		if count >= 4 then mapSnapshots[oldestKey]=nil end
		mapSnapshotSerial=mapSnapshotSerial+1
		token=mapSnapshotSession .. ":" .. mapSnapshotSerial
		cached={kind=kind,ids=ids,created=now,serial=mapSnapshotSerial}
		mapSnapshots[token]=cached
	end
	local items = {}
	for i = offset + 1, math.min(#ids, offset + limit) do
		if cached and (not api.engine.entityExists(ids[i]) or getComponent(ids[i],kind) == nil) then
			items[#items+1]={id=ids[i],missing=true}
		elseif args.ids_only == true then
			items[#items+1]={id=ids[i]}
		elseif kind == "MODEL_INSTANCE_LIST" or kind == "ASSET_GROUP" then
			local comp = getComponent(ids[i], "MODEL_INSTANCE_LIST")
			items[#items+1] = {id=ids[i], fatCount=comp and #comp.fatInstances or 0, thinCount=comp and #comp.thinInstances or 0, dynamic=comp and comp.dynamic}
		else
			items[#items+1] = commands.get_entity({id=ids[i], components={kind, "NAME"}})
		end
	end
	local hasMore = offset + #items < #ids
	return {kind=kind, total=#ids, offset=offset, limit=limit, items=items,
		hasMore=hasMore, nextOffset=hasMore and (offset + #items) or nil,
		snapshot=token, snapshotExpiresInSeconds=cached and math.max(0,MAP_SNAPSHOT_TTL-(now-cached.created)) or nil,
		consistency=cached and "fixed entity ids; fields are live; deleted entries marked missing" or "live; entity changes between pages can shift offsets"}
end

-- Bounded read-only industry bonus view. Never calls RNG-mutating potential-boost helper.
do
 local function read(id,name)
  local ct=componentTypes()[name]
  if ct==nil then return nil end
  return api.engine.getComponent(id,ct)
 end
 commands.get_industry_bonuses=function(args)
  local id=args.industry
  assert(type(id)=='number' and id>=0 and id%1==0 and api.engine.entityExists(id),'industry entity unavailable')
  local ind=assert(read(id,'INDUSTRY'),'entity is not an industry; use current industry ID')
  local stock=assert(read(ind.stockList,'STOCK_LIST'),'industry stock list unavailable')
  local con=assert(read(ind.construction,'CONSTRUCTION'),'industry construction unavailable')
  local gameTime=read(api.engine.util.getWorld(),'GAME_TIME').gameTime
  local capacity=read(id,'PERSON_CAPACITY')
  local w={available=capacity~=nil,deliveryTarget=id,deliveryKind='industry_internal_passenger_transfer',
   arrivalRequirement='citizens arriving at this industry via transport lines; not seats, nearby-stop unloads or stored cargo',
   observationAvailable=false,potentialMultiplierAvailable=false}
  local util=ug_require('::/industries/industry_productivity_util.tl')
  if capacity then
   w.capacity=capacity.capacity;w.requiredFraction=util.RequiredWorkersFractionForBoost
   w.requiredVisitors=math.max(1,math.ceil(capacity.capacity*w.requiredFraction))
   w.windowGameTime=util.workersTimeIntervalMax
   w.currentMultiplier=stock.modifiers and stock.modifiers.productivity
   if type(w.currentMultiplier)=='number' then w.active=w.currentMultiplier>1 end
   local sid=api.engine.system.gameScriptSystem.getEntityForGameScript('::/industries/industry_workers.gs')
   local script=sid and sid>=0 and read(sid,'GAME_SCRIPT') or nil
   if script and script.state_native then
    local entry=script.state_native:findPath({'industriesState',id})
    local state=entry and entry:asTable() or nil
    local visitors=state and state.lastVisitors or {}
    w.observationAvailable=true;w.recordedVisitors=#visitors;w.pendingVisitors=state and state.pendingVisitors and #state.pendingVisitors or 0
    w.inWindowVisitors=0
    for _,v in ipairs(visitors)do
     assert(type(v.time)=='number','invalid native worker visitor time')
     if v.time>=gameTime-w.windowGameTime then w.inWindowVisitors=w.inWindowVisitors+1 end
    end
    w.thresholdMet=w.recordedVisitors>=w.requiredVisitors
    w.countScope='native lastVisitors used by worker script; expiry/pending may await native update'
   else w.observationUnavailableReason='native worker game-script state unavailable; count is unknown' end
   local md=con.persistentMetadata
   local potential=md and md.workersBoostFactor
   if type(potential)=='number' then w.potentialMultiplier=potential;w.potentialMultiplierAvailable=true;w.potentialSource='construction persistentMetadata.workersBoostFactor'
   elseif w.active then w.potentialMultiplier=w.currentMultiplier;w.potentialMultiplierAvailable=true;w.potentialSource='currently applied worker multiplier'
   else w.potentialUnavailableReason='not stored in metadata; seeded native fallback mutates RNG and is not called by this read-only endpoint' end
  end
  local cargo={};local stocks=stock.stocks
  assert(#stock.rules<=32,'too many production rules for bounded bonus query')
  for ruleIndex,rule in ipairs(stock.rules)do
   if rule.booster then
    local inputs={};assert(#rule.input<=16,'too many input alternatives')
    for alternative,vector in ipairs(rule.input)do
     local items={}
     for stockIndex,quantity in pairs(vector)do
      if quantity>0 then
       local st=assert(stocks[stockIndex],'booster input stock index unavailable')
       local ct=st.cargoType;local resource=api.res.cargoTypeRep.getName(ct)
       local data=api.res.cargoTypeRep.get(ct)
       items[#items+1]={stockIndex=stockIndex,cargo=ct,resource=resource,name=data and data.name,
        quantity=quantity,stockCapacity=st.capacity}
      end
     end
     table.sort(items,function(a,b)return a.stockIndex<b.stockIndex end)
     inputs[#inputs+1]={alternative=alternative,items=items}
    end
    local rd=stock.ruleDatas and stock.ruleDatas[ruleIndex]
    cargo[#cargo+1]={ruleIndex=ruleIndex,booster=true,boostFactor=rule.boostFactor,capacity=rule.capacity,
     consumptionFactor=rule.consumptionFactor,inputAlternatives=inputs,deliveryTarget=id,stockList=ind.stockList,
     deliveryKind='industry_internal_cargo_transfer',activeKnown=false,
     lastApplyDecayFactor=rd and rd.lastApplyDecayFactor,
     scope='native rule configuration; quantity is per rule, not annual demand; activation not inferred from configuration'}
   end
  end
  local stops={};local seen={}
  local function station(sid)
   if seen[sid] then return end;seen[sid]=true
   local st=read(sid,'STATION');if not st then return end
   assert(#st.terminals<=32,'too many industry terminals')
   local ts={}
   for index,t in ipairs(st.terminals)do
    ts[#ts+1]={nativeCollectionIndex=index,tag=t.tag,passengersLoad=t.passengersLoad,passengersUnload=t.passengersUnload,
     cargoLoad=t.cargoLoad,cargoUnload=t.cargoUnload,transportModes=toPlain(t.transportModes),vehicleNodeId=toPlain(t.vehicleNodeId,0,nil,"NodeId")}
   end
   stops[#stops+1]={station=sid,terminals=ts}
  end
  station(id)
  assert(#con.stations<=32,'too many industry stations')
  for _,sid in ipairs(con.stations)do station(sid)end
  return {industry=id,construction=ind.construction,stockList=ind.stockList,resource=con.fileName,
   gameTime=gameTime,workers=w,cargoBonuses=cargo,transfer={targetEntity=id,stations=stops,
    stationResolved=#stops>0,scope='industry internal transfer target; select actual compatible terminal before routing; nearby warehouse is not automatic delivery'},
   readOnly=true,industryBonusesVersion=1}
 end
end

commands.get_map_info = function()
	local bounds = api.engine.terrain.getBoundingBox()
	-- Without a heightmap, makeMapFromGame leaves tile sizes at zero: use bounds instead.
	local map = api.engine.terrain.makeMapFromGame(false, true, true, false)
	local towns, industries = {}, {}
	for _, town in pairs(map.towns) do
		towns[#towns+1] = {id=town.existing, name=town.name, position=toPlain(town.pos)}
	end
	for _, industry in pairs(map.industries) do
		industries[#industries+1] = {id=industry.existing, fileName=industry.fileName, position=toPlain(industry.pos)}
	end
	return {bounds=toPlain(bounds), width=bounds.max.x-bounds.min.x,
		height=bounds.max.y-bounds.min.y, baseResolution=toPlain(api.engine.terrain.getBaseResolution()),
		highResolution=toPlain(api.engine.terrain.getHighResolution()), climateId=map.climateId,
		towns=towns, industries=industries}
end

-- Coordinates are sampled in row-major order. A bounded page can cover the whole
-- map at a chosen spacing; rows/columns can also describe a smaller rectangle.
commands.get_terrain_grid = function(args)
	local function finite(value, name)
		local n = tonumber(value)
		if not n or n ~= n or n == math.huge or n == -math.huge then error(name .. " must be finite", 0) end
		return n
	end
	local bounds = api.engine.terrain.getBoundingBox()
	local x = args.x == nil and bounds.min.x or finite(args.x, "x")
	local y = args.y == nil and bounds.min.y or finite(args.y, "y")
	local spacing = args.spacing == nil and 64 or finite(args.spacing, "spacing")
	if spacing < 1 then error("spacing must be at least 1 metre", 0) end
	if x < bounds.min.x or x > bounds.max.x or y < bounds.min.y or y > bounds.max.y then
		error("grid origin is outside the map", 0)
	end
	local maxCols = math.floor((bounds.max.x-x)/spacing) + 1
	local maxRows = math.floor((bounds.max.y-y)/spacing) + 1
	local cols = pageInteger(args.columns, maxCols, 1, maxCols, "columns")
	local rows = pageInteger(args.rows, maxRows, 1, maxRows, "rows")
	local total = cols * rows
	local offset = pageInteger(args.offset, 0, 0, 2147483647, "offset")
	local limit = pageInteger(args.limit, 512, 1, 1024, "limit")
	local mode = args.mode or "surface"
	if mode ~= "surface" and mode ~= "base" then error("mode must be surface or base", 0) end
	local heights, water = {}, {}
	for i = offset, math.min(total, offset + limit)-1 do
		local px, py = x+(i % cols)*spacing, y+math.floor(i/cols)*spacing
		local pos = api.type.Vec2f.new(px, py)
		heights[#heights+1] = mode == "base" and api.engine.terrain.getBaseHeightAt(pos) or api.engine.terrain.getHeightAt(pos)
		water[#water+1] = api.engine.terrain.isOnWater(pos)
	end
	local hasMore = offset + #heights < total
	return {origin={x=x,y=y}, spacing=spacing, columns=cols, rows=rows, total=total,
		offset=offset, count=#heights, heights=heights, water=water, mode=mode,
		hasMore=hasMore, nextOffset=hasMore and (offset+#heights) or nil,
		order="row-major; x varies fastest", consistency="live; not a terrain snapshot"}
end

-- Native notification inspection. No GUI hooks, events, dismissals, or sim updates.
do
 local base="::/game_mechanics/notifications/types/"
 local function render(n)
  local p,s=n.params or {},n.simParams
  if not s then return nil,"native simParams unavailable" end
  local lang=ug_require("::/scripts/lang_util.tl")
  if n.type==base.."town_rating_warning.script" then
   local town=p.entities and p.entities[1] and p.entities[1].entity
   local name=s.mapping and s.mapping[town]
   local ratingName,icon
   for _,r in ipairs(ug_require("::/game_mechanics/towns/town_util.tl").GetRatings())do
    if p.param and p.param.key==r.key then ratingName=r.name;icon=r.icon;break end
   end
   if not name or not ratingName then return nil,"town/rating label unavailable" end
   return {title=_("Town Rating Very Poor"),icon=icon,
    description=lang.format(_("The rating \"{what}\" of {town} is very poor and the residents are furious. Action should be taken immediately."),{town=name,what=ratingName})}
  elseif n.type==base.."industry_spawn.script" then
   local name=s.mapping and p.entity and s.mapping[p.entity.entity]
   if not name then return nil,"industry label unavailable" end
   return {title=_("New Industry Founded"),
    description=lang.format(_("A visionary entrepreneur smells an opportunity for profit and has founded {industry}."),{industry=name})}
  elseif n.type==base.."subvention_notification.script" then
   -- Only the reviewed native, read-only formatters. Never load arbitrary mod GUI code.
   local allowed={
    ["::/game_mechanics/subventions/deliver_passengers/deliver_passengers.res"]=true,
    ["::/game_mechanics/subventions/deliver_cargo/deliver_cargo.res"]=true}
   if not allowed[p.id] then return nil,"subvention formatter not reviewed" end
   local rid=api.res.genericRep.find(p.id)
   if not rid or rid<0 then return nil,"subvention resource unavailable" end
   local desc=api.res.genericRep.get(rid).data
   -- Verify resource indirection too, before executing a formatter.
   local entryName=p.id:match("/([^/]+)%.res$")
   if desc.scriptFile~=p.id:gsub("%.res$",".script").."@"..entryName then return nil,"subvention script differs from reviewed resource" end
   local util=ug_require("::/scripts/util.tl")
   local script=util.useFn(desc.scriptFile)
   local status=({"Proposed","Active","Complete","Failed"})[p.status]
   if not status or not s.mapping then return nil,"subvention status/mapping unavailable" end
   local data=script.getNotificationData(p.id,p.params,status,"None",s.mapping)
   data.title=p.status==1 and _("Subsidy Available") or p.status==2 and _("Subsidy in Progress")
    or p.status==3 and _("Subsidy Effect Active") or "Invalid Status"
   return data
  end
  return nil,"GUI-only or unsupported text renderer; raw native parameters retained"
 end
 commands.get_notifications=function(args)
  if args.include_history~=nil then assert(type(args.include_history)=="boolean","include_history must be boolean") end
  local offset=pageInteger(args.offset,0,0,2147483647,"offset")
  local limit=pageInteger(args.limit,100,1,1024,"limit")
  local id=api.engine.system.gameScriptSystem.getEntityForGameScript("::/game_mechanics/notifications/notifications.gs")
  assert(id and id>=0,"native notifications script unavailable")
  local c=assert(getComponent(id,"GAME_SCRIPT"),"native notification component unavailable")
  local state=c.state
  if not state and c.state_native then state=c.state_native:asTable() end
  assert(state and state.notifications and state.history,"native notification state/history unavailable")
  local membership,historyMissing={},{}
  for _,key in ipairs(state.history)do
   membership[key]=true
   if not state.notifications[key] then historyMissing[#historyMissing+1]=key end
  end
  local selected,currentCount={},0
  for key,e in pairs(state.notifications)do
   assert(type(key)=="number","unsupported native notification key")
   -- This is exactly the native popup-list selector, not expired/TTL inference.
   local current=membership[key]==true and not e.dismissed
   if current then currentCount=currentCount+1 end
   if args.include_history==true or current then selected[#selected+1]={id=key,entry=e,current=current} end
  end
  table.sort(selected,function(a,b)
   local at,bt=a.entry.timestamp or 0,b.entry.timestamp or 0
   if at~=bt then return at<bt end
   return a.id<b.id
  end)
  local items={}
  for i=offset+1,math.min(#selected,offset+limit)do
   local v=selected[i];local e=v.entry;local n=e.notification
   local row={id=v.id,timestamp=e.timestamp,inHistory=membership[v.id]==true,popupEligible=v.current,
    dismissed=e.dismissed==true,expired=e.expired==true,tracked=e.tracked==true,
    dismissedRecorded=e.dismissed~=nil,expiredRecorded=e.expired~=nil,trackedRecorded=e.tracked~=nil,
    persisting=toPlain(e.persisting),screenVisibleKnown=false,textKnown=false}
   if n then
    row.type=n.type;row.params=toPlain(n.params);row.simParams=toPlain(n.simParams)
    row.autoDismissDuration=n.autoDismissDuration;row.subventionUid=n.params and n.params.uid
    local categoryOk,category=pcall(function()
     return ug_require("::/game_mechanics/notifications/notification_util.tl").getGuiTypeFromNotificationType(n.type)
    end)
    row.category=categoryOk and category or "Unknown"
    row.categoryKnown=categoryOk and category~=nil and category~="Unknown"
    local ok,data,reason=pcall(render,n)
    if ok and type(data)=="table" then
     row.title=data.title;row.description=data.description;row.icon=data.icon
     row.textKnown=type(data.title)=="string" and type(data.description)=="string"
     row.textSource="native template/formatter; no React hooks"
    else row.textUnavailableReason=ok and reason or tostring(data) end
   else row.textUnavailableReason="native notification payload missing" end
   items[#items+1]=row
  end
  local more=offset+#items<#selected
  return {notificationsVersion=1,readOnly=true,scriptEntity=id,player=api.engine.util.getPlayer(),
   gameTime=getComponent(api.engine.util.getWorld(),"GAME_TIME").gameTime,
   scope=args.include_history==true and "retained" or "current",items=items,total=#selected,
   currentCount=currentCount,offset=offset,hasMore=more,nextOffset=more and offset+#items or nil,
   historyComplete=#historyMissing==0,missingHistoryIds=historyMissing,
   ignored=toPlain(state.ignored),nativePaused=state.paused==true,
   consistency="live; pages may change between calls",screenVisibleKnown=false,
   visibilityDefinition="Native popup list: id in history and not dismissed. GUI render/hover/layout state is not observed.",
   rawSerialization="Standard bridge toPlain bounds apply; current list membership is enumerated before serialization."}
 end
end

-- Large component collections can be retrieved without the serializer's 2000-item cap.
commands.get_component_collection = function(args)
	local kind, field = args.component, args.field
	local schema = RECORD_SCHEMAS[COMPONENT_RECORDS[kind] or ""]
	local hint = schema and schema[field]
	if type(hint) ~= "table" then error("field is not a supported collection", 0) end
	local entity = tonumber(args.id)
	if not entity or not api.engine.entityExists(entity) then error("entity does not exist", 0) end
	local comp = getComponent(entity, kind)
	local values = comp and readField(comp, field)
	if values == nil then error("component or collection is unavailable", 0) end
	local offset = pageInteger(args.offset, 0, 0, 2147483647, "offset")
	local limit = pageInteger(args.limit, 100, 1, 1024, "limit")
	local keys = {}
	for key in pairs(values) do
		if type(key) ~= "number" and type(key) ~= "string" then error("unsupported collection key type", 0) end
		keys[#keys+1] = key
	end
	table.sort(keys, function(a,b)
		if type(a) == type(b) then return a < b end
		return type(a) < type(b)
	end)
	local items = {}
	for i=offset+1,math.min(#keys,offset+limit) do
		local key=keys[i]
		items[#items+1]={key=key,value=toPlain(values[key],0,nil,hint.element)}
	end
	local hasMore=offset+#items < #keys
	return {id=entity,component=kind,field=field,total=#keys,offset=offset,items=items,
		hasMore=hasMore,nextOffset=hasMore and offset+#items or nil,consistency="live"}
end

commands.get_terrain_tile = function(args)
	local bounds=api.engine.terrain.getBoundingBox()
	local x=pageInteger(args.tile_x,nil,math.floor(bounds.min.x/256),math.ceil(bounds.max.x/256)-1,"tile_x")
	local y=pageInteger(args.tile_y,nil,math.floor(bounds.min.y/256),math.ceil(bounds.max.y/256)-1,"tile_y")
	if x == nil or y == nil then error("tile_x and tile_y are required",0) end
	local id=api.engine.terrain.getHeightmapEntity(api.type.Vec2i.new(x,y))
	local heights=getComponent(id,"TERRAIN_TILE_HEIGHTMAP")
	local brush=getComponent(id,"TERRAIN_TILE_BRUSH")
	local terrain=getComponent(api.engine.util.getWorld(),"TERRAIN")
	return {id=id,tile={x=x,y=y},origin={x=x*256,y=y*256},sizeMetres=256,
		heightValueCount=heights and #heights.vertices or 0,
		brushAvailable=brush~=nil,brushValueCount=brush and #brush.materialIndexBrush or 0,
		baseResolution=toPlain(terrain.baseResolution),offsetZ=terrain.offsetZ,
		heightEncoding="raw integer vertices; prefer get_terrain_grid for heights in metres"}
end

commands.get_map_data = function(args)
	local terrain=getComponent(api.engine.util.getWorld(),"TERRAIN")
	local layers={}
	for name, layer in pairs(terrain.dataMaps) do
		local size=layer:getSize()
		layers[#layers+1]={name=name,width=size.x,height=size.y}
	end
	table.sort(layers,function(a,b) return a.name < b.name end)
	if args.layer == nil then return {layers=layers} end
	local layer=terrain.dataMaps[args.layer]
	if layer == nil then error("unknown map data layer",0) end
	local size=layer:getSize()
	local total=size.x*size.y
	local offset=pageInteger(args.offset,0,0,2147483647,"offset")
	local limit=pageInteger(args.limit,512,1,1024,"limit")
	local values={}
	for i=offset,math.min(total,offset+limit)-1 do values[#values+1]=layer:at(i % size.x,math.floor(i/size.x)) end
	local hasMore=offset+#values < total
	return {layer=args.layer,width=size.x,height=size.y,total=total,offset=offset,values=values,
		hasMore=hasMore,nextOffset=hasMore and offset+#values or nil,
		order="row-major; x varies fastest",meaning="raw game data layer; not rendered texture pixels",consistency="live"}
end

commands.set_game_speed = function(args, reply)
	local speed = tonumber(args and args.speed)
	if speed == nil or speed < 0 then error("'speed' must be a non-negative integer", 0) end
	speed = math.floor(speed)
	return sendGameCommand(api.cmd.makeGameSetSpeedCmd(speed), reply, function()
		return { speedup = speed }
	end)
end

-- survives between eval calls in the same Lua state (the game forbids creating globals)
local SCRATCH = {}

commands.eval = function(args)
	local code = args and args.code
	if type(code) ~= "string" then error("missing 'code'", 0) end
	if type(load) ~= "function" then error("load() is not available in this Lua state", 0) end
	local env = setmetatable({ json = json, toPlain = toPlain, log = log, scratch = SCRATCH }, { __index = _G })
	local chunk, err = load(code, "=mcp_eval", "t", env)
	if not chunk then
		-- allow bare expressions: "api.engine.util.getPlayer()"
		chunk, err = load("return " .. code, "=mcp_eval", "t", env)
	end
	if not chunk then error("compile error: " .. tostring(err), 0) end
	local results = { pcall(chunk) }
	if not results[1] then error("runtime error: " .. tostring(results[2]), 0) end
	local out = {}
	for i = 2, #results do out[#out + 1] = toPlain(results[i]) end
	if #out <= 1 then return out[1] end
	return out
end

------------------------------------------------------------------------------
-- request loop
------------------------------------------------------------------------------

local lastRequestId = nil
local lastPoll = -1e9
local lastHeartbeat = -1e9
local updateCount = 0
local requestsHandled = 0
local lastError = nil
local startedLogged = false
local transportLogged = false

local function writeResponse(id, ok, payload)
	local resp = { id = id, ok = ok }
	if ok then resp.result = payload else resp.error = tostring(payload) end
	local okEnc, text = pcall(json.encode, resp)
	if not okEnc then
		text = json.encode({ id = id, ok = false, error = "failed to encode result: " .. tostring(text) })
	end
	local okW, err = writeMessage("response", text)
	if not okW then
		lastError = "write response failed: " .. tostring(err)
		log(lastError)
	end
end

-- Runs a request's handler and calls respond(ok, payload) exactly once.
-- In the engine state command callbacks fire synchronously, so ASYNC handlers still
-- respond before this returns there; in the GUI state they respond a few frames later.
local function runRequest(req, respond, overrideHandler)
	local handler = overrideHandler or commands[req.cmd or ""]
	if handler == nil then
		respond(false, "unknown command: " .. tostring(req.cmd))
		return
	end
	local replied = false
	local function reply(ok, payload)
		if replied then return end
		replied = true
		respond(ok, payload)
	end
	local ok, result = pcall(handler, req.args or {}, reply)
	if not ok then
		reply(false, result)
	elseif result ~= ASYNC then
		reply(true, result)
	end
	return replied
end

local function encodeResponse(id, ok, payload)
	local resp = { id = id, ok = ok }
	if ok then resp.result = payload else resp.error = tostring(payload) end
	local okEnc, text = pcall(json.encode, resp)
	if okEnc then return text end
	return json.encode({ id = id, ok = false, error = "failed to encode result: " .. tostring(text) })
end

-- Engine execution: some operations (e.g. removing or replacing existing streets) only
-- work in the engine state. The GUI forwards such requests as a script event; the engine
-- runs them in handleEvent and publishes the encoded response in the game script state,
-- which guiUpdate reads (read-only) and writes back to the response file.
local ENGINE_EVENT = "tf3_mcp_request"
local ENGINE_EVENT_ID = "tf3_mcp"
local MAX_ENGINE_RESPONSES = 8
local ENGINE_COMMANDS = {get_notifications=true,get_industry_bonuses=true}   -- filled by the construction commands below
local pendingEngine = {}     -- request id -> wall clock when forwarded
local ENGINE_TIMEOUT = 25.0
local terrainStateBind = nil
local facilityStateBind = nil
local prospectionStateBind = nil
local workflowStateBinders = {}
local terrainEpoch = tostring(wallClock()) .. ":" .. tostring({})

local function forwardToEngine(req)
	req.facilityEpoch = terrainEpoch
	if req.cmd and req.cmd:find("terrain", 1, true) then req.terrainEpoch = terrainEpoch end
	local cmd = api.cmd.makeScriptingSendEventCmd("tf3_mcp_bridge", ENGINE_EVENT_ID, ENGINE_EVENT, json.encode(req))
	api.cmd.sendCommand(cmd)
	pendingEngine[req.id] = wallClock() or 0
end

local function handleEngineEvent(state, param)
	local req = json.decode(param or "")
	if type(req) ~= "table" or req.id == nil then return end
	-- Native state:get() can remain a snapshot until this event finishes.
	-- Keep read-your-writes locally so the response checkpoint cannot overwrite
	-- a workflow preview or journal written earlier in the same event.
	local nativeState, currentState = state, state:get() or {}
	state = {
		get = function() return currentState end,
		set = function(_, value)
			currentState = value
			nativeState:set(value)
		end,
	}
	local text = nil
	local checkpointProspection
	local checkpointWorkflow
	if req.cmd and req.cmd:find("road_graph",1,true) then
		checkpointWorkflow=workflowStateBinders.roadGraph(state,req.facilityEpoch,req.id)
	else
	for key,bind in pairs(workflowStateBinders) do
		if req.cmd and req.cmd:find(key,1,true) then checkpointWorkflow=bind(state,req.facilityEpoch,req.id);break end
	end
	end
	if prospectionStateBind and req.cmd and req.cmd:find("prospection", 1, true) then
		checkpointProspection = prospectionStateBind(state, req.facilityEpoch)
	end
	if facilityStateBind and ({preview_facility_module=true,preview_facility_parameter=true,build_facility=true,configure_facility=true,build_headquarters=true,build_warehouse=true,build_helipad=true,build_heliport=true,build_airfield=true,build_water_facility=true,commit_facility=true})[req.cmd] then
		facilityStateBind(state, req.facilityEpoch)
	end
	if terrainStateBind and req.cmd and req.cmd:find("terrain", 1, true) then
		terrainStateBind(state, req.terrainEpoch)
	end
	local replied = runRequest(req, function(ok, payload) text = encodeResponse(req.id, ok, payload) end)
	if checkpointProspection then checkpointProspection() end
	if checkpointWorkflow then checkpointWorkflow() end
	if not replied or text == nil then
		text = encodeResponse(req.id, false, "engine handler did not produce a result")
	end
	log("engine request " .. tostring(req.cmd) .. " -> " .. text:sub(1, 400))
	local s = state:get() or {}
	local responses = s.responses or {}
	responses[#responses + 1] = { id = req.id, text = text }
	while #responses > MAX_ENGINE_RESPONSES do table.remove(responses, 1) end
	s.responses = responses
	state:set(s)
end

local function collectEngineResponses(state)
	if next(pendingEngine) == nil or state == nil then return end
	local s = tryField(function() return state:get() end)
	local responses = s and s.responses or {}
	for _, r in ipairs(responses) do
		if pendingEngine[r.id] then
			pendingEngine[r.id] = nil
			local okW, err = writeMessage("response", r.text)
			if not okW then lastError = "write response failed: " .. tostring(err) end
		end
	end
	local now = wallClock()
	if now then
		for id, sent in pairs(pendingEngine) do
			if now - sent > ENGINE_TIMEOUT then
				pendingEngine[id] = nil
				writeResponse(id, false, "the engine did not answer (is the game running a loaded save?)")
			end
		end
	end
end

local function handleRequest(req)
	requestsHandled = requestsHandled + 1
	if req.engine == true or ENGINE_COMMANDS[req.cmd or ""] then
		local ok, err = pcall(forwardToEngine, req)
		if not ok then writeResponse(req.id, false, "could not forward to engine: " .. tostring(err)) end
		return
	end
	runRequest(req, function(ok, payload) writeResponse(req.id, ok, payload) end)
end

local function pollRequest()
	local text = readMessage("request")
	if text == nil or text == "" then return end
	local req, err = json.decode(text)
	if req == nil then
		-- probably caught mid-write; try again next poll
		lastError = "bad request json: " .. tostring(err)
		return
	end
	if req.id == nil or req.id == lastRequestId then return end
	lastRequestId = req.id
	removeMessage("request")
	handleRequest(req)
end

local function writeHeartbeat(dt)
	local hb = {
		bridgeVersion = BRIDGE_VERSION,
		updateCount = updateCount,
		requestsHandled = requestsHandled,
		dt = dt,
		clock = wallClock(),
		time = (type(os) == "table" and type(os.time) == "function") and tryField(os.time) or nil,
		paused = (dt == 0),
		lastError = lastError,
		probe = probe,
		userdataFolder = userdataFolder(),
	}
	local world = tryField(function() return api.engine.util.getWorld() end)
	if world then
		local gt = getComponent(world, "GAME_TIME")
		hb.gameTime = tryField(function() return gt.gameTime end)
		hb.tickCount = tryField(function() return gt.tickCount end)
	end
	writeMessage("heartbeat", json.encode(hb))
end

------------------------------------------------------------------------------
-- construction
------------------------------------------------------------------------------
-- Streets, depots and street stops are built with SimpleProposals applied through
-- makeWorldBuildProposalCmd. Replacing or removing existing streets only works in the
-- engine state, so all build commands are listed in ENGINE_COMMANDS and run there
-- (where command callbacks are synchronous, so several attempts can be made in one call).

local function V3(x, y, z) return api.type.Vec3f.new(x, y, z) end
local function V2(x, y) return api.type.Vec2f.new(x, y) end

local function terrainHeight(x, y)
	return api.engine.terrain.getHeightAt(V2(x, y))
end

local function dist2d(a, b)
	return math.sqrt((a.x - b.x) ^ 2 + (a.y - b.y) ^ 2)
end

local function round1(v) return v and math.floor(v * 10 + 0.5) / 10 end

local function roundPos(p)
	if p == nil then return nil end
	return { x = round1(p.x), y = round1(p.y), z = round1(p.z) }
end

local STREET_PREFIX = "::/infrastructure/street/"
local STREET_SUFFIX = ".street_template"

local function escapePattern(s)
	return (s:gsub("%p", "%%%0"))
end

local function shortStreetName(name)
	if type(name) ~= "string" then return name end
	local short = name:gsub("^" .. escapePattern(STREET_PREFIX), "")
	short = short:gsub(escapePattern(STREET_SUFFIX) .. "$", "")
	return short
end

local function resolveStreetTemplate(name)
	name = name or "town/town_old_small"
	for _, c in ipairs({ name, STREET_PREFIX .. name .. STREET_SUFFIX, STREET_PREFIX .. name, name .. STREET_SUFFIX }) do
		local id = api.res.streetTemplateRep.find(c)
		if id ~= nil and id >= 0 then return c, api.res.streetTemplateRep.get(id) end
	end
	error("unknown street type: " .. tostring(name) .. " (see list_street_types)", 0)
end

local function nodePosition(node)
	local n = getComponent(node, "BASE_NODE")
	if n == nil then return nil end
	return tryField(function() return { x = n.position.x, y = n.position.y, z = n.position.z } end)
end

local function constructionOfNode(node)
	local con = tryField(function() return api.engine.system.streetConnectorSystem.getConstructionEntityForNode(node) end)
	if con ~= nil and con >= 0 then return con end
	return nil
end

local function constructionOfEdge(edge)
	local con = tryField(function() return api.engine.system.streetConnectorSystem.getConstructionEntityForEdge(edge) end)
	if con ~= nil and con >= 0 then return con end
	return nil
end

local function newStreetEdge(entity, node0, node1, p0, p1, t0, t1, tplName, tpl)
	local e = api.type.SegmentAndEntity.new()
	e.entity = entity
	e.type = 0 -- street
	e.comp.node0 = node0
	e.comp.node1 = node1
	e.comp.position0 = V3(p0.x, p0.y, p0.z)
	e.comp.position1 = V3(p1.x, p1.y, p1.z)
	e.comp.tangent0 = V3(t0.x, t0.y, t0.z)
	e.comp.tangent1 = V3(t1.x, t1.y, t1.z)
	e.comp.type = api.type.enum.BaseEdgeType.NORMAL
	e.comp.typeIndex = -1
	e.comp.laneConfigs = tpl.laneConfigs
	e.comp.roadTemplate = tplName
	e.comp.roadStyle = tpl.streetStyle
	e.comp.roadType = api.type.enum.RoadType.STREET
	return e
end

-- Dry run. Only valid for proposals that don't remove existing streets (the game's
-- preview asserts on those). Collisions with town buildings, streets or other constructions
-- are reported as `blocking`; anything else (trees, rocks) the game clears on its own.
-- `ignore` lists entities that may be touched, e.g. the street node a new road joins.
-- Read-only, using the same penalty pipeline as the native construction UI.
-- The reconstructed Proposal is for statistics only, never for submission.
local function previewReputation(proposal, pd)
 local ok,result=pcall(function()
  local native=proposal
  if tryField(function()return proposal.constructionsToAdd end)~=nil then
   assert(#listOf(proposal.constructionsToRemove)==0,"removal proposals are not supported by the reputation adapter")
   for _,key in ipairs({"nodesToAdd","edgesToAdd","nodesToRemove","edgesToRemove","edgeObjectsToAdd","edgeObjectsToRemove","nodeConfigsToAdd","nodeConfigsToRemove"}) do
    assert(#listOf(proposal.streetProposal[key])==0,"street proposals are not supported by the reputation adapter")
   end
   native=api.type.Proposal.new()
   local additions={}
   for _,entry in ipairs(listOf(proposal.constructionsToAdd)) do
    local built=api.engine.util.construction.getConstructionResult(entry.fileName,0,entry.params)
    assert(built,"construction result unavailable")
    local item=api.type.Proposal.ConstructionEntity.new()
    item.construction.subconstructions=built.subconstructions
    item.transf=entry.transf
    item.playerEntity=entry.playerEntity
    additions[#additions+1]=item
   end
   native.toAdd=additions
   assert(native.toAdd_native:size()==pd.toAddData_native:size(),"construction preview count mismatch")
  end
  local util=ug_require("::/game_mechanics/towns/town_util.tl")
  local stats=util.getProposalStats(native,pd,true)
  local out={available=true,source="native_construction_ui",unit="percentage_points",towns={},total_penalty=0,
   scope="immediate_construction_preview",actual_score_change=false}
  for town,s in pairs(stats.townStats) do
   local impact=util.calculateProposalImpact(s)
   local factors={score=1,reasonToPenalty={}}
   util.addTownAuthorityPenalties(factors,{Trees=impact.trees,Rocks=impact.rocks,
    TerrainModification=impact.terrainModification,DemolishedTownBuilding=impact.demolishedTownBuilding})
   local row={town=town,penalty=0,reasons={}}
   local name=getComponent(town,"NAME")
   if name then row.name=name.name end
   for reason,value in pairs(factors.reasonToPenalty) do
    assert(type(value)=="number" and value==value and math.abs(value)<math.huge,"invalid reputation penalty")
    row.reasons[reason]=value*100;row.penalty=row.penalty+value*100
   end
   row.delta=-row.penalty
   out.total_penalty=out.total_penalty+row.penalty
   out.towns[#out.towns+1]=row
  end
  table.sort(out.towns,function(a,b)return a.town<b.town end)
  out.total_delta=-out.total_penalty
  return out
 end)
 if ok then return result end
 return {available=false,reason=tostring(result):match("^[^\n]*"),scope="immediate_construction_preview"}
end

local function previewProposal(proposal, ignore)
	local ok, pd = pcall(api.engine.util.proposal.makeProposalData, proposal, nil)
	if not ok then
		return { reputation={available=false,reason="proposal preview failed"}, ok = false, critical = true, messages = { "preview failed: " .. (tostring(pd):match("^[^\n]*") or "") } }
	end
	if pd == nil then
		return { reputation={available=false,reason="proposal data unavailable"}, ok = false, critical = true, messages = { "the game could not evaluate this proposal" } }
	end
	local r = {
		critical = tryField(function() return pd.errorState.critical end) or false,
		messages = tryField(function() return toPlain(pd.errorState.messages) end) or {},
		warnings = tryField(function() return toPlain(pd.errorState.warnings) end) or {},
		infos = tryField(function() return toPlain(pd.errorState.infos) end) or {},
		cost = tryField(function() return pd.costs end),
		collisions = {},
	}
	r.reputation = r.critical and {available=false,reason="critical proposal"} or previewReputation(proposal,pd)
	local seen = {}
	pcall(function()
		for _, c in ipairs(pd.collisionInfo.collisionEntities) do
			if not seen[c.entity] then
				seen[c.entity] = true
				r.collisions[#r.collisions + 1] = c.entity
			end
		end
	end)
	local blocking = { townBuildings = {}, streets = {}, constructions = {} }
	for _, e in ipairs(r.collisions) do
		if not (ignore and ignore[e]) then
			if getComponent(e, "BASE_EDGE") or getComponent(e, "BASE_NODE") then
				blocking.streets[#blocking.streets + 1] = e
			elseif getComponent(e, "TOWN_BUILDING") then
				blocking.townBuildings[#blocking.townBuildings + 1] = e
			else
				local con = getComponent(e, "CONSTRUCTION")
				if con then
					local isTown = #listOf(tryField(function() return con.townBuildings end) or {}) > 0
					local list = isTown and blocking.townBuildings or blocking.constructions
					list[#list + 1] = e
				end
			end
		end
	end
	r.blocked = #blocking.townBuildings + #blocking.streets + #blocking.constructions > 0
	if r.blocked then r.blocking = blocking end
	-- Native placement constraints (e.g. coastline) may be infos with critical=false.
	r.placementBlocked = #r.infos > 0 or #r.messages > 0
	r.ok = not r.critical and not r.blocked and not r.placementBlocked
	return r, pd
end

-- Applies a proposal. done(success, res, results) is called synchronously in the engine state.
local function applyProposal(proposal, allowCollisions, done)
	api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal, nil, allowCollisions == true, true),
		function(res, success, results) done(success, res, results) end)
end

-- The segment ids in the command result are not reliable (verified in game: a reported id
-- no longer existed right after building), but node ids are; so edges are looked up from nodes.
local function addedStreetEntities(res, endpoints)
	local out = { edges = {}, nodes = {} }
	pcall(function()
		for _, n in ipairs(res.proposal.proposal.addedNodes) do out.nodes[#out.nodes + 1] = n.entity end
	end)
	local involved = {}
	for _, n in ipairs(out.nodes) do involved[n] = true end
	for _, n in ipairs(endpoints or {}) do involved[n] = true end
	local seen = {}
	local scan = {}
	for _, n in ipairs(out.nodes) do scan[#scan + 1] = n end
	for _, n in ipairs(endpoints or {}) do scan[#scan + 1] = n end
	for _, n in ipairs(scan) do
		for _, e in ipairs(listOf(tryField(function() return api.engine.system.streetSystem.getNodeSegments(n) end) or {})) do
			local be = getComponent(e, "BASE_EDGE")
			if be and not seen[e] and involved[be.node0] and involved[be.node1] then
				seen[e] = true
				out.edges[#out.edges + 1] = e
			end
		end
	end
	return out
end

------------------------------------------------------------------------------
-- queries for planning

commands.get_terrain = function(args)
	local x, y = tonumber(args.x), tonumber(args.y)
	if x == nil or y == nil then error("'x' and 'y' are required", 0) end
	return {
		height = terrainHeight(x, y),
		water = tryField(function() return api.engine.terrain.isOnWater(V2(x, y)) end),
		valid = tryField(function() return api.engine.terrain.isValidCoordinate(V2(x, y)) end),
	}
end

commands.list_street_types = function(args)
	local filter = type(args.filter) == "string" and args.filter or nil
	local names = {}
	for _, v in pairs(api.res.streetTemplateRep.getAll()) do
		if type(v) == "string" and v:find("/street/", 1, true) and not v:find("airport", 1, true)
				and not v:find("/constructions/", 1, true) then
			local short = shortStreetName(v)
			if filter == nil or short:find(filter, 1, true) then names[#names + 1] = short end
		end
	end
	table.sort(names)
	return { count = #names, streetTypes = names,
		hint = "town_* for towns, country_* between towns; old_* before ~1920; small/medium/large = lanes" }
end

local function directionDeg(dx, dy)
	return math.floor(math.deg(math.atan2(dy, dx)) % 360 + 0.5)
end

local function nodeInfo(node, center)
	local pos = nodePosition(node)
	local connections = {}
	for _, e in ipairs(listOf(tryField(function() return api.engine.system.streetSystem.getNodeSegments(node) end) or {})) do
		local be = getComponent(e, "BASE_EDGE")
		if be then
			local t, sign
			if be.node0 == node then t, sign = be.tangent0, 1 else t, sign = be.tangent1, -1 end
			connections[#connections + 1] = {
				edge = e,
				direction = tryField(function() return directionDeg(t.x * sign, t.y * sign) end),
				streetType = shortStreetName(tryField(function() return be.roadTemplate end)),
			}
		end
	end
	return {
		id = node,
		position = roundPos(pos),
		distance = pos and center and round1(dist2d(pos, center)) or nil,
		connections = connections,
		construction = constructionOfNode(node),
	}
end

local function stationGroupOfStation(station)
	for _, g in ipairs(collectEntities("STATION_GROUP", MAX_LIST)) do
		local group = getComponent(g, "STATION_GROUP")
		for _, s in ipairs(group and listOf(group.stations) or {}) do
			if s == station then return g end
		end
	end
	return nil
end

commands.find_nearby = function(args)
	local x, y = tonumber(args.x), tonumber(args.y)
	if x == nil or y == nil then error("'x' and 'y' are required", 0) end
	local radius = math.min(tonumber(args.radius) or 100, 500)
	local limit = tonumber(args.limit) or 15
	local center = { x = x, y = y }
	local CT = componentTypes()
	local function inCircle(ct)
		return listOf(api.engine.util.octree.findEntitiesInCircle(V2(x, y), radius, ct))
	end

	local nodes = {}
	for _, n in ipairs(inCircle(CT.BASE_NODE)) do nodes[#nodes + 1] = nodeInfo(n, center) end
	table.sort(nodes, function(a, b) return (a.distance or 1e9) < (b.distance or 1e9) end)
	for i = #nodes, limit + 1, -1 do nodes[i] = nil end

	local edges = {}
	for _, e in ipairs(inCircle(CT.BASE_EDGE)) do
		local be = getComponent(e, "BASE_EDGE")
		if be and #edges < limit then
			local p0, p1 = be.position0, be.position1
			edges[#edges + 1] = {
				id = e,
				node0 = be.node0,
				node1 = be.node1,
				streetType = shortStreetName(tryField(function() return be.roadTemplate end)),
				track = tryField(function() return be.roadType == api.type.enum.RoadType.TRACK end),
				length = tryField(function() return round1(dist2d(p0, p1)) end),
				objects = #listOf(tryField(function() return be.objects end) or {}),
				construction = constructionOfEdge(e),
			}
		end
	end

	local stations, seenGroups = {}, {}
	for _, s in ipairs(inCircle(CT.STATION)) do
		local g = stationGroupOfStation(s)
		if g and not seenGroups[g] then
			seenGroups[g] = true
			stations[#stations + 1] = { id = g, name = entityName(g), position = roundPos(stationGroupPosition(g)) }
		end
	end

	local constructions, townBuildings = {}, 0
	for _, c in ipairs(inCircle(CT.CONSTRUCTION)) do
		local con = getComponent(c, "CONSTRUCTION")
		local fileName = con and tryField(function() return con.fileName end) or ""
		if #listOf(con and tryField(function() return con.townBuildings end) or {}) > 0 then
			townBuildings = townBuildings + 1
		elseif #constructions < limit then
			constructions[#constructions + 1] = { id = c, fileName = fileName, position = roundPos(constructionPosition(c)) }
		end
	end

	return {
		center = { x = x, y = y, height = round1(terrainHeight(x, y)) },
		radius = radius,
		nodes = nodes,
		edges = edges,
		stations = stations,
		constructions = constructions,
		townBuildings = townBuildings,
	}
end

------------------------------------------------------------------------------
-- roads

local function roadNumber(value, label, minimum, maximum)
	local n = tonumber(value)
	if not n or n ~= n or n == math.huge or n == -math.huge then error(label .. " must be finite", 0) end
	if minimum and (n < minimum or n > maximum) then error(label .. " must be between " .. minimum .. " and " .. maximum, 0) end
	return n
end

local function isStreetNode(node)
	if nodePosition(node) == nil then return false end
	for _, e in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do
		local be = getComponent(e, "BASE_EDGE")
		if be and be.roadType == api.type.enum.RoadType.STREET then return true end
	end
	return false
end

-- Construction-owned internal nodes are not legal public street attachment points.
-- A degree-one frozen node can look like an entrance; joining it can trigger the
-- native TransportNetworkSystem::EntityToBeRemoved assertion before readback.
local function isFrozenStreetNode(node)
 local owners = {}
 local owner = constructionOfNode(node)
 if owner then owners[owner] = true end
 for _, edge in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do
  local con = constructionOfEdge(edge)
  if con then owners[con] = true end
 end
 for con in pairs(owners) do
  local c = getComponent(con, "CONSTRUCTION")
  for _, frozen in ipairs(listOf(c and c.frozenNodes)) do
   if frozen == node then return true end
  end
 end
 return false
end

-- A failed native submission may leave BASE_EDGE/BASE_NODE present while its
-- generated TRANSPORT_NETWORK has gone. Geometry alone cannot reconcile it.
local function assertStreetNetworkHealthy(node, label)
 if componentTypes().TRANSPORT_NETWORK == nil then return end
 if getComponent(node, "TRANSPORT_NETWORK") == nil then
  error(label .. ": street node is missing TRANSPORT_NETWORK; reload a clean checkpoint", 0)
 end
 for _, edge in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do
  if getComponent(edge, "TRANSPORT_NETWORK") == nil then
   error(label .. ": adjacent street edge is missing TRANSPORT_NETWORK; reload a clean checkpoint", 0)
  end
 end
end

local function resolveEndpoint(spec, snapRadius, label)
	if type(spec) ~= "table" then error("'" .. label .. "' must be {node=id} or {x=..., y=...}", 0) end
	if spec.node ~= nil then
		local node = roadNumber(spec.node, label .. ".node", 0, 2147483647)
		if node % 1 ~= 0 or not isStreetNode(node) then error(label .. ": " .. tostring(spec.node) .. " is not a street node", 0) end
		if isFrozenStreetNode(node) then error(label .. ": frozen construction node; use the external road port", 0) end
		assertStreetNetworkHealthy(node, label)
		return { node = node, pos = nodePosition(node), snapped = false }
	end
	local x = roadNumber(spec.x or spec[1], label .. ".x")
	local y = roadNumber(spec.y or spec[2], label .. ".y")
	if not api.engine.terrain.isValidCoordinate(V2(x, y)) then error(label .. " is outside the map", 0) end
	local z = spec.z ~= nil and roadNumber(spec.z, label .. ".z") or nil
	local radius = roadNumber(spec.snap == nil and snapRadius or spec.snap, label .. ".snap", 0, 500)
	if radius > 0 then
		local best, bestD
		for _, n in ipairs(listOf(api.engine.util.octree.findEntitiesInCircle(V2(x, y), radius, componentTypes().BASE_NODE))) do
			if isStreetNode(n) and not isFrozenStreetNode(n) then
				local p = nodePosition(n)
				local d = dist2d(p, { x = x, y = y })
				if z then d = math.sqrt(d * d + (p.z - z) ^ 2) end
				if d <= radius and (bestD == nil or d < bestD or (d == bestD and n < best)) then best, bestD = n, d end
			end
		end
		if best then assertStreetNetworkHealthy(best, label); return { node = best, pos = nodePosition(best), snapped = true, snapDistance = round1(bestD), explicitHeight = z ~= nil } end
	end
	return { pos = { x = x, y = y, z = z or roadNumber(terrainHeight(x, y), "terrain height") }, snapped = false, explicitHeight = z ~= nil }
end

-- Straight road through the given points, split so no piece is longer than maxLen and
-- every intermediate node follows the terrain.
local function makeRoadProposal(points, tplName, tpl, maxLen)
	local proposal = api.type.SimpleProposal.new()
	local nodesToAdd, edgesToAdd = {}, {}
	local nextId = -1
	local function newId() local id = nextId; nextId = nextId - 1; return id end
	local function addNode(pos)
		local n = api.type.NodeAndEntity.new()
		n.entity = newId()
		n.comp.position = V3(pos.x, pos.y, pos.z)
		nodesToAdd[#nodesToAdd + 1] = n
		return n.entity
	end
	local length = 0
	local prevNode = points[1].node or addNode(points[1].pos)
	local prevPos = points[1].pos
	for i = 2, #points do
		local a, b = points[i - 1].pos, points[i].pos
		local legLen = dist2d(a, b)
		if legLen < 2 then error("points " .. (i - 1) .. " and " .. i .. " are less than 2 m apart", 0) end
		length = length + legLen
		local pieces = math.max(1, math.ceil(legLen / maxLen))
		if #edgesToAdd + pieces > 512 then error("road exceeds 512 segments; split it into smaller requests", 0) end
		for k = 1, pieces do
			local pos, node
			if k == pieces then
				pos = b
				node = points[i].node or addNode(b)
			else
				local t = k / pieces
				pos = { x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t }
				if not api.engine.terrain.isValidCoordinate(V2(pos.x, pos.y)) then error("road crosses outside the map", 0) end
				pos.z = (points[i - 1].explicitHeight or points[i].explicitHeight)
					and (a.z + (b.z - a.z) * t) or roadNumber(terrainHeight(pos.x, pos.y), "terrain height")
				node = addNode(pos)
			end
			local tan = { x = pos.x - prevPos.x, y = pos.y - prevPos.y, z = pos.z - prevPos.z }
			edgesToAdd[#edgesToAdd + 1] = newStreetEdge(newId(), prevNode, node, prevPos, pos, tan, tan, tplName, tpl)
			prevNode, prevPos = node, pos
		end
	end
	proposal.streetProposal.nodesToAdd = nodesToAdd
	proposal.streetProposal.edgesToAdd = edgesToAdd
	return proposal, length, #edgesToAdd
end

-- Existing nodes a road joins, and the streets already at them, are expected to touch it.
local function roadIgnoreSet(points)
	local ignore = {}
	for _, pt in ipairs(points) do
		if pt.node then
			ignore[pt.node] = true
			for _, e in ipairs(listOf(tryField(function() return api.engine.system.streetSystem.getNodeSegments(pt.node) end) or {})) do
				ignore[e] = true
			end
			local con = constructionOfNode(pt.node)
			if con then ignore[con] = true end
		end
	end
	return ignore
end

-- Run after construction, separately from the original proposal. Replacing an edge
-- can change its id, so keep node pairs as the durable identity for this operation.
local function finishRoadConnections(endpoints, newEdges, before)
 local CT=api.type.ComponentType
 local pairsToFind={}
 for _,id in ipairs(newEdges) do local e=getComponent(id,'BASE_EDGE');if e then pairsToFind[#pairsToFind+1]={e.node0,e.node1} end end
 local function currentEdges()
  local out={};local seen={}
  for _,pair in ipairs(pairsToFind) do
   for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(pair[1]))) do
    local e=getComponent(id,'BASE_EDGE')
    if e and ((e.node0==pair[1] and e.node1==pair[2]) or (e.node1==pair[1] and e.node0==pair[2])) and not seen[id] then
     seen[id]=true;out[#out+1]=id
    end
   end
  end
  return out,seen
 end
 local function farNodes(edge,node,mode,incoming)
  local tn=getComponent(edge,'TRANSPORT_NETWORK');local out={}
  if tn then for _,e in ipairs(tn.edges) do if e.transportModes[mode] then
   local a,b=e.conns[1],e.conns[2]
   if incoming and a.entity~=node and b.entity==node then out[#out+1]=a end
   if not incoming and a.entity==node and b.entity~=node then out[#out+1]=b end
  end end end
  return out
 end
 local function check(node,newSet)
  local old,new={},{}
  for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do
   if newSet[id] then new[#new+1]=id else old[#old+1]=id end
  end
  if #new==0 or #old==0 then return false,'missing adjacent road' end
  if not api.engine.util.pathfinding then return false,'pathfinding unavailable' end
  for _,mode in ipairs({api.type.enum.TransportMode.CAR,api.type.enum.TransportMode.TRUCK}) do
   for _,a in ipairs(old) do for _,b in ipairs(new) do
    local x,y=farNodes(a,node,mode,true),farNodes(b,node,mode,false)
    local rx,ry=farNodes(b,node,mode,true),farNodes(a,node,mode,false)
    if #x==0 or #y==0 or #rx==0 or #ry==0 then return false,'vehicle lanes unavailable' end
    for _,direction in ipairs({{x,y},{rx,ry}}) do
     local route=api.engine.util.pathfinding.findPathNodeToNode(direction[1],direction[2],{mode})
     local usesOld,usesNew=false,false
     for _,step in ipairs(route) do
      local id=step[1].entity
      if id~=a and id~=b and id~=node then return false,'path detours through other roads' end
      usesOld=usesOld or id==a;usesNew=usesNew or id==b
     end
     if not usesOld or not usesNew then return false,'no direct two-way vehicle path' end
    end
   end end
  end
  return true
 end
 local out={verified=true,junctions={}}
 local visited={}
 for _,node in ipairs(endpoints) do if not visited[node] then
  visited[node]=true
  local _,newSet=currentEdges()
  local ok,why=check(node,newSet)
  local row={node=node,verified=ok,repaired=false}
  if not ok and why~='pathfinding unavailable' and why~='vehicle lanes unavailable' then
   local cfg=getComponent(node,'BASE_NODE_CONFIG')
   local canReset=before[node] and #before[node]==1 and cfg and #listOf(cfg.laneConnections)==0
   local reset=true
   if canReset then
    local p=api.type.SimpleProposal.new();p.streetProposal.nodeConfigsToRemove={node}
    reset=false;applyProposal(p,false,function(success) reset=success==true end)
   end
   if reset then
    for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do if newSet[id] then
     local success=false
     applyProposal(api.engine.util.proposal.replaceSegment(id),false,function(value) success=value==true end)
     row.repaired=success
     if not success then why='junction refresh rejected' end
     break
    end end
   else why='lane configuration reset rejected' end
   _,newSet=currentEdges()
   local checked,message=check(node,newSet);ok=checked;why=message or why
   row.verified=ok
  end
  if not ok then out.verified=false;row.reason=why end
  out.junctions[#out.junctions+1]=row
 end end
 out.edges=currentEdges()
 return out
end

local function buildRoad(points, tplName, tpl, maxLen, allowCollisions)
	local proposal, length, pieces = makeRoadProposal(points, tplName, tpl, maxLen)
	local outcome = { built = false, verified = false, complete = false, length = round1(length), segments = pieces }
	local endpoints, oldEdges, before = {}, {}, {}
	for _, pt in ipairs(points) do
		if pt.node then
			endpoints[#endpoints + 1] = pt.node
			before[pt.node] = listOf(api.engine.system.streetSystem.getNodeSegments(pt.node))
            -- r15/r16: adding a branch at an existing multi-edge node asserted
            -- in native commit despite clean previews. Keep this topology read-only
            -- until the native junction contract is understood; collision flags do not bypass it.
            if #before[pt.node] >= 2 then
                outcome.reason = { ok = false, code = "junction_commit_suspended",
                    node = pt.node, degree = #before[pt.node],
                    messages = { "Existing junction branch commits are suspended after native assertions; preview is geometry only" } }
                return outcome
            end
			for _, e in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(pt.node))) do oldEdges[e] = true end
		end
	end
	local check = previewProposal((makeRoadProposal(points, tplName, tpl, maxLen)), roadIgnoreSet(points))
	outcome.cost = check.cost
	if check.critical or (check.blocked and not allowCollisions) then
		outcome.reason = check
		return outcome
	end
	applyProposal(proposal, allowCollisions == true, function(success, res)
		outcome.built = success
		if success then
			local added = addedStreetEntities(res, endpoints)
			outcome.edges, outcome.nodes = {}, added.nodes
			for _, e in ipairs(added.edges) do
				if not oldEdges[e] then outcome.edges[#outcome.edges + 1] = e end
			end
		end
	end)
	if outcome.built then
        local ok, connections = pcall(finishRoadConnections, endpoints, outcome.edges, before)
        outcome.connections = ok and connections or {verified=false, reason=tostring(connections)}
        outcome.verified = ok and connections.verified or false
        outcome.complete = outcome.verified
        if ok then outcome.edges = connections.edges end
        if not outcome.verified then outcome.reason = {ok=false, messages={"Road exists, but vehicle connections are not verified; do not rebuild it."}} end
    end
	if not outcome.built then
		outcome.reason = { ok = false, messages = { "game rejected the build command" }, preview = check }
	end
	return outcome
end

commands.build_road = function(args)
	local tplName, tpl = resolveStreetTemplate(args.street_type)
	local snap = roadNumber(args.snap_radius == nil and 5 or args.snap_radius, "snap_radius", 0, 500)
	if args.via ~= nil and type(args.via) ~= "table" then error("via must be an array of points", 0) end
	if #(args.via or {}) > 126 then error("road supports at most 128 points", 0) end
	for _, key in ipairs({ "preview", "allow_collisions" }) do
		if args[key] ~= nil and type(args[key]) ~= "boolean" then error(key .. " must be boolean", 0) end
	end
	local points = { resolveEndpoint(args.start, snap, "start") }
	for i, v in ipairs(type(args.via) == "table" and args.via or {}) do
		points[#points + 1] = resolveEndpoint(v, 0, "via[" .. i .. "]")
	end
	points[#points + 1] = resolveEndpoint(args["end"], snap, "end")
	local maxLen = roadNumber(args.max_segment_length == nil and 50 or args.max_segment_length, "max_segment_length", 10, 200)
	local summary = { streetType = shortStreetName(tplName), from = points[1].node or roundPos(points[1].pos),
		to = points[#points].node or roundPos(points[#points].pos), points = {}, maxSegmentLength = maxLen }
	for _, pt in ipairs(points) do
		summary.points[#summary.points + 1] = { node = pt.node, position = roundPos(pt.pos), snapped = pt.snapped,
			snapDistance = pt.snapDistance }
	end
	local r
	if args.preview then
		local proposal, length, pieces = makeRoadProposal(points, tplName, tpl, maxLen)
		r = previewProposal(proposal, roadIgnoreSet(points))
		r.length, r.segments = round1(length), pieces
		r.buildable = not r.critical and (not r.blocked or args.allow_collisions == true)
        r.geometryBuildable = r.buildable
        r.commitSupported = true
        for _, pt in ipairs(points) do
            if pt.node and #listOf(api.engine.system.streetSystem.getNodeSegments(pt.node)) >= 2 then
                r.commitSupported = false
                r.commitBlockedReason = "junction_commit_suspended"
                r.buildable = false
            end
        end
		r.path = {}
		for i, edge in ipairs(proposal.streetProposal.edgesToAdd) do
			if i == 1 then r.path[1] = roundPos(edge.comp.position0) end
			r.path[#r.path + 1] = roundPos(edge.comp.position1)
		end
	else
		r = buildRoad(points, tplName, tpl, maxLen, args.allow_collisions)
	end
	for k, v in pairs(summary) do r[k] = v end
	return r
end
ENGINE_COMMANDS.build_road = true

-- Native replacement preserves road geometry and junctions. Do not pass a removal
-- proposal to makeProposalData: that path can assert in this game version.
commands.upgrade_road = function(args)
	local edge = roadNumber(args.edge, "edge", 0, 2147483647)
	if edge % 1 ~= 0 then error("edge must be an integer", 0) end
	if args.preview ~= nil and type(args.preview) ~= "boolean" then error("preview must be boolean", 0) end
	local be = getComponent(edge, "BASE_EDGE")
	if not be or be.roadType ~= api.type.enum.RoadType.STREET then error("edge is not a street segment", 0) end
	if constructionOfEdge(edge) then error("construction-owned streets must be modified through their construction", 0) end
	if be.type ~= api.type.enum.BaseEdgeType.NORMAL then error("bridge and tunnel upgrades are not supported yet", 0) end
	if #listOf(be.objects) > 0 then error("roads with stops or other edge objects are not supported yet", 0) end
	if type(args.street_type) ~= "string" or args.street_type == "" then error("street_type is required", 0) end
	local name, target = resolveStreetTemplate(args.street_type)
	assert(target.roadType==nil or target.roadType==api.type.enum.RoadType.STREET,"Road upgrade cannot change network type")
	local oldName = be.roadTemplate
	if args.expected_street_type ~= nil then
		local expected = resolveStreetTemplate(args.expected_street_type)
		if expected ~= oldName then error("road type changed since preview; preview again", 0) end
	end
	local n0, n1 = be.node0, be.node1
	local out = { edge = edge, fromType = shortStreetName(oldName), toType = shortStreetName(name),
		nodes = { n0, n1 }, positions = { roundPos(be.position0), roundPos(be.position1) },
		preview = args.preview ~= false, changed = false, geometryPreserved = true }
	if oldName == name then out.noChange = true; return out end
	local proposal = api.engine.util.proposal.replaceSegment(edge, name)
	if not proposal then error("game could not create a road replacement proposal", 0) end
	-- Keep the first implementation scoped to replacement of exactly one bare road.
	local added, removed = listOf(proposal.proposal.addedSegments), listOf(proposal.proposal.removedSegments)
	if #added ~= 1 or #removed ~= 1 or removed[1].entity ~= edge
		or #listOf(proposal.toRemove) > 0 or #listOf(proposal.toAdd) > 0
		or added[1].comp.node0 ~= n0 or added[1].comp.node1 ~= n1
		or added[1].comp.roadTemplate ~= name then
		error("replacement proposal changes more than the requested road; refused", 0)
	end
	out.validation = "structural_only"
	out.collisionCheck = "deferred_to_build"
	out.costAvailable = false
	if out.preview then return out end
	local before = {}
	for _, e in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(n0))) do before[e] = true end
	local success = false
	-- Never ignore errors for upgrades; the engine must accept the replacement atomically.
	applyProposal(proposal, false, function(ok) success = ok == true end)
	out.applied = success
	if not success then
		out.reason = { messages = { "game rejected the road upgrade; check collisions, junction geometry and funds" } }
		return out
	end
	out.edges = {}
	for _, e in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(n0))) do
		local current = getComponent(e, "BASE_EDGE")
		if current and (not before[e] or e == edge) and current.roadTemplate == name
			and current.node0 == n0 and current.node1 == n1 then out.edges[#out.edges + 1] = e end
	end
	out.changed = #out.edges == 1
	out.verified = out.changed
	if not out.verified then out.reason = { messages = { "command succeeded but replacement could not be verified; inspect before retrying" } } end
	return out
end
ENGINE_COMMANDS.upgrade_road = true


------------------------------------------------------------------------------
-- depots and stations (constructions whose street entrance must face and join a street)

local DEPOT_FILES = {
	ROAD = "::/depots/road/road_depot/road_depot.con",
	TRAM = "::/depots/road/tram_depot/tram_depot.con",
	RAIL = "::/depots/rail/rail_depot.con",
	WATER = "::/depots/water/water_depot.con",
}
-- Measured in game: the street entrance node sits on the construction's local -y axis.
local ENTRANCE_OFFSET = {
	["::/depots/road/road_depot/road_depot.con"] = 20.26,
	["::/stations/street/modular_street_station/modular_terminal.con"] = 15,
}
local TERMINAL_CON = "::/stations/street/modular_street_station/modular_terminal.con"
local TERMINAL_DIR = "::/stations/street/modular_street_station/"

local function transfAt(x, y, z, angle)
	local c, s = math.cos(angle), math.sin(angle)
	local V4 = api.type.Vec4f.new
	return api.type.Mat4f.new(V4(c, s, 0, 0), V4(-s, c, 0, 0), V4(0, 0, 1, 0), V4(x, y, z, 1))
end

-- Angle that points the entrance (local -y) towards (tx, ty).
local function angleFacing(x, y, tx, ty)
	return math.atan2(tx - x, -(ty - y))
end

local function nearestStreetNodes(x, y, radius, exclude)
	local out = {}
	for _, n in ipairs(listOf(api.engine.util.octree.findEntitiesInCircle(V2(x, y), radius, componentTypes().BASE_NODE))) do
		local pos = nodePosition(n)
		if pos and not (exclude and exclude[n]) and constructionOfNode(n) == nil then
			out[#out + 1] = { node = n, pos = pos, d = dist2d(pos, { x = x, y = y }) }
		end
	end
	table.sort(out, function(a, b) return a.d < b.d end)
	return out
end

local function resolveFacing(args, x, y)
	if type(args.face_towards) == "table" then
		local tx = tonumber(args.face_towards.x or args.face_towards[1])
		local ty = tonumber(args.face_towards.y or args.face_towards[2])
		if tx and ty then return angleFacing(x, y, tx, ty) end
	end
	if args.rotation ~= nil then return math.rad(tonumber(args.rotation)) end
	local near = nearestStreetNodes(x, y, 200)
	if near[1] then return angleFacing(x, y, near[1].pos.x, near[1].pos.y) end
	return 0
end

-- Build ids reported by command callbacks are unreliable, so find the new construction by
-- position and file name.
local function findConstructionAt(x, y, fileName)
	local best, bestD
	for _, c in ipairs(listOf(api.engine.util.octree.findEntitiesInCircle(V2(x, y), 40, componentTypes().CONSTRUCTION))) do
		local con = getComponent(c, "CONSTRUCTION")
		if con and tryField(function() return con.fileName end) == fileName then
			local pos = constructionPosition(c)
			local d = pos and dist2d(pos, { x = x, y = y }) or 1e9
			if bestD == nil or d < bestD then best, bestD = c, d end
		end
	end
	return best
end

-- A construction's entrance is a short stub street it owns (a frozen edge) running from a
-- frozen node inside it to a free node outside; new streets must join that outer node.
local function entranceNodeOf(con)
	local frozen = {}
	for _, n in ipairs(listOf(con.frozenNodes)) do frozen[n] = true end
	for _, e in ipairs(listOf(con.frozenEdges)) do
		local be = getComponent(e, "BASE_EDGE")
		if be then
			if not frozen[be.node1] then return be.node1, frozen end
			if not frozen[be.node0] then return be.node0, frozen end
		end
	end
	return listOf(con.frozenNodes)[1], frozen
end

-- Joins a construction's street entrance to the nearest reachable street node.
local function connectEntrance(con, args)
	local entranceNode, frozen = entranceNodeOf(con)
	if entranceNode == nil then return { failed = true, reason = "the construction has no street entrance" } end
	local segments = listOf(tryField(function() return api.engine.system.streetSystem.getNodeSegments(entranceNode) end) or {})
	if #segments > 1 then return { entranceNode = entranceNode, alreadyConnected = true } end
	local ePos = nodePosition(entranceNode)
	local tplName, tpl = resolveStreetTemplate(args.street_type)
	local exclude = { [entranceNode] = true }
	for n in pairs(frozen) do exclude[n] = true end
	local attempts = {}
	for _, cand in ipairs(nearestStreetNodes(ePos.x, ePos.y, tonumber(args.connect_radius) or 80, exclude)) do
		if #attempts >= 6 then break end
		local r = buildRoad({ { node = entranceNode, pos = ePos }, { node = cand.node, pos = cand.pos } },
			tplName, tpl, 50, args.allow_collisions)
		attempts[#attempts + 1] = { toNode = cand.node, distance = round1(cand.d), built = r.built,
			reason = r.reason and (r.reason.blocking or r.reason.messages) or nil }
		if r.built then
			return { entranceNode = entranceNode, toNode = cand.node, edges = r.edges, length = r.length,
                built = true, verified = r.verified, complete = r.complete, connections = r.connections, reason = r.reason }
		end
	end
	return { failed = true, entranceNode = entranceNode, attempts = attempts,
		hint = "no street node within reach could be joined; connect it with build_road from entranceNode" }
end

-- Shared placement for depots and stations: preview, refuse real obstacles, build, connect.
local frontageAdapter={}
-- Preserve native rejection details without another engine request or weakening
-- the guard. Bound diagnostics before JSON encoding so errors remain readable.
frontageAdapter.fail=function(message,stage,check,context)
 local remaining=96
 local function short(s,n)
  if #s<=n then return s end
  local cut=n+1
  while cut>1 and s:byte(cut)>=128 and s:byte(cut)<192 do cut=cut-1 end
  return s:sub(1,cut-1).."<truncated>"
 end
 local function bounded(v,depth)
  local t=type(v)
  if t=="string" then return short(v,128) end
  if t=="number" or t=="boolean" or t=="nil" then return v end
  if t~="table" then return "<"..t..">" end
  if depth>=5 then return "<depth limit>" end
  local out={}
  for k,value in pairs(v)do
   if remaining<=0 then out._truncated=true;break end
   remaining=remaining-1
   if type(k)=="string" or type(k)=="number" then out[type(k)=="string" and short(k,48) or k]=bounded(value,depth+1)end
  end
  return out
 end
 error(message.."; diagnostic="..json.encode({stage=stage,context=bounded(context,0),native=bounded(check,0)}),0)
end
do
 local function canonical(v)
  if type(v)~="table" then return type(v)..":"..tostring(v) end
  local keys={};for k in pairs(v) do keys[#keys+1]=k end
  table.sort(keys,function(a,b)return tostring(a)<tostring(b)end)
  local out={};for _,k in ipairs(keys)do out[#out+1]=canonical(k).."="..canonical(v[k])end
  return "{"..table.concat(out,";").."}"
 end
 local function point(p)return {x=p.x,y=p.y,z=p.z}end
 local function laneSnapshot(lanes)
  local out={}
  for _,lane in ipairs(lanes)do
   local v={transportModes={}}
   for _,key in ipairs({"offset","width","height","speed","forward"})do
    local value=lane[key]
    assert(type(value)=="number" or type(value)=="boolean","Invalid native lane field: "..key)
    v[key]=value
   end
   for mode,enabled in pairs(lane.transportModes)do
    assert(type(mode)=="number" and type(enabled)=="boolean","Invalid lane transport modes")
    v.transportModes[mode]=enabled
   end
   out[#out+1]=v
  end
  return out
 end
 frontageAdapter.inspect=function(node)
  assert(type(node)=="number" and node%1==0 and node>=0,"Invalid frontage node")
  assert(getComponent(node,"BASE_NODE") and not isFrozenStreetNode(node),"Frontage must be a current unfrozen road node")
  local ids=listOf(api.engine.system.streetSystem.getNodeSegments(node));table.sort(ids)
  assert(#ids==2,"Frontage requires exactly two road segments")
  local snapshot={node=node,position=point(nodePosition(node)),edges={},configs={},adjacency={}}
  local endpoints={[node]=true}
  for _,id in ipairs(ids) do
   local e=getComponent(id,"BASE_EDGE");assert(e and (e.node0==node or e.node1==node),"Frontage adjacency changed")
   assert(not constructionOfEdge(id) and e.roadType==api.type.enum.RoadType.STREET and e.type==api.type.enum.BaseEdgeType.NORMAL,"Only ordinary unconstrained streets supported")
   assert(#listOf(e.objects)==0,"Frontage roads with edge objects are not supported")
   local owner=ownerOf(id);assert(not owner or owner<0 or owner==api.engine.util.getPlayer(),"Foreign-owned frontage")
   for _,n in ipairs({e.node0,e.node1}) do assert(not isFrozenStreetNode(n),"Frozen frontage endpoint");endpoints[n]=true end
   snapshot.edges[#snapshot.edges+1]={id=id,node0=e.node0,node1=e.node1,position0=point(e.position0),position1=point(e.position1),
    tangent0=point(e.tangent0),tangent1=point(e.tangent1),roadTemplate=e.roadTemplate,roadStyle=e.roadStyle,
    laneConfigs=laneSnapshot(e.laneConfigs),roadDevelopmentLocked=e.roadDevelopmentLocked}
  end
  for id in pairs(endpoints) do
   local adjacent={};for _,edge in pairs(api.engine.system.streetSystem.getNodeSegments(id))do adjacent[#adjacent+1]=edge end
   table.sort(adjacent);snapshot.adjacency[tostring(id)]=adjacent
   local cfg=getComponent(id,"BASE_NODE_CONFIG")
   if cfg then
    assert(not cfg.userModifiedLaneConnections and not cfg.userModifiedTrafficLightStates,"Custom frontage node configuration requires separate review")
    assert(#listOf(cfg.trafficLightConfig.states)==0,"Traffic light phases require separate preservation support")
    local lanes={};for _,v in ipairs(cfg.laneConnections)do lanes[#lanes+1]={v.segment0,v.segment1,v.lane0,v.lane1,v.withRoad,v.withTram}end
    snapshot.configs[tostring(id)]={lanes=lanes,crosswalks=listOf(cfg.crosswalks),trafficLightPreference=cfg.trafficLightPreference,
     trafficLightType=cfg.trafficLightConfig.trafficLightType,doubleSlipSwitch=cfg.doubleSlipSwitch}
   end
  end
  return snapshot,canonical(snapshot)
 end
 frontageAdapter.geometrySummary=function(pd,target,carrier)
  local out={networkCount=0,edgeCount=0,endpointCount=0,rows={},truncated=false}
  if not pd or not pd.entity2tn then out.networkAvailable=false;return out end
  out.networkAvailable=true
  local seen={}
  for network,net in pairs(pd.entity2tn)do
   out.networkCount=out.networkCount+1
   for _,e in ipairs(net.edges)do
    out.edgeCount=out.edgeCount+1
    local modes=e.transportModes
    local compatible=(carrier=="TRAM" and modes[5] and modes[6]) or (carrier=="ROAD" and modes[2] and modes[3] and modes[4])
    local geometry=e.geometry and e.geometry.cubicSpline
    if geometry then for k=1,2 do
     local id=e.conns[k].entity;local p=geometry.pos[k]
     local z=k==1 and e.geometry.height.x or e.geometry.height.y
     local reason=not compatible and "mode" or id>=0 and "existing" or (id>=-4 and id<0) and "reserved_in_joint"
       or (math.abs(p.x-target.x)>=.05 or math.abs(p.y-target.y)>=.05) and "xy" or math.abs(z-target.z)>.01 and "height_alignment" or "match"
     local row=string.format("net=%s id=%s x=%.3f y=%.3f z=%.3f dx=%.3f dy=%.3f reason=%s",tostring(network),tostring(id),p.x,p.y,z,p.x-target.x,p.y-target.y,reason)
     if not seen[row]then seen[row]=true;out.endpointCount=out.endpointCount+1
      if #out.rows<12 then out.rows[#out.rows+1]=row else out.truncated=true end
     end
    end end
   end
  end
  table.sort(out.rows)
  return out
 end
 frontageAdapter.bind=function(proposal,node,carrier,alignFoundation)
  carrier=carrier or "ROAD";assert(carrier=="ROAD" or carrier=="TRAM","Unsupported frontage carrier")
  local before=frontageAdapter.inspect(node);local target=before.position
  if carrier=="TRAM" then
   for _,edge in ipairs(before.edges) do
    local forward,backward=false,false
    for _,lane in ipairs(edge.laneConfigs) do
     if lane.transportModes[5] and lane.transportModes[6] then
      if lane.forward then forward=true else backward=true end
     end
    end
    assert(forward and backward,"Tram frontage requires both directions of electric tram lanes on each road")
   end
  end
  -- Discovery cannot retain a coincident existing node or add a coincident
  -- placeholder: native proposal generation can fail before returning geometry.
  -- Use a displaced preview-only placeholder. Its ID is above both replacement
  -- segment IDs, so removing it in the final proposal does not renumber ports.
  local first=before.edges[1]
  local outer=first.node0==node and first.position1 or first.position0
  local dx,dy=outer.x-target.x,outer.y-target.y;local span=math.sqrt(dx*dx+dy*dy)
  assert(span>=1,"Frontage segment too short for geometry discovery")
  local shift=math.min(2,span*.1)
  local port,position=-2,{x=target.x+dx/span*shift,y=target.y+dy/span*shift,z=target.z}
  local edges,remove,remap={}, {}, {}
  local nextId=-3
  local function allocate()local id=nextId;nextId=nextId-1;return id end
  for _,row in ipairs(before.edges)do
   local old=getComponent(row.id,"BASE_EDGE");local e=api.type.SegmentAndEntity.new();e.entity=allocate();e.type=0
   e.comp.node0=old.node0==node and port or old.node0;e.comp.node1=old.node1==node and port or old.node1
   local a=old.node0==node and position or row.position0;local b=old.node1==node and position or row.position1
   e.comp.position0=V3(a.x,a.y,a.z);e.comp.position1=V3(b.x,b.y,b.z)
   e.comp.tangent0=V3(row.tangent0.x,row.tangent0.y,old.node0==node and 0 or row.tangent0.z)
   e.comp.tangent1=V3(row.tangent1.x,row.tangent1.y,old.node1==node and 0 or row.tangent1.z)
   e.comp.type=old.type;e.comp.typeIndex=-1;e.comp.roadTemplate=old.roadTemplate;e.comp.roadStyle=old.roadStyle
   e.comp.roadType=old.roadType;e.comp.laneConfigs=old.laneConfigs;e.comp.roadDevelopmentLocked=old.roadDevelopmentLocked
   edges[#edges+1]=e;remove[#remove+1]=row.id;remap[row.id]=e.entity
  end
  local configRemove,configAdd={},{}
  for key in pairs(before.configs)do
   local id=tonumber(key);local cfg=getComponent(id,"BASE_NODE_CONFIG");configRemove[#configRemove+1]=id
   if id~=node then
    local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=id
    local lanes={};for _,old in ipairs(cfg.laneConnections)do local l=api.type.LaneConnection.new()
     l.segment0=remap[old.segment0] or old.segment0;l.segment1=remap[old.segment1] or old.segment1
     l.lane0=old.lane0;l.lane1=old.lane1;l.withRoad=old.withRoad;l.withTram=old.withTram;lanes[#lanes+1]=l
    end
    local walks={};for _,edge in ipairs(cfg.crosswalks)do walks[#walks+1]=remap[edge] or edge end
    v.comp.laneConnections=lanes;v.comp.crosswalks=walks;v.comp.trafficLightPreference=cfg.trafficLightPreference
    v.comp.trafficLightConfig=cfg.trafficLightConfig;v.comp.doubleSlipSwitch=cfg.doubleSlipSwitch
    -- These engine-reported flags are not writable on proposal components.
    -- inspect() already rejects custom lanes/phases; retain writable config only.
    configAdd[#configAdd+1]=v
   end
  end
  proposal.streetProposal.edgesToRemove=remove;proposal.streetProposal.nodesToRemove={node}
  proposal.streetProposal.edgesToAdd=edges;proposal.streetProposal.nodeConfigsToRemove=configRemove;proposal.streetProposal.nodeConfigsToAdd=configAdd
  local placeholder=api.type.NodeAndEntity.new();placeholder.entity=port
  placeholder.comp.position=V3(position.x,position.y,position.z)
  proposal.streetProposal.nodesToAdd={placeholder}
  local check,pd=previewProposal(proposal)
  -- This first proposal intentionally contains an unbound construction port.
  -- Its placement verdict is not the verdict for the bound proposal. Use only
  -- returned geometry here; never authorize construction from this check.
  if not pd or not pd.entity2tn then
   frontageAdapter.fail("Native construction geometry unavailable","discover_port",check,{node=node,target=target,carrier=carrier,replacedEdges=remove})
  end
  local found={}
  for _,net in pairs(pd.entity2tn)do for _,e in ipairs(net.edges)do
   local matching=(carrier=="TRAM" and e.transportModes[5] and e.transportModes[6])
    or (carrier=="ROAD" and e.transportModes[2] and e.transportModes[3] and e.transportModes[4])
   if matching and e.geometry and e.geometry.cubicSpline then
    for k=1,2 do local id=e.conns[k].entity;local p=e.geometry.cubicSpline.pos[k]
     if id<-4 and math.abs(p.x-target.x)<.05 and math.abs(p.y-target.y)<.05 then
      local z=k==1 and e.geometry.height.x or e.geometry.height.y
      if found[id] then assert(math.abs(found[id].z-z)<.01,"Ambiguous entrance height") end
      found[id]={x=p.x,y=p.y,z=z}
     end
    end
   end
  end end
  local port,position,count=nil,nil,0;for id,p in pairs(found)do port=id;position=p;count=count+1 end
  if count~=1 then
   -- A construction-only control has no road-removal proposal and never commits.
   -- Keep diagnostics separate: a collision in the control cannot approve the bound proposal.
   local control,controlData
   if proposal.constructionsToAdd and #proposal.constructionsToAdd>0 then
    local unbound=api.type.SimpleProposal.new();unbound.constructionsToAdd=proposal.constructionsToAdd
    control,controlData=previewProposal(unbound)
   end
   frontageAdapter.fail("Native entrance does not uniquely match frontage; redesign placement","unique_port",check,
    {node=node,target=target,count=count,joint=frontageAdapter.geometrySummary(pd,target,carrier),
     control=control and {critical=control.critical,messages=control.messages,collisions=control.collisions,
      geometry=frontageAdapter.geometrySummary(controlData,target,carrier)} or nil})
  end
  -- Keep the existing road at its observed height. A placement guess is not
  -- grounds to move the live road or accept a disconnected port. Rebuild the
  -- construction-only input at the measured correction once, then rediscover
  -- its real port and independently preview the final bound proposal.
  if math.abs(position.z-target.z)>.01 then
   if not alignFoundation then
    frontageAdapter.fail("Native entrance needs foundation alignment or did not converge","port_height",check,
     {node=node,target=target,nativeNode=port,nativeHeight=position.z,tolerance=.01})
   end
   local delta=target.z-position.z
   local corrected=alignFoundation(delta)
   local bound,metadata,verdict=frontageAdapter.bind(corrected,node,carrier)
   metadata.heightAlignment={applied=true,delta=delta,originalNativeHeight=position.z,
    roadHeight=target.z,finalNativeHeight=metadata.nativePosition.z,roadHeightPreserved=true,iterations=1}
   return bound,metadata,verdict
  end
  for _,e in ipairs(edges)do
   if e.comp.node0==-2 then e.comp.node0=port;e.comp.position0=V3(position.x,position.y,position.z)end
   if e.comp.node1==-2 then e.comp.node1=port;e.comp.position1=V3(position.x,position.y,position.z)end
  end
  proposal.streetProposal.nodesToAdd={};proposal.streetProposal.edgesToAdd=edges
  local finalCheck,finalData=previewProposal(proposal)
  if not finalData or finalCheck.critical then
   frontageAdapter.fail("Final native frontage preview failed","bound_preview",finalCheck,{node=node,nativePort=port,nativePosition=position})
  end
  assert(finalData.entity2tn[port],"Generated port identity changed after binding")
  local ci=finalData.collisionInfo;assert(ci,"Native collision information unavailable")
  local removals={};local removalCount=0;local treeRemovals={}
  for _,key in ipairs({"buildingEntities","removableModules","autoRemovalEntity2models"})do
   local entries={};local count=0
   for id,value in pairs(ci[key] or {})do
    local entity=key=="autoRemovalEntity2models" and id or value
    local row={entity=entity};local treeOnly=false
    if type(entity)=="number" and entity>=0 then
     local con=getComponent(entity,"CONSTRUCTION");local models=getComponent(entity,"MODEL_INSTANCE_LIST")
     row.fileName=con and con.fileName or nil
     row.isRoad=getComponent(entity,"BASE_EDGE")~=nil or getComponent(entity,"BASE_NODE")~=nil
     row.hasModels=models~=nil
     if key=="autoRemovalEntity2models" and models and not con and not row.isRoad and not getComponent(entity,"TOWN_BUILDING") then
      assert(models.thinInstances~=nil and models.fatInstances~=nil,"Model lists unavailable")
      treeOnly=true;local n=0;row.modelNames={}
      -- Check all models, not just the sampled names or selected removal indices.
      for _,collection in ipairs({models.thinInstances,models.fatInstances})do
       for _,model in pairs(collection)do
        n=n+1;local name=api.res.modelRep.getName(model.modelId)
        if n<=8 then row.modelNames[#row.modelNames+1]=type(name)=="string" and name or "<unknown>" end
        local prefix="::/assets/vegetation/trees/"
        if type(name)~="string" or name:sub(1,#prefix)~=prefix then treeOnly=false end
       end
      end
      row.modelCount=n;row.namesTruncated=n>8;treeOnly=treeOnly and n>0
     end
    end
    if treeOnly then
     treeRemovals[#treeRemovals+1]=row
    else
     count=count+1;if count<=16 then entries[#entries+1]=row end
    end
   end
   if count>0 then removals[key]={count=count,entries=entries,truncated=count>16};removalCount=removalCount+count end
  end
  if #treeRemovals>0 then finalCheck.treeRemovals=treeRemovals end
  if removalCount>0 then
   finalCheck.ok=false;finalCheck.blocked=true;finalCheck.unexpected_removals=true
   finalCheck.removalReview=removals
  end
  -- Unknown/mixed assets remain blocked. Only positively identified tree groups
  -- may be cleared by the ordinary native construction proposal.

  return proposal,{roadNode=node,nativeEntranceNode=port,nativePosition=position,replacedEdges=remove,
   discoveryCritical=check.critical==true,discoveryMessages=check.messages,
   connectionsVerified=false},finalCheck
 end
end
local function placeConstruction(args, fileName, params, extra)
	local x, y = tonumber(args.x), tonumber(args.y)
	if x == nil or y == nil then error("'x' and 'y' are required", 0) end
	local groundZ = terrainHeight(x, y)
	local z = groundZ
	if args.z~=nil then
		assert(args.frontage_node~=nil and (fileName==DEPOT_FILES.ROAD or fileName==DEPOT_FILES.TRAM or fileName==TERMINAL_CON),"Explicit height requires road/tram frontage")
		assert(type(args.z)=="number" and args.z==args.z and math.abs(args.z)<math.huge,"Frontage foundation height must be finite")
		z=args.z
	end
	local angle = resolveFacing(args, x, y)
	local offset = ENTRANCE_OFFSET[fileName]
	local nativeParams = params()
	local function makeProposal()
		local proposal = api.type.SimpleProposal.new()
		local ce = api.type.SimpleProposal.ConstructionEntity.new()
		ce.fileName = fileName
		ce.transf = transfAt(x, y, z, angle)
		ce.params = nativeParams
		if type(args.name) == "string" then ce.name = args.name end
		ce.playerEntity = api.engine.util.getPlayer()
		proposal.constructionsToAdd = { ce }
		return proposal
	end

	local out = { position = roundPos({ x = x, y = y, z = z }), rotation = round1(math.deg(angle) % 360), foundationHeightAdjustment=z-groundZ }
	if offset then
		out.expectedEntrance = roundPos({ x = x + offset * math.sin(angle), y = y - offset * math.cos(angle) })
	end
	for k, v in pairs(extra or {}) do out[k] = v end

	local prepared=makeProposal()
	local check
	if args.frontage_node~=nil then
		assert(fileName==DEPOT_FILES.ROAD or fileName==DEPOT_FILES.TRAM or fileName==TERMINAL_CON,"Direct frontage supports road/tram depots and modular street stations only")
		prepared,out.frontage,check=frontageAdapter.bind(prepared,args.frontage_node,fileName==DEPOT_FILES.TRAM and "TRAM" or "ROAD",function(delta)
			assert(delta==delta and math.abs(delta)<math.huge,"Invalid native height correction")
			z=z+delta
			return makeProposal()
		end)
		out.position=roundPos({x=x,y=y,z=z});out.foundationHeightAdjustment=z-groundZ
		out.expectedEntrance=out.frontage.nativePosition
	end
	check = check or previewProposal(prepared)
	if args.preview then
		for k, v in pairs(check) do out[k] = v end
		return out
	end
	out.built = false
	if check.critical then
		out.reason = check
		return out
	end
	if check.blocked and not args.allow_collisions then
		out.reason = check
		out.hint = "it would clear the listed buildings/streets; move it, or pass allow_collisions=true"
		return out
	end
	-- only trees and similar remain in the way at this point, which the game clears itself
	applyProposal(args.frontage_node~=nil and prepared or makeProposal(), false, function(success) out.built = success end)
	if not out.built then
		out.reason = check
		return out
	end
	out.construction = findConstructionAt(x, y, fileName)
	out.cost = check.cost
	local con = out.construction and getComponent(out.construction, "CONSTRUCTION")
	if con == nil then return out end
	out.con = con
	if args.connect ~= false then out.connection = connectEntrance(con, args) end
	return out
end

-- Generic facility support. Kept in a scope to avoid Lua's chunk-local limit.
local prepareHeadquarters
do
 local tickets, serial = {}, 0
 local checkpoint=function()end
 -- Events may execute in different Lua modules. Keep lossless plain ticket data
 -- in game-owned state; a new GUI session invalidates old previews.
 facilityStateBind=function(state,epoch)
  assert(type(epoch)=='string','facility GUI session epoch required')
  local saved=(state:get() or {}).facilityAdapter or {}
  tickets=saved.epoch==epoch and (saved.tickets or {}) or {}
  serial=saved.serial or 0
  checkpoint=function()
   local root=state:get() or {}
   root.facilityAdapter={epoch=epoch,tickets=tickets,serial=serial}
   state:set(root)
  end
  checkpoint()
 end
 local function field(v,k) return tryField(function() return v[k] end) end
 local function copy(v)
  if type(v) ~= "table" then
   if type(v)=="userdata" or type(v)=="function" then error("configuration is not a lossless Lua table",0) end
   return v
  end
  local r={}; for k,x in pairs(v) do r[k]=copy(x) end; return r
 end
 local function canonical(v)
  if type(v)~="table" then return type(v)..":"..tostring(v) end
  local keys={};for k in pairs(v) do keys[#keys+1]=k end
  table.sort(keys,function(a,b) return type(a)..tostring(a)<type(b)..tostring(b) end)
  local r={};for _,k in ipairs(keys) do r[#r+1]=canonical(k).."="..canonical(v[k]) end
  return "{"..table.concat(r,";").."}"
 end
 local function lookup(kind,name)
  local rep=api.res[kind.."Rep"]
  local id=rep.find(name); if id==nil or id<0 then error("unknown "..kind..": "..tostring(name),0) end
  return rep.get(id)
 end
 local function available(d)
  local a=field(d,"availability");local y=currentYear()
  if not a or not y then return true end
  local f,t=field(a,"yearFrom") or 0,field(a,"yearTo") or 0
  if f<0 or t<0 then return nil end -- internal base resources use negative sentinels
  return (f==0 or y>=f) and (t==0 or y<t)
 end
 local function definitions(d)
  local r={}
  for _,p in ipairs(listOf(field(d,"params") or {})) do
   r[#r+1]={key=p.key,name=p.name,values=listOf(p.values or {}),numbers=listOf(p.numbers or {}),
    defaultIndex=p.defaultIndex,modifiable=p.postConstructionModifiable==true}
  end
  return r
 end
 local function category(name,d)
  if name=="::/landmarks/hq/headquarter.con" then return "headquarters",false end
  if field(d,"isIndustry")==true then return "industry",false end
  if name:find("/small_stops/",1,true) then return "street_stop",false end
  if name:find("/warehouses/",1,true) then return "warehouse",true end
  if name:find("/depots/",1,true) then return name:find("maint",1,true) and "maintenance" or "depot",true end
  if name:find("::/stations/",1,true)==1 then return "station",true end
  return "other",false
 end
 commands.list_facility_resources=function(args)
  local kind=args.kind or "construction"
  if kind~="construction" and kind~="metaConstruction" and kind~="module" then error("invalid resource kind",0) end
  local rep=api.res[kind.."Rep"]; local rows={}
  for id,name in pairs(rep.getAll(true)) do
   if not args.search or name:lower():find(args.search:lower(),1,true) then
    local d=rep.get(id);local cat,supported=category(name,d)
    local desc=field(d,"description")
    local row={id=id,resource=name,name=desc and field(desc,"name"),category=cat,available=available(d),
     parameters=definitions(d),module_type=field(d,"type"),
     construction_support=cat=="headquarters" and "build_headquarters" or (name=="::/stations/air/airfield.con" and "build_airfield" or name=="::/stations/air/helipad.con" and "build_helipad" or name=="::/stations/air/heliport.con" and "build_heliport" or (cat=="warehouse" and kind=="construction" and "build_warehouse" or (kind=="construction" and supported and "clone_existing_layout" or "dedicated_or_unsupported"))),
     template_script=field(field(d,"createTemplateScript"),"fileName")}
    if kind=="construction" and ({["::/stations/water/harbor_modular.con"]=true,["::/depots/water/water_depot.con"]=true,["::/depots/water/water_maint_station.con"]=true})[name] then
     row.construction_support="build_water_facility";row.liveAcceptance="pending"
    end
    rows[#rows+1]=row
   end
  end
  table.sort(rows,function(a,b)return a.resource<b.resource end)
  local offset=math.max(0,math.floor(tonumber(args.offset) or 0));local limit=math.min(200,math.max(1,math.floor(tonumber(args.limit) or 100)))
  local page={};for i=offset+1,math.min(#rows,offset+limit) do page[#page+1]=rows[i] end
  return {kind=kind,total=#rows,items=page,next_offset=offset+#page<#rows and offset+#page or nil}
 end
 local function inspect(id)
  id=tonumber(id);local c=id and getComponent(id,"CONSTRUCTION")
  if not c then error("entity is not a current construction; resolve it again",0) end
  local d=lookup("construction",c.fileName);local cat,supported=category(c.fileName,d)
  local p=copy(c.params_native:asTable())
  local slots,configs={},{}
  for _,s in ipairs(listOf(c.slots or {})) do slots[#slots+1]={id=s.id,type=s.type,replaceable=s.replaceable==true} end
  table.sort(slots,function(a,b)return a.id<b.id end)
  for k,v in pairs(c.slotConfig or {}) do configs[k]={maxModules=v.maxModules} end
  local transform={};for col=0,3 do
   local v=tryField(function()return c.transf:cols(col) end)
   if not v then v=tryField(function()return c.transf.cols[col+1] end) end
   if not v then error("cannot read complete construction transform",0) end
   transform[#transform+1]={x=v.x,y=v.y,z=v.z,w=v.w}
  end
  local out={entity=id,resource=c.fileName,category=cat,params=p,slots=slots,slot_config=configs,
   parameters=definitions(d),position=constructionPosition(id),owner=ownerOf(id),time_built=c.timeBuilt,
   frozen_nodes=listOf(c.frozenNodes or {}),frozen_edges=listOf(c.frozenEdges or {}),transform=transform,
   cloneable=supported and ownerOf(id)==api.engine.util.getPlayer(),
   dependent_slots=copy(toPlain(c.dependentSlots or {}))}
  local hasParameters=false;for _,param in ipairs(out.parameters) do if param.modifiable then hasParameters=true end end
  out.configurable=out.cloneable and (#slots>0 or hasParameters)
  -- External road/rail attachments can change while the construction id stays the same.
  local nodes,edges={},{}
  for _,eid in ipairs(out.frozen_edges) do
   local e=getComponent(eid,"BASE_EDGE")
   if e then nodes[e.node0]=true;nodes[e.node1]=true end
  end
  for n in pairs(nodes) do
   for _,eid in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(n))) do
    local e=getComponent(eid,"BASE_EDGE")
    if e then edges[tostring(eid)]={node0=e.node0,node1=e.node1,roadTemplate=e.roadTemplate,roadStyle=e.roadStyle,
     position0=toPlain(e.position0),position1=toPlain(e.position1),objects=toPlain(e.objects)} end
   end
  end
  out.attachments=edges
  return out,c,d
 end
 local function compactFacility(out,offset,limit)
  local result={entity=out.entity,resource=out.resource,category=out.category,position=out.position,owner=out.owner,
   configurable=out.configurable,cloneable=out.cloneable,params={modules={}},slots={},compact=true,
   detailScope="scalar parameters and bounded module/slot page; metadata and attachment graphs excluded"}
  for key,value in pairs(out.params) do
   if type(value)=="string" or type(value)=="number" or type(value)=="boolean" then result.params[key]=value end
  end
  local ids={};for id in pairs(out.params.modules or {}) do ids[#ids+1]=id end;table.sort(ids)
  for i=offset+1,math.min(#ids,offset+limit) do
   local id=ids[i];local m=out.params.modules[id];result.params.modules[id]={name=m.name,variant=m.variant}
  end
  for i=offset+1,math.min(#out.slots,offset+limit) do result.slots[#result.slots+1]=out.slots[i] end
  result.moduleCount=#ids;result.slotCount=#out.slots;result.offset=offset
  result.hasMore=offset+limit<math.max(#ids,#out.slots)
  return result
 end
 commands.get_facility_layout=function(args)
  return compactFacility(inspect(args.entity),args.offset or 0,args.limit or 30)
 end
 ENGINE_COMMANDS.get_facility_layout=true
 commands.get_facility_config=function(args)
  local out=inspect(args.entity);local types={};for _,s in ipairs(out.slots) do types[s.type]=true end
  out.compatible_modules={}
  for id,name in pairs(api.res.moduleRep.getAll(true)) do
   local d=api.res.moduleRep.get(id)
   if types[d.type] then out.compatible_modules[#out.compatible_modules+1]={resource=name,type=d.type,available=available(d)} end
  end
  table.sort(out.compatible_modules,function(a,b)return a.resource<b.resource end)
  if args.compact then
   local offset,limit=args.offset or 0,args.limit or 30
   local result=compactFacility(out,offset,limit)
   result.compatible_modules={};result.compatibleModuleCount=#out.compatible_modules
   for i=offset+1,math.min(#out.compatible_modules,offset+limit) do
    result.compatible_modules[#result.compatible_modules+1]=out.compatible_modules[i]
   end
   result.hasMore=result.hasMore or offset+limit<#out.compatible_modules
   return result
  end
  return out
 end
 commands.get_facility_access=function(args)
  local function read(id,name)
   local ct=componentTypes()[name];assert(ct,"Missing native component type: "..name)
   return api.engine.getComponent(id,ct)
  end
  local target=tonumber(args.entity)
  assert(target and api.engine.entityExists(target),"Facility no longer exists")
  local con=read(target,"CONSTRUCTION")
  assert(con,"Target is not a construction")
  local out={entity=target,resource=con.fileName,position=constructionPosition(target),links={},roads={},
   complete=true,vehiclePathVerified=false,sharedStockVerified=false}
  local function belongs(id)
   return id==target or api.engine.system.streetConnectorSystem.getConstructionEntityForSubconstruction(id)==target
  end
  local seen,roadSeen={},{};local scanned=0
  for _,ids in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities()) do
   for _,id in ipairs(ids) do
    scanned=scanned+1;assert(scanned<=100000,"Access scan limit exceeded; access unknown")
    if not seen[id] then
     seen[id]=true
     local link=read(id,"TP_NET_LINK")
     assert(link and link.from and link.to,"Native link changed; access unknown")
     local a,b=link.from.edgeId,link.to.edgeId
     if belongs(a.entity) or belongs(b.entity) then
      assert(#out.links<128,"Access result limit exceeded; access unknown")
      out.links[#out.links+1]={entity=id,fromEntity=a.entity,fromIndex=a.index,toEntity=b.entity,toIndex=b.index}
      for _,edgeId in ipairs({a.entity,b.entity}) do
       local edge=read(edgeId,"BASE_EDGE")
       local street=read(edgeId,"BASE_EDGE_STREET")
       if edge and street and not roadSeen[edgeId] then
        roadSeen[edgeId]=true
        local n0,n1=read(edge.node0,"BASE_NODE"),read(edge.node1,"BASE_NODE")
        assert(n0 and n1,"Road nodes changed; access unknown")
        out.roads[#out.roads+1]={entity=edgeId,node0=edge.node0,node1=edge.node1,
         position0=toPlain(n0.position),position1=toPlain(n1.position)}
       end
      end
     end
    end
   end
  end
  table.sort(out.links,function(a,b)return a.entity<b.entity end)
  table.sort(out.roads,function(a,b)return a.entity<b.entity end)
  out.automaticRoadLinkObserved=#out.roads>0
  assert(not args.person_geometry or args.person_graph,"PERSON geometry requires person_graph")
  if args.person_graph then
   local isHQ=con.fileName=="::/landmarks/hq/headquarter.con"
   assert(isHQ or con.fileName=="::/stations/rail/modular_station/modular_station.con"
    or con.fileName:match("^::/stations/air/"),"Unsupported construction for PERSON audit")
   if isHQ then assert(#out.roads==1,"HQ audit requires one observed frontage road; access unknown") end
   assert(#out.roads<=8,"PERSON audit frontage road bound exceeded")
   local graph={nativeProposalCalls=0,commitEnabled=false,check={clear=true},road=out.roads[1] and out.roads[1].entity,
    networks={},links={},hqEntities={},scope="existing facility PERSON graph; no proposal, native path query or simulation proof"}
   local owned,visited={},{};local scannedSubs,edgeCount,scannedEdges=0,0,0
   local function integer(v)
    assert(type(v)=="number" and v==v and math.abs(v)<math.huge and v%1==0 and v>=0,"Invalid HQ graph entity/index");return v
   end
   local function network(id,isOwned,required)
    integer(id);assert(api.engine.entityExists(id),"HQ network entity removed")
    if visited[id] then return end;visited[id]=true
    local net=read(id,"TRANSPORT_NETWORK")
    assert(net or not required,"Missing linked HQ transport network")
    if not net then return end
    assert(#graph.networks<64,"HQ readback network bound exceeded")
    local row={entity=id,edges={}}
    for i,e in ipairs(net.edges) do
     scannedEdges=scannedEdges+1;assert(scannedEdges<=1024,"PERSON audit native scan bound exceeded")
     if e.transportModes[0] then
      edgeCount=edgeCount+1;assert(edgeCount<=256,"HQ readback edge bound exceeded")
      assert(type(e.forwardOnly)=="boolean","Missing HQ lane direction")
      local a,b=e.conns[1],e.conns[2]
      local item={index=i-1,from={entity=integer(a.entity),index=integer(a.index)},
       to={entity=integer(b.entity),index=integer(b.index)},forwardOnly=e.forwardOnly}
      if args.person_geometry then
       assert(e.geometry,"Missing PERSON edge geometry")
       local function position(t)
        local p=api.engine.util.transport.calcPosition(e.geometry,t)
        assert(p and type(p.x)=="number" and type(p.y)=="number" and type(p.z)=="number"
         and p.x==p.x and p.y==p.y and p.z==p.z and math.abs(p.x)<math.huge
         and math.abs(p.y)<math.huge and math.abs(p.z)<math.huge,"Invalid PERSON edge position")
        return {x=p.x,y=p.y,z=p.z}
       end
       item.position0=position(0);item.position1=position(1);item.linkable=e.linkable
      end
      row.edges[#row.edges+1]=item
     end
    end
    graph.networks[#graph.networks+1]=row
    if isOwned then owned[id]=true;graph.hqEntities[#graph.hqEntities+1]=id end
   end
   network(target,true,false)
   assert(con.subconstructions~=nil,"Missing HQ subconstruction inventory")
   for _,id in ipairs(con.subconstructions) do
    scannedSubs=scannedSubs+1;assert(scannedSubs<=256,"HQ subconstruction bound exceeded")
    assert(belongs(id),"HQ subconstruction owner changed")
    network(id,true,false)
   end
   local frontage={};graph.roads={}
   for _,road in ipairs(out.roads) do
    frontage[road.entity]=true;graph.roads[#graph.roads+1]=road.entity;network(road.entity,false,true)
   end
   -- Only linked junctions proven to be endpoints of the observed frontage
   -- streets may extend the inventory. Arbitrary external entities stay rejected.
   local roadNodes={};graph.junctions={}
   for _,road in ipairs(out.roads) do roadNodes[road.node0]=true;roadNodes[road.node1]=true end
   for _,item in ipairs(out.links) do
    for _,id in ipairs({item.fromEntity,item.toEntity}) do
     if not owned[id] and not frontage[id] and roadNodes[id] then
      assert(read(id,"BASE_NODE"),"Linked frontage junction removed")
      network(id,false,true);frontage[id]=true;graph.junctions[#graph.junctions+1]=id
     end
    end
   end
   table.sort(graph.junctions)
   local function endpoint(p)
    assert(p and p.edgeId and type(p.param)=="number" and p.param>=0 and p.param<=1,"Invalid HQ automatic link")
    return {entity=integer(p.edgeId.entity),index=integer(p.edgeId.index),param=p.param}
   end
   for _,item in ipairs(out.links) do
    assert(#graph.links<64,"HQ readback link bound exceeded")
    local link=read(item.entity,"TP_NET_LINK");assert(link,"HQ link removed during readback")
    local a,b=endpoint(link.from),endpoint(link.to)
    for _,p in ipairs({a,b}) do
     assert(owned[p.entity] or frontage[p.entity],"HQ link endpoint outside inspected inventory")
    end
    graph.links[#graph.links+1]={entity=item.entity,from=a,to=b}
   end
   assert(#graph.hqEntities>0,"No HQ transport networks; access unknown")
   graph.facilityEntities=graph.hqEntities
   graph.scannedNativeEdges=scannedEdges;graph.personEdgeCount=edgeCount
   out.personGraph=graph
  end
  return out
 end
 ENGINE_COMMANDS.get_facility_access=true
 -- Resolve real inventory identities before any quantity queries. Catchment is
 -- read from native station catchables, never inferred from geometric distance.
 commands.get_facility_inventory=function(args)
  local id=tonumber(args.entity)
  assert(id and api.engine.entityExists(id),"Facility no longer exists")
  local con=getComponent(id,"CONSTRUCTION")
  local station=getComponent(id,"STATION")
  local group=getComponent(id,"STATION_GROUP")
  assert(con or station or group,"Expected construction, station or station group")
  local result={entity=id,warehouses={},stations={},inventories={},unknownCatchables={},
   totalCapacity=0,complete=true,scope="native inventory identity and capacity; no delivery or throughput proof"}
  local stockSeen,stationSeen,unknownSeen={},{},{}
  local function inventory(stockId)
   assert(type(stockId)=="number" and stockId>=0 and stockId%1==0,"Invalid inventory identity")
   local st=getComponent(stockId,"STOCK_LIST")
   if not st then return false end
   if stockSeen[stockId] then return true end
   assert(#result.inventories<128,"Inventory result limit exceeded")
   local slots=listOf(st.stocks);assert(#slots<=64,"Inventory slot limit exceeded")
   local row={stockList=stockId,stocks={},capacity=0}
   for i,s in ipairs(slots) do
    local capacity=s.capacity
    assert(type(capacity)=="number" and capacity>=0 and capacity<math.huge,"Invalid native stock capacity")
    row.stocks[#row.stocks+1]={stockIndex=i-1,capacity=capacity}
    row.capacity=row.capacity+capacity
   end
   stockSeen[stockId]=true;result.inventories[#result.inventories+1]=row
   result.totalCapacity=result.totalCapacity+row.capacity
   return true
  end
  if con then
   local count=0
   api.engine.forEachEntityWithComponent(function(wid)
    count=count+1;assert(count<=20000,"Warehouse scan limit exceeded")
    local w=assert(getComponent(wid,"WAREHOUSE"),"Warehouse changed during read")
    if w.construction==id then
     assert(#result.warehouses<128,"Warehouse result limit exceeded")
     assert(inventory(w.stockList),"Warehouse stock list missing")
     result.warehouses[#result.warehouses+1]={entity=wid,construction=id,stockList=w.stockList}
    end
   end,assert(componentTypes().WAREHOUSE,"Warehouse component unavailable"))
  end
  local stations=station and {id} or listOf((group and group.stations) or (con and con.stations) or {})
  assert(#stations<=64,"Station result limit exceeded")
  for _,sid in ipairs(stations) do if not stationSeen[sid] then
   stationSeen[sid]=true;assert(getComponent(sid,"STATION"),"Station changed during read")
   local catches=listOf(api.engine.system.catchmentAreaSystem.getStationCatchables(sid,true))
   assert(#catches<=512,"Catchment result limit exceeded")
   local row={station=sid,stockLists={}};local seen={}
   for _,stockId in ipairs(catches) do
    if inventory(stockId) then
     if not seen[stockId] then seen[stockId]=true;row.stockLists[#row.stockLists+1]=stockId end
    elseif not unknownSeen[stockId] then
     unknownSeen[stockId]=true;result.unknownCatchables[#result.unknownCatchables+1]=stockId;result.complete=false
    end
   end
   table.sort(row.stockLists);result.stations[#result.stations+1]=row
  end end
  table.sort(result.inventories,function(a,b)return a.stockList<b.stockList end)
  table.sort(result.warehouses,function(a,b)return a.entity<b.entity end)
  table.sort(result.stations,function(a,b)return a.station<b.station end)
  table.sort(result.unknownCatchables)
  return result
 end
 ENGINE_COMMANDS.get_facility_inventory=true
 -- One fresh, directed native query per request; no cache or batched path search.
 commands.check_road_junction_path=function(args)
  local node,a,b=args.node,args.from_edge,args.to_edge
  assert(a~=b,"Distinct road edges required")
  local supported={BUS=true,TRUCK=true,CAR=true,TRAM=true,ELECTRIC_TRAM=true,TRAIN=true,ELECTRIC_TRAIN=true}
  assert(supported[args.mode],"Unsupported junction transport mode")
  local mode=api.type.enum.TransportMode[args.mode]
  assert(type(mode)=="number" and getComponent(node,"BASE_NODE"),"Current road node required")
  local adjacency={};for _,id in pairs(api.engine.system.streetSystem.getNodeSegments(node))do adjacency[id]=true end
  local function endpoints(id,incoming)
   local edge=getComponent(id,"BASE_EDGE")
   assert(adjacency[id] and edge and (edge.node0==node or edge.node1==node),"Edge no longer joins node")
   if args.mode=="TRAIN" or args.mode=="ELECTRIC_TRAIN" then
    assert(edge.roadType==api.type.enum.RoadType.TRACK,"Train query requires railway edges")
   end
   local net=getComponent(id,"TRANSPORT_NETWORK");assert(net,"Road transport network unavailable")
   local out={}
   for _,lane in ipairs(net.edges)do
    if lane.transportModes[mode] then
     local x,y=lane.conns[1],lane.conns[2]
     if incoming and y.entity==node and x.entity~=node then out[#out+1]=x end
     if not incoming and x.entity==node and y.entity~=node then out[#out+1]=y end
     -- Railway transport edges can be bidirectional. Absence of the native flag
     -- never grants a reverse direction; use only an explicit false value.
     if lane.forwardOnly==false then
      if incoming and x.entity==node and y.entity~=node then out[#out+1]=y end
      if not incoming and y.entity==node and x.entity~=node then out[#out+1]=x end
     end
    end
   end
   assert(#out<=32,"Directed road lanes excessive")
   return out
  end
  local from,to=endpoints(a,true),endpoints(b,false)
  local config=getComponent(node,"BASE_NODE_CONFIG");local lanes,crosswalks={},{}
  if config then
   for _,c in ipairs(config.laneConnections)do
    assert(#lanes<256,"Node lane configuration too large")
    lanes[#lanes+1]={segment0=c.segment0,segment1=c.segment1,lane0=c.lane0,lane1=c.lane1,withRoad=c.withRoad,withTram=c.withTram}
   end
   for _,id in pairs(config.crosswalks)do crosswalks[#crosswalks+1]=id end
  end
  if #from==0 or #to==0 then
   return {node=node,fromEdge=a,toEdge=b,mode=args.mode,pathFound=false,directPathVerified=false,
    steps={},laneConnections=lanes,crosswalks=crosswalks,configurationAvailable=config~=nil,
    nativeQueries=0,directedLanesAvailable=false,reason=#from==0 and "no_supported_incoming_lane" or "no_supported_outgoing_lane",
    scope="directed lane eligibility; native pathfinding not invoked"}
  end
  local path=api.engine.util.pathfinding.findPathNodeToNode(from,to,{mode})
  local steps={};local usesA,usesB=false,false;local direct=true
  for _,step in ipairs(path)do
   assert(#steps<256,"Native path exceeds result limit")
   local e=step[1];steps[#steps+1]={entity=e.entity,index=e.index}
   usesA=usesA or e.entity==a;usesB=usesB or e.entity==b
   if e.entity~=a and e.entity~=b and e.entity~=node then direct=false end
  end
  return {node=node,fromEdge=a,toEdge=b,mode=args.mode,pathFound=#steps>0,
   directPathVerified=usesA and usesB and direct,steps=steps,laneConnections=lanes,crosswalks=crosswalks,
   configurationAvailable=config~=nil,nativeQueries=1,scope="one directed junction path; not depot operation"}
 end
 ENGINE_COMMANDS.check_road_junction_path=true
 commands.check_network_junction_path=commands.check_road_junction_path
 ENGINE_COMMANDS.check_network_junction_path=true

 commands.list_facilities=function(args)
  local rows={};api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION");local cat,supported=category(c.fileName,lookup("construction",c.fileName))
   if (supported or cat=="headquarters") and (args.mine_only==false or ownerOf(id)==api.engine.util.getPlayer()) then
    rows[#rows+1]={entity=id,resource=c.fileName,category=cat,position=constructionPosition(id)}
   end
  end,componentTypes().CONSTRUCTION)
  table.sort(rows,function(a,b)return a.entity<b.entity end)
  return {items=rows,total=#rows}
 end
 local function moduleRecord(name)
  local d=lookup("module",name)
  if available(d)~=true then error("module is unavailable in the current year",0) end
  return {name=name,variant=0,metadata=d.metadata,
   updateScript={fileName=d.updateScript.fileName,params=d.updateScript.params}},d.type
 end
 local function patch(before,args)
  local p=copy(before.params);p.modules=p.modules or {};local defs={};for _,d in ipairs(before.parameters) do defs[d.key]=d end
  for k,v in pairs(args.parameters or {}) do
   local d=defs[k];if not d or not d.modifiable then error("parameter is not post-construction modifiable: "..k,0) end
   local valid=false
   if #d.numbers>0 then for _,n in ipairs(d.numbers) do if v==n then valid=true end end
   else valid=type(v)=="number" and v%1==0 and v>=1 and v<=#d.values end
   if not valid then error("parameter value outside native choices: "..k,0) end
   p[k]=v
  end
  local slots={};for _,s in ipairs(before.slots) do slots[s.id]=s end
  local touched={}
  for _,change in ipairs(args.modules or {}) do
   local id=tonumber(change.slot);local s=slots[id]
   if not s or touched[id] then error("unknown or repeated module slot",0) end;touched[id]=true
   if change.remove then error("module removal requires dependency-aware bulldozing; not supported",0) end
   if p.modules[id] and not s.replaceable then error("occupied slot is not replaceable",0) end
   local rec,typ=moduleRecord(change.resource)
   if typ~=s.type then error("module type does not match slot",0) end
   if change.variant~=nil and change.variant~=0 then error("only native default variant 0 is supported",0) end
   p.modules[id]=rec
  end
  local counts={}
  for _,m in pairs(p.modules) do local typ=lookup("module",m.name).type;counts[typ]=(counts[typ] or 0)+1 end
  for typ,cfg in pairs(before.slot_config) do
   if cfg.maxModules and cfg.maxModules>0 and (counts[typ] or 0)>cfg.maxModules then error("module limit exceeded: "..typ,0) end
  end
  return p
 end
 local function issue(mode,before,params,args,check)
  if not wallClock() then error("preview clock unavailable",0) end
  for k,t in pairs(tickets) do if wallClock()-t.created>60 then tickets[k]=nil end end
  serial=serial+1;local token=tostring(wallClock())..":"..serial
  tickets[token]={mode=mode,entity=before.entity,snapshot=canonical(before),params=params,args=copy(args),created=wallClock(),game_time=commands.get_game_state().gameTime,year=currentYear()}
  checkpoint()
  local result={preview=true,preview_token=token,expires_in_seconds=60,mode=mode,entity=before.entity,
   parameters=toPlain(params),check=check,verification="configuration_only; simulation safety unverified"}
  if args.compact==true then
   local small=compactFacility({params=params,slots={}},0,30)
   result.parameters=small.params;result.parameterModuleCount=small.moduleCount;result.parametersHasMore=small.hasMore
  end
  return result
 end
 commands.preview_facility_module=function(args)
  return commands.configure_facility({entity=args.entity,compact=args.compact,modules={{slot=args.slot,resource=args.resource}}})
 end
 commands.preview_facility_parameter=function(args)
  return commands.configure_facility({entity=args.entity,compact=args.compact,parameters={[args.key]=args.value}})
 end
 ENGINE_COMMANDS.preview_facility_module=true;ENGINE_COMMANDS.preview_facility_parameter=true
 commands.configure_facility=function(args)
  local before=inspect(args.entity)
  if not before.configurable then error("construction is not an owned configurable facility",0) end
  local p=patch(before,args)
  if canonical(p)==canonical(before.params) then return {preview=true,changed=false} end
  -- Native replacement can remove frozen street edges. Do NOT call makeProposalData on it.
  return issue("configure",before,p,args,{structural_only=true,collision_checked=false,reputation={available=false,reason="structural-only preview"},
   warning="Native replacement not previewed: removed-edge preview can assert. Strict engine validation runs once on commit."})
 end
 local function buildProposal(t)
  local a=t.args;local c=api.type.SimpleProposal.ConstructionEntity.new()
  c.fileName=t.resource;c.params=t.params;c.transf=transfAt(a.x,a.y,a.z,math.rad(a.rotation or 0));c.playerEntity=api.engine.util.getPlayer()
  if a.name then c.name=a.name end
  local p=api.type.SimpleProposal.new();p.constructionsToAdd={c};return p
 end
 local function facilityPreview(proposal)
  local check,pd=previewProposal(proposal)
  if not pd then return check end
  local ok=pcall(function()
   local ci=pd.collisionInfo
   assert(ci~=nil,"collision information unavailable")
   for _,row in pairs(ci.collisionEntities or {}) do assert(type(row.entity)=="number","invalid collision entity") end
   for _,key in ipairs({"buildingEntities","removableModules"}) do
    for _ in pairs(ci[key] or {}) do check.ok=false;check.blocked=true;check.unexpected_removals=true end
   end
   -- Native terrain clearing may remove trees. Inspect the complete model list;
   -- mixed lists, unknown entities/resources and non-tree assets remain blocked.
   for id,indices in pairs(ci.autoRemovalEntity2models or {}) do
    local models=getComponent(id,"MODEL_INSTANCE_LIST")
    local treeOnly=models~=nil;local count=0
    if models then
     for _,collection in ipairs({models.thinInstances,models.fatInstances}) do
      for _,model in ipairs(listOf(collection)) do
       count=count+1
       local name=api.res.modelRep.getName(model.modelId)
       if type(name)~="string" or name:sub(1,27)~="::/assets/vegetation/trees/" then treeOnly=false end
      end
     end
    end
    if treeOnly and count>0 then
     check.tree_removals=check.tree_removals or {}
     check.tree_removals[#check.tree_removals+1]={entity=id,indices=toPlain(indices)}
    else check.ok=false;check.blocked=true;check.unexpected_removals=true end
   end
  end)
  if not ok then check.ok=false;check.blocked=true;check.collision_data_unavailable=true end
  return check
 end
 commands.build_facility=function(args)
  local before,_,d=inspect(args.source_entity)
  if not before.cloneable then error("source must be an owned facility",0) end
  for _,k in ipairs({"x","y","z"}) do if type(args[k])~="number" or args[k]~=args[k] or math.abs(args[k])==math.huge then error("finite "..k.." is required (including explicit water elevation)",0) end end
  if args.rotation~=nil and (type(args.rotation)~="number" or args.rotation~=args.rotation or math.abs(args.rotation)==math.huge) then error("rotation must be finite",0) end
  local params=copy(before.params)
  local t={resource=before.resource,params=params,args=args}
  local check=facilityPreview(buildProposal(t))
  -- Unknown collision entities must never be silently treated as vegetation.
  if not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
  return issue("build",before,params,args,check)
 end
 -- Dedicated native HQ template; never clone or freely configure permit-gated HQ modules.
 local HQ="::/landmarks/hq/headquarter.con"
 local function headquartersState(args)
  local d=lookup("construction",HQ)
  if available(d)~=true then error("headquarters resource is unavailable",0) end
  local town=tonumber(args.town)
  if not town or not getComponent(town,"TOWN") then error("resolve a current town entity first",0) end
  local owned={}
  api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION")
   if c.fileName==HQ and ownerOf(id)==api.engine.util.getPlayer() then owned[#owned+1]=id end
  end,componentTypes().CONSTRUCTION)
  if #owned>0 then error("player already owns headquarters; relocation is not supported",0) end
  local util=ug_require("::/game_mechanics/company/company_util.tl")
  local cache=util.getConstructionDisableCacheData({{HQ,d.metadata,"Headquarters"}})
  local disabled=util.getConstructionDisableReason(HQ,d.metadata,cache)
  -- Native permission data also returns {numRemaining=n} for permitted items.
  -- Only a reason means disabled; keep the native rank/permit/cooldown checks.
  if disabled and disabled.reason~=nil then error("headquarters is locked: "..tostring(disabled.reason),0) end
  local towns=commands.get_map_info({}).towns
  local selected,nearest,best
  for _,t in ipairs(towns) do
   if t.id==town then selected=t end
   local distance=dist2d(t.position,args)
   if not best or distance<best then best=distance;nearest=t.id end
  end
  if not selected or nearest~=town or best>1000 then error("site must be within 1000 m of the selected nearest town center",0) end
  return {entity=town,resource=HQ,world=api.engine.util.getWorld(),player=api.engine.util.getPlayer(),
   town_name=selected.name,position=selected.position},d
 end
 -- Shared native parameter preparation: no preview, tickets or world commands.
 -- Keep the typed parameter table here; never reconstruct it from a JSON preview.
 prepareHeadquarters=function(args,stage)
  assert(stage==nil or type(stage)=="function","invalid headquarters stage logger")
  assert(type(args)=="table","headquarters arguments must be a table")
  for _,k in ipairs({"x","y","z"}) do roadNumber(args[k],k) end
  roadNumber(args.rotation or 0,"rotation")
  if not api.engine.terrain.isValidCoordinate(V2(args.x,args.y)) then error("headquarters is outside the map",0) end
  local before,d=headquartersState(args)
  local template=field(d,"createTemplateScript")
  if not template or template.fileName~="::/landmarks/hq/headquarter.script@createTemplateFn" then error("unrecognized headquarters native template",0) end
  local factory=ug_require("::/landmarks/hq/headquarter.script.tl")
  local native=factory.createTemplateFn(copy(template.params or {}),{})
  assert(type(native)=="table","headquarters native template must be a table")
  local modules={};local count=0
  for slot,name in pairs(native) do
   if type(slot)~="number" or slot~=slot or math.abs(slot)==math.huge or slot%1~=0 or slot<0
    or name~="::/landmarks/hq/modules/hq_main.module" then error("unrecognized headquarters root module",0) end
   local md=lookup("module",name)
   assert(md and md.metadata and md.updateScript and type(md.updateScript.fileName)=="string",
    "headquarters main module metadata/update script missing")
   modules[slot]={name=name,variant=0,metadata=md.metadata,updateScript={fileName=md.updateScript.fileName,params=md.updateScript.params}}
   count=count+1
  end
  if count~=1 then error("headquarters template must contain exactly one main module",0) end
  local params={seed=1,year=currentYear(),modules=modules}
  assert(type(params.year)=="number" and params.year==params.year and math.abs(params.year)<math.huge,
   "headquarters year must be finite")
  assert(type(params.modules)=="table" and next(params.modules),"headquarters modules missing")
  if stage then stage("native_parameters_validated");stage("construction_assignment_begin") end
  local proposal=buildProposal({resource=HQ,params=params,args=args})
  if stage then stage("construction_assignment_complete") end
  return proposal,before,params
 end
 -- Typed, bounded preview data for the directed PERSON graph audit. This is
 -- one proposal read, not pathfinding and not permission to commit a building.
 commands.preview_headquarters_access=function(args)
  local road=requireEntity(args,"road","BASE_EDGE")
  local target=getComponent(road,"BASE_EDGE")
  assert(target.roadType==api.type.enum.RoadType.STREET,"HQ frontage must be a street")
  local proposal,before=prepareHeadquarters(args)
  local context=api.type.Context.new();context.player=before.player;context.checkTerrainAlignment=true
  local pd=api.engine.util.proposal.makeProposalData(proposal,context)
  local es=pd.errorState
  local function strings(values)
   local out={};for _,v in ipairs(values) do
    assert(#out<64,"HQ preview message bound exceeded");out[#out+1]=tostring(v):sub(1,512)
   end;return out
  end
  local check={critical=es.critical,messages=strings(es.messages),infos=strings(es.infos),warnings=strings(es.warnings),collisions={}}
  for _,v in ipairs(pd.collisionInfo.collisionEntities) do
   assert(#check.collisions<256,"HQ preview collision bound exceeded");check.collisions[#check.collisions+1]=v.entity
  end
  check.clear=es.critical==false and #check.messages==0 and #check.infos==0 and #check.warnings==0 and #check.collisions==0
  local out={previewOnly=true,commitEnabled=false,nativeProposalCalls=1,road=road,check=check,networks={},links={},
   scope="typed PERSON graph for independent audit; no commit token or native path query"}
  if not check.clear then return out end
  local seen,networkCount,edgeCount={},0,0
  local function integer(v)
   assert(type(v)=="number" and v==v and math.abs(v)<math.huge and v%1==0,"Invalid HQ graph entity/index");return v
  end
  local function readNetwork(entity,net)
   integer(entity);assert(not seen[entity] and net,"Duplicate or missing HQ graph network")
   seen[entity]=true;networkCount=networkCount+1;assert(networkCount<=128,"HQ network bound exceeded")
   local row={entity=entity,edges={}}
   for i,e in ipairs(net.edges) do
    edgeCount=edgeCount+1;assert(edgeCount<=4096,"HQ graph edge bound exceeded")
    if e.transportModes[0] then
     assert(type(e.forwardOnly)=="boolean","Missing HQ lane direction")
     local a,b=e.conns[1],e.conns[2]
     row.edges[#row.edges+1]={index=i-1,from={entity=integer(a.entity),index=integer(a.index)},
      to={entity=integer(b.entity),index=integer(b.index)},forwardOnly=e.forwardOnly}
    end
   end
   out.networks[#out.networks+1]=row
  end
  for entity,net in pairs(pd.entity2tn) do readNetwork(entity,net) end
  if not seen[road] then readNetwork(road,getComponent(road,"TRANSPORT_NETWORK")) end
  local function endpoint(p)
   assert(p and p.edgeId and type(p.param)=="number" and p.param>=0 and p.param<=1,"Invalid HQ automatic link")
   return {entity=integer(p.edgeId.entity),index=integer(p.edgeId.index),param=p.param}
  end
  for _,r in ipairs(pd.tpNetLinkProposal.toAdd) do
   assert(#out.links<1024,"HQ link bound exceeded")
   out.links[#out.links+1]={from=endpoint(r.link.from),to=endpoint(r.link.to)}
  end
  return out
 end
 ENGINE_COMMANDS.preview_headquarters_access=true
 commands.build_headquarters=function(args)
  local proposal,before,params=prepareHeadquarters(args)
  local check=facilityPreview(proposal)
  if not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
  local out=issue("headquarters",before,params,args,check)
  out.resource=HQ;out.town=before.entity
  out.expansion={basis="native main module: 48 x 40 m ground texture; side slots at +/-24 m; reserve at least 100 x 100 m including access (estimate, not native validation)",automatic=false}
  return out
 end
 -- Native warehouse starter layout, mirrored from warehouse.script.lua createTemplateFn
 -- and its EncodeSlotId. Adjacent modules use the native 4-cell large-module spacing.
 -- The game exposes this factory as a .lua data() script, not an importable .tl module;
 -- requiring it directly would overwrite global data(). Never do that here.
 local WH="::/warehouses/warehouse.con"
 local WH_MODULE="::/warehouses/wh_universal.module"
 local function warehouseState(args)
  local count=args.module_count or 4
  if count~=1 and count~=4 then error("module_count must be 1 or 4",0) end
  local era=currentYear()>=1980 and "c" or (currentYear()>=1940 and "b" or "a")
  local templateName="::/warehouses/warehouse_era_"..era.."_universal.metacon"
  local d=lookup("metaConstruction",templateName)
  if available(d)~=true then error("warehouse template unavailable in the current year",0) end
  local template=field(d,"createTemplateScript")
  if not template or template.fileName~="::/warehouses/warehouse.script@createTemplateFn" or
   not template.params or template.params.initialModule~="wh_universal.module" then
   error("unrecognized native warehouse template",0)
  end
  local con=lookup("construction",WH)
  local company=ug_require("::/game_mechanics/company/company_util.tl")
  local cache=company.getConstructionDisableCacheData({{WH,con.metadata,"Warehouses"}})
  local disabled=company.getConstructionDisableReason(WH,con.metadata,cache)
  if disabled and disabled.reason~=nil then error("warehouse is locked: "..tostring(disabled.reason),0) end
  local module,typ=moduleRecord(WH_MODULE)
  if typ~="warehouse_large" then error("unrecognized warehouse module type",0) end
  local duplicates={}
  api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION")
   if c.fileName==WH then
    local p=constructionPosition(id)
    if p and dist2d(p,args)<5 then duplicates[#duplicates+1]=id end
   end
  end,componentTypes().CONSTRUCTION)
  if #duplicates>0 then error("warehouse already exists at site; inspect before building",0) end
  return {entity=api.engine.util.getWorld(),resource=WH,world=api.engine.util.getWorld(),
   player=api.engine.util.getPlayer(),template=templateName,module_count=count,module=module}
 end
 commands.build_warehouse=function(args)
  for _,k in ipairs({"x","y","z"}) do roadNumber(args[k],k) end
  roadNumber(args.rotation or 0,"rotation")
  if not api.engine.terrain.isValidCoordinate(V2(args.x,args.y)) then error("warehouse outside map",0) end
  if api.engine.terrain.isOnWater(V2(args.x,args.y))~=false then error("warehouse needs confirmed dry land",0) end
  local before=warehouseState(args)
  local modules={}
  local function add(x,y)
   local slot=10*(250000*(y+250)+(x+250))
   modules[slot]=copy(before.module)
  end
  add(0,3)
  if before.module_count==4 then add(4,3);add(0,7);add(4,7) end
  local params={seed=1,year=currentYear(),modules=modules}
  local check=facilityPreview(buildProposal({resource=WH,params=params,args=args}))
  if not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
  local out=issue("warehouse",before,params,args,check)
  out.resource=WH;out.template=before.template;out.module_count=before.module_count
  out.expected_capacity=500*before.module_count
  out.layout_basis="native warehouse starter slot (0,3); large modules spaced four 8m cells; factory encoding mirrored from installed base assets"
  out.expansion={automatic=false,basis="40x40m module collider; 4 modules plus entrance about 72x88m; reserve at least 192x192m for 16 modules and access (estimate, not upgrade preview)"}
  return out
 end
 -- Native module-free helicopter station, available from 1950.
 local HELI="::/stations/air/helipad.con"
 local function helipadState(args)
  local d=lookup("construction",HELI)
  if available(d)~=true then error("helipad unavailable in current year",0) end
  local update=field(d,"updateScript")
  if not update or update.fileName~="::/stations/air/helipad/helipad.script@updateFn" then
   error("unrecognized native helipad update script",0)
  end
  local company=ug_require("::/game_mechanics/company/company_util.tl")
  local cache=company.getConstructionDisableCacheData({{HELI,d.metadata,"Airfields"}})
  local disabled=company.getConstructionDisableReason(HELI,d.metadata,cache)
  if disabled and disabled.reason~=nil then error("helipad locked: "..tostring(disabled.reason),0) end
  api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION")
   if c.fileName==HELI then local p=constructionPosition(id)
    if p and dist2d(p,args)<5 then error("helipad already exists; inspect before building",0) end
   end
  end,componentTypes().CONSTRUCTION)
  return {entity=api.engine.util.getWorld(),resource=HELI,world=api.engine.util.getWorld(),player=api.engine.util.getPlayer()}
 end
 commands.build_helipad=function(args)
  for _,k in ipairs({"x","y","z"}) do roadNumber(args[k],k) end
  roadNumber(args.rotation or 0,"rotation")
  if not api.engine.terrain.isValidCoordinate(V2(args.x,args.y)) then error("helipad outside map",0) end
  if api.engine.terrain.isOnWater(V2(args.x,args.y))~=false then error("helipad requires confirmed dry land",0) end
  local before=helipadState(args)
  local params={seed=1,year=currentYear()}
  local check=facilityPreview(buildProposal({resource=HELI,params=params,args=args}))
  if not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
  local out=issue("helipad",before,params,args,check)
  out.resource=HELI
  out.expansion={automatic=false,basis="native 36x38m; reserve 90x90m for a second pad and access (estimate); road snap point local (0,-25)"}
  return out
 end
 -- Native helicopter station with native purchase and maintenance depot, available from 1950.
 local HELIPORT="::/stations/air/heliport.con"
 local function heliportState(args)
  local d=lookup("construction",HELIPORT)
  if available(d)~=true then error("heliport unavailable in current year",0) end
  local update=field(d,"updateScript")
  if not update or update.fileName~="::/stations/air/heliport/heliport.script@updateFn" then
   error("unrecognized native heliport update script",0)
  end
  local company=ug_require("::/game_mechanics/company/company_util.tl")
  local cache=company.getConstructionDisableCacheData({{HELIPORT,d.metadata,"Airfields"}})
  local disabled=company.getConstructionDisableReason(HELIPORT,d.metadata,cache)
  if disabled and disabled.reason~=nil then error("heliport locked: "..tostring(disabled.reason),0) end
  api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION")
   if c.fileName==HELIPORT then local p=constructionPosition(id)
    if p and dist2d(p,args)<5 then error("heliport already exists; inspect before building",0) end
   end
  end,componentTypes().CONSTRUCTION)
  return {entity=api.engine.util.getWorld(),resource=HELIPORT,world=api.engine.util.getWorld(),player=api.engine.util.getPlayer()}
 end
 commands.build_heliport=function(args)
  for _,k in ipairs({"x","y","z"}) do roadNumber(args[k],k) end
  roadNumber(args.rotation or 0,"rotation")
  if not api.engine.terrain.isValidCoordinate(V2(args.x,args.y)) then error("heliport outside map",0) end
  if api.engine.terrain.isOnWater(V2(args.x,args.y))~=false then error("heliport requires confirmed dry land",0) end
  local before=heliportState(args)
  local params={seed=1,year=currentYear(),modules={}}
  local check=facilityPreview(buildProposal({resource=HELIPORT,params=params,args=args}))
  if not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
  local out=issue("heliport",before,params,args,check)
  out.resource=HELIPORT
  out.capabilities={purchase=true,transport_mode="HELICOPTER",depot_capacity=5,maintenance_pool=4,maintenance_radius=800,basis="installed native heliport definition; verify actual depot after commit"}
  out.externalConnectionsBuilt=false
  out.expansion={automatic=false,basis="native approximately 100x108m; reserve 170x170m (estimate); extra landing slot 1000 at local (-26.8,37.6); road snap local (0,-60)"}
  return out
 end
 -- Fixed native small-airfield starter: installed airfield.script createTemplateFn
 -- with hangar=1, terminals=1. Resolve every module through current resources.
 local AIRFIELD="::/stations/air/airfield.con"
 local function airfieldState(args)
  local era=currentYear()>=1980 and "c" or (currentYear()>=1950 and "b" or "a")
  local templateName="::/stations/air/airfield_era_"..era..".metacon"
  local d=lookup("metaConstruction",templateName)
  assert(available(d)==true,"airfield template unavailable in current year")
  local template=field(d,"createTemplateScript")
  assert(template and template.fileName=="::/stations/air/airfield.script@createTemplateFn","unrecognized native airfield template")
  local con=lookup("construction",AIRFIELD)
  local update=field(con,"updateScript")
  assert(update and update.fileName=="::/stations/air/airfield.script@updateFn","unrecognized native airfield update script")
  local company=ug_require("::/game_mechanics/company/company_util.tl")
  local cache=company.getConstructionDisableCacheData({{AIRFIELD,con.metadata,"Airfields"}})
  local disabled=company.getConstructionDisableReason(AIRFIELD,con.metadata,cache)
  assert(not disabled or disabled.reason==nil,"airfield locked by native permission")
  local modules={}
  for i,name in ipairs({"af_hangar","af_main","af_terminal"}) do
   local record,typ=moduleRecord("::/stations/air/airfield/"..name..".module")
   assert(typ=="airfield_building","unrecognized airfield module type")
   modules[10001000+(i-1)*2]=record
  end
  api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION")
   if c.fileName==AIRFIELD then local pos=constructionPosition(id)
    assert(not pos or dist2d(pos,args)>=5,"airfield already exists at site; inspect before building")
   end
  end,componentTypes().CONSTRUCTION)
  return {entity=api.engine.util.getWorld(),resource=AIRFIELD,world=api.engine.util.getWorld(),
   player=api.engine.util.getPlayer(),template=templateName,modules=modules}
 end
 commands.build_airfield=function(args)
  for _,k in ipairs({"x","y","z"}) do roadNumber(args[k],k) end
  roadNumber(args.rotation or 0,"rotation")
  assert(api.engine.terrain.isValidCoordinate(V2(args.x,args.y)),"airfield outside map")
  assert(api.engine.terrain.isOnWater(V2(args.x,args.y))==false,"airfield requires confirmed dry land")
  local before=airfieldState(args)
  local params={seed=1,year=currentYear(),modules=copy(before.modules)}
  local check=facilityPreview(buildProposal({resource=AIRFIELD,params=params,args=args}))
  if not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
  local out=issue("airfield",before,params,args,check)
  out.resource=AIRFIELD;out.template=before.template
  out.layout_basis="installed native createTemplateFn: hangar=1, terminals=1; slots 10001000/10001002/10001004"
  out.externalConnectionsBuilt=false;out.serviceVerified=false
  return out
 end
 -- Bounded native water starters. Mirror installed native template slot encoding;
 -- never execute a data() asset script in the game global environment.
 local function waterScriptState(script)
  -- Native script descriptors may expose wrapper methods/opaque identities.
  -- Only the documented descriptor fields define the construction recipe.
  return {fileName=script.fileName,params=copy(script.params)}
 end
 local function waterFacilityState(args)
  local size=args.harbor_size or "small"
  assert(size=="small" or size=="large","harbor_size must be small or large")
  assert(args.kind=="harbor" or args.harbor_size==nil,"harbor_size only applies to harbor")
  local kinds={harbor={"::/stations/water/harbor_modular.con","::/stations/water/harbor_modular.script@updateFn","Harbors"},
   shipyard={"::/depots/water/water_depot.con","::/depots/water/water_depot.script@updateFn","Depots"},
   maintenance={"::/depots/water/water_maint_station.con","::/depots/water/water_maint_station.script@updateFn","Depots"}}
  local spec=kinds[args.kind];assert(spec,"water facility kind must be harbor, shipyard or maintenance")
  local d=lookup("construction",spec[1]);assert(available(d)==true,"water facility unavailable")
  local update=field(d,"updateScript")
  assert(update and update.fileName==spec[2],"unrecognized native water facility update script")
  if args.kind=="maintenance" then assert(currentYear()>=1900,"water maintenance unavailable before 1900") end
  local company=ug_require("::/game_mechanics/company/company_util.tl")
  local cache=company.getConstructionDisableCacheData({{spec[1],d.metadata,spec[3]}})
  local disabled=company.getConstructionDisableReason(spec[1],d.metadata,cache)
  assert(not disabled or disabled.reason==nil,"water facility locked by native permission")
  local modules={}
  if args.kind=="harbor" then
   local function add(x,y,face,name,typ)
    local record,actual=moduleRecord("::/stations/water/"..name..".module")
    assert(actual==typ,"unrecognized water starter module type")
    modules[1000000*(x+100)+100*(y+100)+face]=record
   end
   if size=="small" then
    -- Native createTemplateFn, smallterminals=1; no existing source required.
    for _,x in ipairs({0,-1}) do add(x,1,50,"pedestrian_entrance","pedestrian_entrance") end
    add(-1,0,53,"passenger_dock_25_25","water_module_25_25")
    add(0,-2,4,"passenger_dock_50_12","water_module_50_12")
    add(0,-3,36,"small_pier","water_pier_50_12")
   else
    -- Native createTemplateFn, largeterminals=1: one medium (SHIP) pier.
    for _,x in ipairs({1,-2,0,-1}) do add(x,1,50,"pedestrian_entrance","pedestrian_entrance") end
    add(0,-3,22,"passenger_dock_100_50","water_module_100_50")
    add(0,-4,12,"passenger_dock_100_25","water_module_100_25")
    add(0,-6,44,"medium_pier","water_pier_100_12")
   end
  else
   local template=field(d,"createTemplateScript")
   assert(template and template.fileName==spec[2]:gsub("@updateFn$","@createTemplateFn"),"unrecognized water depot template")
  end
  api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION")
   if c.fileName==spec[1] then local p=constructionPosition(id)
    assert(not p or dist2d(p,args)>=5,"water facility already exists at site; inspect before building")
   end
  end,componentTypes().CONSTRUCTION)
  return {entity=api.engine.util.getWorld(),resource=spec[1],world=api.engine.util.getWorld(),player=api.engine.util.getPlayer(),
   kind=args.kind,modules=copy(modules),update=waterScriptState(update),metadata=copy(d.metadata)}
 end
 commands.build_water_facility=function(args)
  for _,k in ipairs({"x","y","z"}) do roadNumber(args[k],k) end
  roadNumber(args.rotation or 0,"rotation")
  assert(api.engine.terrain.isValidCoordinate(V2(args.x,args.y)),"water facility outside map")
  local before=waterFacilityState(args)
  local params={seed=1,year=currentYear(),modules=copy(before.modules)}
  local check=facilityPreview(buildProposal({resource=before.resource,params=params,args=args}))
  if not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
  local out=issue("water_starter",before,params,args,check)
  out.resource=before.resource;out.waterFacilityVersion=1;out.waterFacilityFingerprintVersion=2;out.waterHarborLayoutVersion=1
  out.harborSize=args.kind=="harbor" and (args.harbor_size or "small") or nil
  out.expectedService=args.kind=="harbor" and (out.harborSize=="small" and "SMALL_SHIP passenger/cargo terminal" or "SHIP/SMALL_SHIP passenger/cargo terminal") or args.kind=="shipyard" and "purchase depot" or "maintenance pool 12, radius 1400"
  out.externalConnectionsBuilt=false;out.serviceVerified=false;out.navigationVerified=false
  return out
 end
 commands.commit_facility=function(args)
  local t=tickets[args.preview_token];tickets[args.preview_token]=nil
  checkpoint() -- consume before validation/submission, including failed commits
  if not t then error("preview expired, already consumed, or bridge reloaded; preview again",0) end
  if wallClock()-t.created>60 or wallClock()<t.created then error("preview expired",0) end
  local gameTime=commands.get_game_state().gameTime
  if currentYear()~=t.year or (t.game_time and gameTime and gameTime<t.game_time) then error("game date/session changed; preview again",0) end
  local before
  if t.mode=="headquarters" then before=headquartersState(t.args)
  elseif t.mode=="warehouse" then before=warehouseState(t.args)
  elseif t.mode=="helipad" then before=helipadState(t.args)
  elseif t.mode=="heliport" then before=heliportState(t.args)
  elseif t.mode=="airfield" then before=airfieldState(t.args)
  elseif t.mode=="water_starter" then before=waterFacilityState(t.args) else before=inspect(t.entity) end
  if canonical(before)~=t.snapshot then error("facility changed since preview; inspect and preview again",0) end
  local proposal;local existing={}
  api.engine.forEachEntityWithComponent(function(id)
   -- Native parcel rebuilding may recycle a removed construction ID in this proposal.
   -- Keep its resource identity; an unrelated old resource is not the new facility.
   local c=getComponent(id,"CONSTRUCTION")
   existing[id]=c and c.fileName or true
  end,componentTypes().CONSTRUCTION)
  if t.mode=="configure" then proposal=api.engine.util.proposal.createProposalReplaceConstruction(t.entity,t.params)
  else
   t.resource=before.resource;proposal=buildProposal(t)
   local check=facilityPreview(proposal)
   if not check.ok or #check.collisions>0 then return {built=false,blocked=true,check=check} end
  end
  if not proposal then return {built=false,reason="native proposal rejected"} end
  local out={submitted=true,built=false,verified=false,mode=t.mode}
  applyProposal(proposal,false,function(success)out.built=success==true end)
  if not out.built then out.reason="native command failed or callback pending; reconcile before retry";return out end
  local a=t.args;local pos=t.mode=="configure" and before.position or {x=a.x,y=a.y,z=a.z}
  local id=findConstructionAt(pos.x,pos.y,before.resource)
  if id and (not existing[id] or (type(existing[id])=="string" and existing[id]~=before.resource) or (t.mode=="configure" and id==t.entity)) then
   local after=inspect(id);out.entity=id;out.config=after
   local matches=true
   for slot,m in pairs(t.params.modules or {}) do
    local got=(after.params.modules or {})[slot]
    if not got or got.name~=m.name or got.variant~=m.variant then matches=false end
   end
   for k,v in pairs(t.params) do if k~="modules" and canonical(after.params[k])~=canonical(v) then matches=false end end
   for slot in pairs(after.params.modules or {}) do if not (t.params.modules or {})[slot] then matches=false end end
   out.verified=matches and after.owner==api.engine.util.getPlayer() and math.abs(after.position.x-pos.x)<0.1 and math.abs(after.position.y-pos.y)<0.1 and math.abs(after.position.z-pos.z)<0.1
   if t.mode=="water_starter" then
    out.configurationVerified=out.verified
    out.serviceVerified=false;out.navigationVerified=false;out.externalConnectionsBuilt=false
    out.acceptanceRequired="Read terminal cargo/modes or depot purchase/maintenance service, then directed navigation and shared stock; configuration alone is insufficient"
   end
   if t.mode=="headquarters" then
    out.town=tryField(function()return api.engine.system.streetConnectorSystem.getConstructionClosestTown(id) end)
    out.verified=out.verified and out.town==t.entity
   end
   if t.mode=="heliport" then
    local con=getComponent(id,"CONSTRUCTION");out.depots={};out.service_verified=false
    for _,depotId in ipairs(listOf(con.depots or {})) do
     local depot=getComponent(depotId,"VEHICLE_DEPOT")
     if depot then
      local helicopter=false
      for mode,enabled in pairs(depot.transportModes) do
       if enabled and enumName("TransportMode",mode)=="HELICOPTER" then helicopter=true end
      end
      local pool=field(depot,"maintenancePool")
      local area=field(depot,"catchmentArea");local radius=area and field(area,"radius")
      out.depots[#out.depots+1]={entity=depotId,helicopter=helicopter,maintenance_pool=pool,maintenance_radius=radius}
      if helicopter and pool==4 and radius==800 then out.service_verified=true end
     end
    end
    out.verified=out.verified and out.service_verified
    out.externalConnectionsBuilt=false
   end
   if t.mode=="warehouse" then
    local capacity,warehouseCount=0,0
    api.engine.forEachEntityWithComponent(function(wid)
     local w=getComponent(wid,"WAREHOUSE")
     if w and w.construction==id then
      warehouseCount=warehouseCount+1
      local stock=getComponent(w.stockList,"STOCK_LIST")
      if stock then for _,s in ipairs(listOf(stock.stocks)) do capacity=capacity+(s.capacity or 0) end end
     end
    end,componentTypes().WAREHOUSE)
    out.stock_capacity=capacity;out.expected_capacity=500*before.module_count
    out.verified=out.verified and warehouseCount>0 and capacity==out.expected_capacity
    out.externalConnectionsBuilt=false
   end
  end
  if args.compact==true and out.config then out.config=compactFacility(out.config,0,30) end
  out.verification="configuration_only; connectivity and long-term simulation must be checked separately"
  return out
 end
 -- Sandbox industries use the native map-editor placement pipeline, not facility cloning.
 do
  local previews,operations={},{}
  local sequence,epoch=0,tostring({})
 local checkpointWorkflow=function()end
 workflowStateBinders.industry=function(state,guiEpoch)
  assert(type(guiEpoch)=='string','workflow GUI session epoch required')
  local saved=(state:get() or {}).industryAdapter or {}
  previews=saved.epoch==guiEpoch and (saved.previews or {}) or {}
  operations=saved.operations or {};sequence=saved.serial or 0;epoch=guiEpoch
  checkpointWorkflow=function()
   local root=state:get() or {}
   root.industryAdapter={epoch=guiEpoch,previews=previews,operations=operations,serial=sequence}
   state:set(root)
  end
  return checkpointWorkflow
 end
  local function sandbox()
   assert(api.res.getBaseConfig().sandboxMode==true,"industry placement requires sandbox mode")
  end
  local function industryResource(name)
   local d=lookup("construction",name)
   assert(field(d,"isIndustry")==true,"resource is not an industry construction")
   return d
  end
  local function session()
   local s=commands.get_game_state({})
   local map=api.engine.terrain.makeMapFromGame(false,true,true,false)
   local rows,industrySet,towns={},{},{}
   for _,v in pairs(map.industries) do rows[#rows+1]=canonical({id=v.existing,resource=v.fileName,pos=toPlain(v.pos)}) end
   for _,r in ipairs(rows) do industrySet[r]=true end
   for _,v in pairs(map.towns) do towns[#towns+1]=canonical({town=v.existing,pos=toPlain(v.pos)}) end
   table.sort(towns)
   for _,r in ipairs(towns) do rows[#rows+1]=r end
   table.sort(rows)
   return {world=s.world,player=s.player,time=s.gameTime,tick=s.tickCount,map=table.concat(rows,"|"),towns=table.concat(towns,"|"),industries=industrySet},map
  end
  local function same(a,b)
   return a.world==b.world and a.player==b.player and b.time>=a.time and b.tick>=a.tick and a.map==b.map
  end
  local function prepare(args)
   sandbox();industryResource(args.resource)
   for _,k in ipairs({"x","y","rotation"}) do roadNumber(args[k] or (k=="rotation" and 0 or nil),k) end
   assert(type(args.on_water)=="boolean","on_water must be boolean")
   assert(type(args.seed)=="string" and #args.seed>0 and #args.seed<=128,"seed must be 1-128 characters")
   assert(api.engine.terrain.isValidCoordinate(V2(args.x,args.y)),"industry outside map")
   local snap,map=session();local all={}
   for _,v in pairs(map.industries) do all[#all+1]=v end
   local item=api.type.Map.Industry.new()
   item.pos=V2(args.x,args.y);item.angle=math.rad(args.rotation or 0)
   item.fileName=args.resource;item.onWater=args.on_water;item.existing=-1
   all[#all+1]=item
   -- Preserve every existing industry when using the native map-editor diff API.
   local generated=api.engine.mapgen.createIndustries(args.seed,all)
   assert(generated and #listOf(generated.toRemove)==0,"industry generation requested removals")
   local additions=listOf(generated.toAdd)
   assert(#additions==1,"native placement must produce exactly one industry")
   local info=additions[1];assert(info.fileName==args.resource,"native resource changed")
   local context=api.type.Context.new()
   local proposal=api.engine.util.proposal.createIndustryProposal(args.seed,info,context)
   if not proposal then return snap,nil,nil,{ok=false,blocked=true,reason="native industry placement rejected"} end
   assert(#listOf(proposal.toRemove)==0,"industry proposal requested removals")
   assert(next(toPlain(proposal.old2new or {}))==nil,"industry proposal requested replacements")
   for _,key in ipairs({"removedSegments","removedNodes","nodeConfigsToRemove","old2newEdgeObjects","new2oldEdgeObjects"}) do
    assert(next(toPlain(proposal.proposal[key] or {}))==nil,"industry proposal modifies existing roads")
   end
   local built=listOf(proposal.toAdd)
   assert(#built==1 and built[1].fileName==args.resource,"unexpected industry construction proposal")
   -- The script binding accepts only SimpleProposal for makeProposalData,
   -- despite its Teal signature. Rebuild from the native generator's resolved
   -- construction parameters; preview and commit this SAME proposal type.
   local simple=api.type.SimpleProposal.new()
   local ce=api.type.SimpleProposal.ConstructionEntity.new()
   ce.fileName=built[1].fileName;ce.transf=built[1].transf
   ce.params=copy(built[1].construction.params)
   ce.playerEntity=built[1].playerEntity
   simple.constructionsToAdd={ce}
   local check=facilityPreview(simple)
   local transform={}
   for i=0,3 do local v=info.transf:cols(i);transform[#transform+1]={v.x,v.y,v.z,v.w} end
   local resolved={resource=info.fileName,transform=transform,bbox=toPlain(info.bbox),streetPoint=toPlain(info.streetPoint),onWater=info.onWater,parameters=copy(ce.params)}
   return snap,simple,resolved,check,context
  end
  commands.list_industry_resources=function()
   local out={sandbox=api.res.getBaseConfig().sandboxMode==true,items={}}
   for id,name in pairs(api.res.constructionRep.getAll()) do
    local d=api.res.constructionRep.get(id)
    if field(d,"isIndustry")==true then
     local desc=field(d,"description")
     out.items[#out.items+1]={resource=name,name=field(desc,"name"),sandbox_only=true}
    end
   end
   table.sort(out.items,function(a,b)return a.resource<b.resource end)
   return out
  end
  commands.preview_industry=function(args)
   args=copy(args);if args.on_water==nil then args.on_water=false end;args.seed=args.seed or "tf3-mcp"
   local s,p,resolved,check=prepare(args)
   if not p or not check.ok or #check.collisions>0 then return {preview=true,blocked=true,check=check} end
   local clock=assert(wallClock(),"preview clock unavailable")
   for key,t in pairs(previews) do if clock-t.clock>60 then previews[key]=nil end end
   sequence=sequence+1;local token="industry:"..epoch..":"..sequence
   previews[token]={clock=clock,session=s,args=args,resolved=canonical(resolved)}
   return {preview=true,preview_token=token,expires_in_seconds=60,check=check,resolved=resolved,
    externalConnectionsBuilt=false,warning="Native preview only; roads, supply, production and long-term simulation require separate acceptance."}
  end
  local function readOperation(op)
   local s=session()
   if not same(op.session,s) then
    -- A new industry changes the fingerprint by design. Still reject reload/time regression.
    local missing=false
    for key in pairs(op.session.industries) do if not s.industries[key] then missing=true end end
    if missing or s.towns~=op.session.towns or s.world~=op.session.world or s.player~=op.session.player or s.time<op.session.time or s.tick<op.session.tick then
     return {operation_id=op.id,status="session_changed",verified=false,do_not_resubmit=true}
    end
   end
   local found={}
   api.engine.forEachEntityWithComponent(function(id)
    local c=getComponent(id,"CONSTRUCTION")
    if c.fileName==op.args.resource and not (op.existing[id] or op.existing[tostring(id)]) then
     local p=c.transf:cols(3)
     if math.abs(p.x-op.position.x)<.1 and math.abs(p.y-op.position.y)<.1 then
      local industries={}
      for _,iid in ipairs(listOf(c.industries or {})) do
       local ind=getComponent(iid,"INDUSTRY")
       if ind and ind.construction==id then industries[#industries+1]=iid end
      end
      if #industries>0 then found[#found+1]={construction=id,industries=industries,position={x=p.x,y=p.y,z=p.z}} end
     end
    end
   end,componentTypes().CONSTRUCTION)
   return {operation_id=op.id,status=#found==1 and "verified" or (op.callback==false and "rejected" or "pending_or_unconfirmed"),
    submitted=true,callback=op.callback,verified=#found==1,entities=found,do_not_resubmit=true,
    verification="industry_component_only; roads, production and simulation safety not verified"}
  end
  commands.get_industry_operation=function(args)
   local op=operations[args.operation_id]
   if not op then return {status="unknown_or_bridge_reloaded",verified=false,do_not_resubmit=true} end
   return readOperation(op)
  end
  commands.commit_industry=function(args)
   local t=previews[args.preview_token];previews[args.preview_token]=nil
   assert(t,"industry preview expired, consumed or bridge reloaded")
   local clock=assert(wallClock());assert(clock>=t.clock and clock-t.clock<=60,"industry preview expired")
   sandbox();local now=session();assert(same(t.session,now),"industry session/map changed; preview again")
   local s,proposal,resolved,check,context=prepare(t.args)
   assert(canonical(resolved)==t.resolved,"native industry layout changed; preview again")
   if not proposal or not check.ok or #check.collisions>0 then return {submitted=false,blocked=true,check=check} end
   local existing={};api.engine.forEachEntityWithComponent(function(id)existing[id]=true end,componentTypes().CONSTRUCTION)
   local pos=proposal.constructionsToAdd[1].transf:cols(3)
   local op={id=args.preview_token,session=s,args=t.args,position={x=pos.x,y=pos.y},existing=existing}
   operations[op.id]=op;checkpointWorkflow() -- Persist intent before native dispatch.
   api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal,context,false,true),function(_,success)op.callback=success==true end)
   return readOperation(op)
  end
  for _,name in ipairs({"list_industry_resources","preview_industry","commit_industry","get_industry_operation"}) do ENGINE_COMMANDS[name]=true end
 end
 for _,name in ipairs({"list_facility_resources","list_facilities","get_facility_config","configure_facility","build_facility","build_headquarters","build_warehouse","build_helipad","build_heliport","build_airfield","build_water_facility","commit_facility"}) do ENGINE_COMMANDS[name]=true end
end

-- City cargo kinds: optimistic preview, one-shot commit, independent readback.
do
 local previews, operations = {}, {}
 local serial, nonce = 0, tostring({})
 local checkpointWorkflow=function()end
 workflowStateBinders.town_cargo=function(state,guiEpoch)
  assert(type(guiEpoch)=='string','workflow GUI session epoch required')
  local saved=(state:get() or {}).town_cargoAdapter or {}
  previews=saved.epoch==guiEpoch and (saved.previews or {}) or {}
  operations=saved.operations or {};serial=saved.serial or 0;nonce=guiEpoch
  checkpointWorkflow=function()
   local root=state:get() or {}
   root.town_cargoAdapter={epoch=guiEpoch,previews=previews,operations=operations,serial=serial}
   state:set(root)
  end
  return checkpointWorkflow
 end
 local districts = {'residential','commercial','industrial'}
 local function read(town)
  assert(type(town)=='number' and town%1==0 and api.engine.entityExists(town),'invalid town')
  local t=assert(getComponent(town,'TOWN'),'entity is not a town')
  local eu=ug_require('::/scripts/entity_util.tl')
  local needs,weighted={},{}
  for i,k in ipairs(districts)do needs[k]={};weighted[k]={};for _,v in ipairs(t.cargoNeeds[i])do
   local id,weight=v[1],v[2];assert(type(id)=='number' and type(weight)=='number','invalid native cargo need pair')
   needs[k][#needs[k]+1]=id;weighted[k][#weighted[k]+1]={id,weight}
  end end
  local world=api.engine.util.getWorld()
  return {town=town,needs=needs,weighted_needs=weighted,reference=toPlain(eu.makeEntityAndRevision(town)),world=world,
   player=api.engine.util.getPlayer(),gameTime=getComponent(world,'GAME_TIME').gameTime}
 end
 local function same(a,b)
  if type(a)~=type(b)then return false end
  if type(a)~='table'then return a==b end
  for k,v in pairs(a)do if not same(v,b[k])then return false end end
  for k in pairs(b)do if a[k]==nil then return false end end
  return true
 end
 local function identity(a,b)
  -- Official entity_util.entityChanged compares generation and modification
  -- revision (num[1:2]); num[3] also advances during ordinary simulation.
  -- Preserve the full revision in receipts, but do not treat that tick as a new town.
  local ar,br=a.reference,b.reference
  local an=ar and ar.revision and ar.revision.num;local bn=br and br.revision and br.revision.num
  return a.world==b.world and a.player==b.player and b.gameTime>=a.gameTime
   and ar and br and ar.entity==br.entity and type(an)=="table" and type(bn)=="table"
   and type(an[1])=="number" and type(an[2])=="number" and an[1]==bn[1] and an[2]==bn[2]
 end
 local function normalize(values)
  assert(type(values)=='table','cargo list must be an array')
  local n=0;for k in pairs(values)do assert(type(k)=='number' and k%1==0 and k>=1 and k<=#values,'cargo list must be a dense array');n=n+1 end
  assert(n==#values,'cargo list must be a dense array')
  local all=api.res.cargoTypeRep.getAll(true);local out,seen={},{}
  for _,id in ipairs(values)do
   assert(type(id)=='number' and id%1==0 and id>0 and all[id]~=nil,'invalid cargo id (passengers excluded)')
   assert(not seen[id],'duplicate cargo id');seen[id]=true;out[#out+1]=id
  end
  return out
 end
 commands.get_town_cargo_needs=function(args)return read(args.town)end
 commands.preview_town_cargo_needs=function(args)
  local before=read(args.town);local after={};local changed=false
  assert(args.update_buildings==nil or type(args.update_buildings)=='boolean','update_buildings must be boolean')
  for _,k in ipairs(districts)do
   if args[k]~=nil then after[k]=normalize(args[k]);assert(#after[k]==#before.needs[k],'district demand count must remain unchanged');changed=true else after[k]=before.needs[k]end
  end
  assert(changed,'provide at least one district')
  serial=serial+1;local token='town-cargo:'..nonce..':'..serial
  previews[token]={before=before,after=after,clock=os.clock(),update=args.update_buildings==true}
  return {preview_token=token,town=args.town,before=before.needs,after=after,update_buildings=args.update_buildings==true,
   no_change=same(before.needs,after),validation_only=true,expires_in_seconds=60}
 end
 commands.get_town_cargo_operation=function(args)
  local op=assert(operations[args.operation_id],'unknown operation')
  local now=read(op.before.town)
  assert(identity(op.committed_context or op.before,now),'town/session changed; cannot reconcile against this world')
  op.observed=now.needs
  if same(now.needs,op.after)then op.status='verified';op.verified=true end
  return op
 end
 commands.commit_town_cargo_needs=function(args)
  local p=assert(previews[args.preview_token],'unknown or consumed preview token')
  assert(os.clock()-p.clock<=60,'preview expired')
  local now=read(p.before.town)
  assert(identity(p.before,now),'town/session changed')
  assert(same(p.before.weighted_needs,now.weighted_needs),'cargo needs changed; preview again')
  for _,op in pairs(operations)do assert(op.before.town~=now.town or op.status~='needs_reconciliation','previous operation needs reconciliation')end
  for _,k in ipairs(districts)do normalize(p.after[k])end
  local op={operation_id=args.preview_token,before=p.before,after=p.after,update_buildings=p.update,verified=false,status='needs_reconciliation'}
  operations[args.preview_token]=op;previews[args.preview_token]=nil;checkpointWorkflow()
  if same(now.needs,p.after)then op.status='verified';op.verified=true;op.no_change=true;return op end
  local needs={};for _,k in ipairs(districts)do needs[#needs+1]=p.after[k]end
  local ok,err=pcall(function()
   api.cmd.sendCommand(api.cmd.makeTownUpdateCargoNeedsCmd(now.town,needs,p.update),function(_,accepted)op.accepted=accepted==true end)
  end)
  if not ok then op.error=tostring(err)end
  -- Native updates increment the town revision; bind successful immediate readback to it.
  if op.accepted then
   local readOK,current=pcall(read,now.town)
   if readOK and current.world==now.world and current.player==now.player and current.gameTime>=now.gameTime and same(current.needs,p.after)then op.committed_context=current end
  end
  -- Callback acceptance alone does not establish mutation success.
  local success,result=pcall(commands.get_town_cargo_operation,{operation_id=args.preview_token})
  if not success then op.readback_error=tostring(result)end
  return op
 end
 for _,name in ipairs({'get_town_cargo_needs','preview_town_cargo_needs','commit_town_cargo_needs','get_town_cargo_operation'})do ENGINE_COMMANDS[name]=true end
end

-- Native resource prospecting. Read-only previews; one-use commits with native permits.
do
 local previews, operations = {}, {}
 local serial, session = 0, tostring({})
 local checkpoint=function()end
 prospectionStateBind=function(state,epoch)
  assert(type(epoch)=='string','prospection GUI session epoch required')
  local saved=(state:get() or {}).prospectionAdapter or {}
  previews=saved.epoch==epoch and (saved.previews or {}) or {}
  -- Keep unresolved operation records across GUI reloads; never clear the submission guard.
  operations=saved.operations or {};serial=saved.serial or 0;session=epoch
  checkpoint=function()
   local root=state:get() or {}
   root.prospectionAdapter={epoch=epoch,previews=previews,operations=operations,serial=serial}
   state:set(root)
  end
  return checkpoint
 end
 local function native()
  return ug_require('::/game_mechanics/company/company_util.tl'),ug_require('::/scripts/entity_util.tl')
 end
 local function read()
  local u=native();local player=api.engine.util.getPlayer();local world=api.engine.util.getWorld()
  local script=api.engine.system.gameScriptSystem.getEntityForGameScript('::/game_mechanics/company/company.gs')
  assert(script and script>=0,'native company script unavailable')
  local state=assert(u.externalGetCompanyState(player),'company state unavailable')
  return {player=player,world=world,script=script,gameTime=getComponent(world,'GAME_TIME').gameTime},state,u
 end
 local function history(player)
  local ok,result=pcall(function()
   local id=api.engine.system.gameScriptSystem.getEntityForGameScript('::/game_mechanics/notifications/notifications.gs')
   local state=assert(getComponent(id,'GAME_SCRIPT')).state;local out={}
   for notificationId,entry in pairs(assert(state.notifications,'notification history unavailable'))do
    local n=entry.notification;local p=n and n.params
    if n and n.type=='::/game_mechanics/company/company_notification_prospection.script' and p and p.companyEntity==player and not p.start then
     out[#out+1]={notification_id=notificationId,timestamp=entry.timestamp,town=p.townEntity and p.townEntity.entity,cargo=p.cargoType,
      status=p.resultEntity and 'succeeded' or 'failed',result=toPlain(p.resultEntity)}
    end
   end
   return out
  end)
  return ok and result or {},ok
 end
 local function catalog()
  local u=native();local cm=ug_require('::/game_mechanics/company/company_metadata.tl')
  local mu=ug_require('::/scripts/metadata_util.tl');local defs,rows={},{}
  local economy=api.res.economyRep.get(api.res.economyRep.find(api.res.getBaseConfig().economyId))
  for _,id in ipairs(api.res.genericRep.getAllOfType('company_exploration'))do
   local e=api.res.genericRep.get(id).data;local resource=api.res.genericRep.getName(id)
   if e.requiredTags and #e.requiredTags>0 then
    local types={}
    for name,p in pairs(economy.placementParams)do
     local matched=true
     for _,tag in ipairs(e.requiredTags)do local found=false;for _,v in ipairs(p.tags)do if tag==v then found=true end end;matched=matched and found end
     if matched then types[#types+1]=name end
    end
    table.sort(types)
    local meta=mu.constructionDesc.make({cm.constructionDesc.make({permitKey=e.permitKey or resource,perkCategory='PROSPECTION',rankAndPermits=e.rankAndPermits})})
    local cargoId=api.res.cargoTypeRep.find(e.cargoType)
    rows[#rows+1]={resource=resource,cargo=e.cargoType,cargo_id=cargoId,name=cargoId>=0 and api.res.cargoTypeRep.get(cargoId).name or e.cargoType,
     permit_key=e.permitKey or resource,industry_types=types,metadata=meta}
    defs[#defs+1]={resource,meta,resource}
   end
  end
  local cache=u.getConstructionDisableCacheData(defs)
  for _,r in ipairs(rows)do
   local reason=u.getConstructionDisableReason(r.resource,r.metadata,cache)
   r.metadata=nil;r.permit=toPlain(reason);r.available=#r.industry_types>0 and not(reason and reason.reason)
   if #r.industry_types==0 then r.unavailable_reason='No matching industry in current economy' elseif reason and reason.reason then r.unavailable_reason=reason.reason end
  end
  table.sort(rows,function(a,b)return a.resource<b.resource end)
  return rows
 end
 local function select(args,state)
  assert(type(args.town)=='number' and args.town%1==0 and getComponent(args.town,'TOWN'),'current town entity required')
  assert(type(args.resource)=='string','exact exploration resource required')
  local chosen;for _,r in ipairs(catalog())do if r.resource==args.resource then chosen=r end end
  assert(chosen,'unknown exploration resource');assert(chosen.available,'prospection unavailable: '..json.encode(chosen.permit))
  local _,eu=native();local ref=eu.makeEntityAndRevision(args.town)
  for _,p in ipairs(state.pendingProspections or {})do
   assert(not(eu.entityEquals(p.townEntity,ref)and p.cargoType==chosen.cargo),'prospection already pending for town and cargo')
  end
  return chosen,ref
 end
 commands.list_prospections=function()return {resources=catalog(),scope='native permits and economy tags; availability is rechecked at commit'}end
 commands.get_prospections=function()
  local now,state,u=read();local out={session=now,pending={},history={}}
  for _,p in ipairs(state.pendingProspections or {})do
   local elapsed=math.max(0,now.gameTime-p.initiatedTimestamp)
   out.pending[#out.pending+1]={town=p.townEntity and p.townEntity.entity,town_ref=toPlain(p.townEntity),cargo=p.cargoType,started_at=p.initiatedTimestamp,
    attempts=p.attempts,permit_key=p.permitKey,industry_types=toPlain(p.types),progress=math.min(1,elapsed/u.prospectionTimeMs),remaining_ms=math.max(0,u.prospectionTimeMs-elapsed)}
  end
  out.history,out.history_available=history(now.player);return out
 end
 commands.preview_prospection=function(args)
  local now,state,u=read();local r,ref=select(args,state);local clock=assert(wallClock(),'preview clock unavailable')
  for k,v in pairs(previews)do if clock-v.clock>60 then previews[k]=nil end end
  serial=serial+1;local token=session..':prospection:'..serial
  previews[token]={clock=clock,session=now,town=toPlain(ref),args={town=args.town,resource=args.resource},selection=table.concat({r.resource,r.cargo,r.permit_key,table.concat(r.industry_types,",")},"|")}
  return {preview=true,preview_token=token,expires_in_seconds=60,town=args.town,resource=r,maximum_duration_ms=u.prospectionTimeMs,
   placement='native selection near town; exact position and success not guaranteed',mutationAttempted=false}
 end
 local function reconcile(op)
  if op.receipt then return op.receipt end
  local now,state=read();local _,eu=native();local out={operation_id=op.id,submitted=true,verified=false,callbackAccepted=op.callbackAccepted,dispatchError=op.dispatchError}
  -- Engine Lua states may be replaced while simulation advances. Keep a portable read-only receipt.
  out.tracking_receipt={id=op.id,session=toPlain(op.session),town=toPlain(op.town),cargo=op.cargo,
   previousNotifications=toPlain(op.previousNotifications),registered=op.registered==true,started_at=op.started_at}

  if now.player~=op.session.player or now.world~=op.session.world or now.script~=op.session.script or now.gameTime<op.session.gameTime then out.status='session_changed';return out end
  for _,p in ipairs(state.pendingProspections or {})do
   if p.townEntity and eu.entityEquals(p.townEntity,op.town) and p.cargoType==op.cargo and p.initiatedTimestamp>=op.session.gameTime and (not op.started_at or op.started_at==p.initiatedTimestamp) then
    op.registered=true;op.started_at=p.initiatedTimestamp;out.tracking_receipt.registered=true;out.tracking_receipt.started_at=p.initiatedTimestamp
    out.status='pending';out.verified=true;out.started_at=p.initiatedTimestamp;return out
   end
  end
  local results,available=history(now.player);out.history_available=available
  for _,r in ipairs(results)do
   if r.notification_id and not op.previousNotifications[tostring(r.notification_id)] and r.timestamp>=op.session.gameTime and r.town==op.town.entity and r.cargo==op.cargo then
    out.status=r.status;out.result=r;out.verified=true;op.registered=true;op.receipt=out;return out
   end
  end
  out.status=op.registered and 'finished_result_unconfirmed' or 'needs_reconciliation'
  out.instruction='Do not resend. Inspect native pending tasks, result history and map; absent pending entry is not proof of success.'
  return out
 end
 commands.get_prospection_operation=function(args)
  local op=operations[args.operation_id]
  if not op and args.tracking_receipt then
   local r=args.tracking_receipt
   assert(type(r)=='table' and r.id==args.operation_id and type(r.session)=='table' and type(r.session.gameTime)=='number' and type(r.town)=='table' and type(r.town.entity)=='number' and r.town.revision~=nil and type(r.cargo)=='string' and type(r.previousNotifications)=='table','invalid tracking receipt')
   op={id=r.id,session=r.session,town=r.town,cargo=r.cargo,previousNotifications=r.previousNotifications,registered=r.registered==true,started_at=r.started_at}
  end
  assert(op,'operation unknown; supply saved tracking_receipt or inspect get_prospections without resubmitting')
  return reconcile(op)
 end
 commands.commit_prospection=function(args)
  local p=previews[args.preview_token];previews[args.preview_token]=nil
  assert(p,'preview expired, consumed or bridge reloaded')
  local clock=assert(wallClock(),'preview clock unavailable');assert(clock>=p.clock and clock-p.clock<=60,'preview expired')
  for _,op in pairs(operations)do assert(op.registered,'previous prospection needs reconciliation')end
  local now,state=read();local _,eu=native()
  assert(now.player==p.session.player and now.world==p.session.world and now.script==p.session.script and now.gameTime>=p.session.gameTime,'session changed')
  local r,ref=select(p.args,state);assert(eu.entityEquals(ref,p.town),'town reference changed')
  assert(table.concat({r.resource,r.cargo,r.permit_key,table.concat(r.industry_types,",")},"|")==p.selection,'resource or permit changed; preview again')
  local previous,available=history(now.player);assert(available,'native result history unavailable')
  local ids={};for _,v in ipairs(previous)do if v.notification_id then ids[tostring(v.notification_id)]=true end end
  local op={id=args.preview_token,session=now,town=toPlain(ref),cargo=r.cargo,previousNotifications=ids};operations[op.id]=op;checkpoint()
  local ok,err=pcall(function()
   api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd('','Companies','spawnIndustry',{companyEntity=now.player,townEntity=p.args.town,
    types=r.industry_types,permitKey=r.permit_key,cargoType=r.cargo}),function(_,success)op.callbackAccepted=success end)
  end)
  if not ok then op.dispatchError=tostring(err)end
  return reconcile(op)
 end
 for _,name in ipairs({'list_prospections','get_prospections','preview_prospection','commit_prospection','get_prospection_operation'})do ENGINE_COMMANDS[name]=true end
end

-- Native loan workflow: previews are local; only commit_loan dispatches an event.
do
	local previews, operations = {}, {}
	local serial, session = 0, tostring({})
 local checkpointWorkflow=function()end
 workflowStateBinders.loan=function(state,guiEpoch)
  assert(type(guiEpoch)=='string','workflow GUI session epoch required')
  local saved=(state:get() or {}).loanAdapter or {}
  previews=saved.epoch==guiEpoch and (saved.previews or {}) or {}
  operations=saved.operations or {};serial=saved.serial or 0;session=guiEpoch
  checkpointWorkflow=function()
   local root=state:get() or {}
   root.loanAdapter={epoch=guiEpoch,previews=previews,operations=operations,serial=serial}
   state:set(root)
  end
  return checkpointWorkflow
 end
	local loanFields = {"id","type","amount","duration","percentage","lastPayDay","timesPaid","birthDay","cooldownUntil"}
	local function cloneLoan(loan)
		local out = {}
		for _, key in ipairs(loanFields) do out[key] = loan[key] end
		return out
	end
	local function signature(loan)
		local parts = {}
		for _, key in ipairs(loanFields) do parts[#parts+1] = key .. ":" .. tostring(loan[key]) end
		return table.concat(parts, "|")
	end
	local function readLoans()
		local entity = api.engine.system.gameScriptSystem.getEntityForGameScript("::/game_mechanics/finance/loan.gs")
		if not entity or entity < 0 then error("native loan script is unavailable", 0) end
		local component = getComponent(entity, "GAME_SCRIPT")
		if not component or not component.state then error("loan state is unavailable", 0) end
		local state = component.state
		if not state.availableLoans or not state.obtainedLoans or state.freeId == nil then error("loan state is not initialized", 0) end
		local util = ug_require("::/game_mechanics/finance/loan_util.tl")
		local player = api.engine.util.getPlayer()
		local time = getComponent(api.engine.util.getWorld(), "GAME_TIME").gameTime
		local out = {player=player, world=api.engine.util.getWorld(), scriptEntity=entity, gameTime=time,
			balance=api.engine.util.finance.getPlayersBalance(player), freeId=state.freeId,
			maxObtained=util.maximalObtainableLoans, available={}, obtained={}}
		out.infiniteMoney = out.balance == nil
		for _, loan in ipairs(state.availableLoans) do out.available[#out.available+1] = cloneLoan(loan) end
		for _, loan in ipairs(state.obtainedLoans) do out.obtained[#out.obtained+1] = cloneLoan(loan) end
		return out, util
	end
	local function stateSignature(state)
		local parts = {tostring(state.player),tostring(state.world),tostring(state.scriptEntity),tostring(state.freeId)}
		for _, loans in ipairs({state.available,state.obtained}) do
			parts[#parts+1] = "list"
			for _, loan in ipairs(loans) do parts[#parts+1] = signature(loan) end
		end
		return table.concat(parts, ";")
	end
	local function findLoan(loans, key, value)
		local found
		for _, loan in ipairs(loans) do
			if loan[key] == value then
				if found then error("ambiguous native loan identity", 0) end
				found = loan
			end
		end
		if not found then error("loan or offer no longer exists; query again", 0) end
		return found
	end
	local function selectAction(state, util, args)
		if state.infiniteMoney then error("loans disabled by bridge for infinite-money mode", 0) end
		local loan, amount
		if args.action == "borrow" then
			if #state.obtained >= state.maxObtained then error("maximum outstanding loans reached", 0) end
			loan = findLoan(state.available, "type", args.offer_type)
			if loan.type == "Custom" then error("custom loan terms are not supported", 0) end
			if loan.cooldownUntil ~= nil then error("loan offer is in cooldown; wait for native refresh", 0) end
			if loan.birthDay and loan.birthDay + api.util.getDefaultYearDuration()/2 <= state.gameTime then error("loan offer expired; wait for native refresh", 0) end
			amount = loan.amount
		elseif args.action == "repay" then
			if type(args.loan_id) ~= "number" or args.loan_id < 0 or args.loan_id % 1 ~= 0 then error("repay requires an integer loan_id", 0) end
			loan = findLoan(state.obtained, "id", args.loan_id)
			amount = util.getFullLoanAndInterestPayBack(loan) -- native UI repays remaining principal only
			if state.balance < amount then error("insufficient balance to repay principal", 0) end
		else error("action must be borrow or repay", 0) end
		if type(amount) ~= "number" or amount <= 0 or amount % 1 ~= 0 or not loan.duration or loan.duration <= 0 then error("invalid native loan terms", 0) end
		return loan, amount
	end
	commands.get_loans = function()
		local state, util = readLoans()
		for _, loans in ipairs({state.available,state.obtained}) do
			for _, loan in ipairs(loans) do
				if loan.amount and loan.duration then
					loan.durationMonths = util.getDurationInMonths(loan.duration)
					local principal, interest = util.getMonthlyLoanAndInterestWithErrors(loan.amount,loan.duration,loan.percentage)
					loan.monthlyPrincipal, loan.monthlyInterest = principal, interest
					loan.monthlyPayment = principal + interest
					if loan.timesPaid ~= nil then loan.repaymentPrincipal = util.getFullLoanAndInterestPayBack(loan) end
				end
			end
		end
		state.rateMeaning = "native total-interest fraction, not an annual percentage rate"
		state.durationMeaning = "native standard accounting months; not wall-clock months"
		return state
	end
	commands.preview_loan = function(args)
		local state, util = readLoans()
		local loan, amount = selectAction(state, util, args)
		local now = wallClock()
		if not now then error("preview clock unavailable", 0) end
		for token, p in pairs(previews) do if now-p.created > 60 then previews[token]=nil end end
		serial = serial+1
		local token = session .. ":loan:" .. serial
		previews[token] = {created=now, state=stateSignature(state), gameTime=state.gameTime,
			args={action=args.action,offer_type=args.offer_type,loan_id=args.loan_id}}
		local principal, interest = util.getMonthlyLoanAndInterestWithErrors(loan.amount,loan.duration,loan.percentage)
		return {preview=true, preview_token=token, expires_in_seconds=60, action=args.action,
			loan=loan, cashChange=args.action == "borrow" and amount or -amount,
			balanceBefore=state.balance, balanceAfter=state.balance+(args.action == "borrow" and amount or -amount),
			monthlyPayment=principal+interest, durationMonths=util.getDurationInMonths(loan.duration),
			rateMeaning="native total-interest fraction, not APR", repaymentPolicy="remaining principal only, matching installed native script"}
	end
	local function reconcile(op)
		if op.receipt then return op.receipt end
		local state = readLoans()
		local out = {operation_id=op.id, action=op.action, submitted=true, verified=false,
			callbackAccepted=op.callbackAccepted, dispatchError=op.dispatchError, balanceBefore=op.balance,
			balanceNow=state.balance, expectedCashChange=op.cashChange, loan_id=op.loanId}
		if state.player ~= op.player or state.world ~= op.world or state.scriptEntity ~= op.scriptEntity or state.gameTime < op.gameTime then
			out.status="session_changed";return out
		end
		local found
		for _, loan in ipairs(state.obtained) do if loan.id == op.loanId then found=loan end end
		local recordsMatch = op.action == "repay" and found == nil
		if op.action == "borrow" then
			recordsMatch = found ~= nil and found.amount == op.loan.amount and found.duration == op.loan.duration
				and found.percentage == op.loan.percentage and found.type == op.loan.type and state.freeId == op.loanId+1
		end
		out.loanRecordMatches = recordsMatch
		out.cashMatches = state.balance ~= nil and state.balance == op.balance+op.cashChange
		out.verified = recordsMatch and out.cashMatches
		if out.verified then op.resolved=true;out.status="verified";op.receipt=out
		else out.status="needs_reconciliation" end
		out.instruction="Never resend a timed-out/unverified operation. Read loan records and journal before any further transaction."
		return out
	end
	commands.get_loan_operation = function(args)
		local op = operations[args.operation_id]
		if not op then error("operation unknown or bridge reloaded; inspect get_loans and finance journal", 0) end
		return reconcile(op)
	end
	commands.commit_loan = function(args)
		local token = args.preview_token
		if type(token) ~= "string" then error("preview_token is required", 0) end
		local preview = previews[token];previews[token]=nil
		if not preview then error("preview expired, consumed or bridge reloaded", 0) end
		for _, op in pairs(operations) do if not op.resolved then error("previous loan operation requires reconciliation", 0) end end
		local now = wallClock()
		if not now or now < preview.created or now-preview.created > 60 then error("preview expired", 0) end
		local state, util = readLoans()
		if state.gameTime < preview.gameTime or stateSignature(state) ~= preview.state then error("loan state changed; inspect and preview again", 0) end
		local loan, amount = selectAction(state, util, preview.args)
		local action = preview.args.action
		local payload
		if action == "borrow" then payload={cloneLoan(loan),cloneLoan(loan)}
		else payload={[2]=cloneLoan(loan)} end
		-- Use native accounting and loan state transitions. Never write ACCOUNT or journals directly.
		local cmd = api.cmd.makeScriptingSendEventCmd("", "Loan", action == "borrow" and "Obtain" or "Repay", payload)
		local op = {id=token,action=action,loan=loan,loanId=action == "borrow" and state.freeId or loan.id,
			player=state.player,world=state.world,scriptEntity=state.scriptEntity,gameTime=state.gameTime,
			balance=state.balance,cashChange=action == "borrow" and amount or -amount}
		operations[token]=op;checkpointWorkflow()
		local ok, err = pcall(function()
			api.cmd.sendCommand(cmd,function(_,success) op.callbackAccepted=success end)
		end)
		if not ok then op.dispatchError=tostring(err) end
		return reconcile(op)
	end
	for _, name in ipairs({"get_loans","preview_loan","commit_loan","get_loan_operation"}) do ENGINE_COMMANDS[name]=true end
end

-- Deterministic comparison of serialized native snapshots across module instances.
local function stableDataSignature(value)
 local function visit(v,depth,path)
  assert(depth<=32,"Snapshot comparison depth exceeded")
  if type(v)~="table" then
   assert(v==nil or type(v)=="string" or type(v)=="number" or type(v)=="boolean","Snapshot contains opaque data")
   return type(v)..":"..json.encode(v)
  end
  assert(v._unavailable==nil and v._unavailableFields==nil and v._truncated==nil and v["..."]~="truncated",
   "Snapshot contains unreadable native data at "..path..": "..json.encode(v._unavailableFields or v._unavailable or v._truncated or v["..."]))
  local keys={};for k in pairs(v) do assert(type(k)=="string" or type(k)=="number","Invalid snapshot key");keys[#keys+1]=k end
  table.sort(keys,function(a,b)return type(a)..tostring(a)<type(b)..tostring(b) end)
  local out={};for _,k in ipairs(keys) do out[#out+1]=visit(k,depth+1,path..".<key>").."="..visit(v[k],depth+1,path.."."..tostring(k)) end
  return "{"..table.concat(out,",").."}"
 end
 return visit(value,0,"$")
end

-- A missing documented flag is recorded explicitly, never converted to false.
-- If a future binding exposes it, its actual value participates in comparisons.
COMPONENT_RECORDS["BASE_EDGE_STREET"]="Engine.Component.BaseEdgeStreet"
RECORD_SCHEMAS["Engine.Component.BaseEdgeStreet"]={precedenceNode0="",precedenceNode1=""}
COMPONENT_RECORDS["RAILROAD_CROSSING"]="Engine.Component.RailroadCrossing"
RECORD_SCHEMAS["Engine.Component.RailroadCrossing"]={nodes={element=""},edges={element=""},typeIndex="",state="",stateTime=""}
local function networkNodeConfigSnapshot(cfg)
 if cfg==nil then return nil end
 local out=toPlain(cfg,0,nil,"Network.BaseNodeConfig")
 local flag=readField(cfg,"userModifiedLaneConnections")
 assert(flag==nil or type(flag)=="boolean","Invalid native userModifiedLaneConnections flag")
 out.userModifiedLaneConnectionsAvailability=flag==nil and "not_exposed" or "available"
 if flag~=nil then out.userModifiedLaneConnections=flag end
 return out
end

-- Native subventions (补贴任务). get_subventions reads the native game-script state;
-- accept_subvention sends the same "Subvention"/"onAccept" event as the UI button, once per uid.
-- Automation belongs to the MCP server: update() runs in several unshared Lua states and must
-- never accept on its own.
do
	local SCRIPT = "::/game_mechanics/subventions/subventions.gs"
	local MAX_ACTIVE = 5 -- MaxAvailable in base subventions.script.tl
	local LISTS = {{"proposedSubventions","Proposed"},{"activeSubventions","Active"},
		{"completedSubventions","Complete"},{"failedSubventions","Failed"}}
	local EXPECTABLE = {kind=true, toDeliver=true, target=true, upfrontMoney=true, failureMoney=true}
	local MODES = {ROAD="TRUCK", RAIL="TRAIN", WATER="SHIP", TRAM="TRAM"}
 local submitted,previews,operations={},{},{}
 local checkpoint=function()end;local sessionEpoch
 workflowStateBinders.subvention=function(state,epoch)
  local saved=(state:get() or {}).subventionAdapter or {};sessionEpoch=epoch
  submitted=saved.submitted or {};operations=saved.operations or {}
  previews=saved.epoch==epoch and (saved.previews or {}) or {}
  checkpoint=function()
   local root=state:get() or {};root.subventionAdapter={epoch=epoch,submitted=submitted,previews=previews,operations=operations};state:set(root)
  end
  return checkpoint
 end

	local function readState()
		local entity = api.engine.system.gameScriptSystem.getEntityForGameScript(SCRIPT)
		if not entity or entity < 0 then error("native subvention script is unavailable", 0) end
		local component = getComponent(entity, "GAME_SCRIPT")
		local state = component and component.state
		if not state or not state.proposedSubventions or not state.activeSubventions then
			error("subvention state is not initialized", 0)
		end
		return state, entity
	end
	local function now() return getComponent(api.engine.util.getWorld(), "GAME_TIME").gameTime end
	local function dayMs() return tryField(function() return api.util.getDefaultDayDuration() end) end
	local function yearMs() return tryField(function() return api.util.getDefaultYearDuration() end) end
	local function ref(r) return type(r) == "table" and r.entity or nil end

	local function cargoIds(d)
		local ids = {}
		for _, c in ipairs(listOf(d.cargosToDeliver)) do ids[#ids + 1] = c end
		if type(d.cargoType) == "string" then
			local id = tryField(function() return api.res.cargoTypeRep.find(d.cargoType) end)
			if id and id >= 0 then ids[#ids + 1] = id end
		end
		return ids
	end
	local function effects(list)
		local money, other = 0, {}
		for _, b in ipairs(listOf(list)) do
			local p = b.params or {}
			if b.type == "Money" then money = money + (p.amount or 0)
			else other[#other + 1] = {type=b.type, amount=p.amount, town=ref(p.townEntity)} end
		end
		return money, other
	end
	local function describeEntity(e)
		if not e then return nil end
		local industry = getComponent(e, "INDUSTRY")
		local kind = industry and "industry" or getComponent(e, "TOWN") and "town"
			or getComponent(e, "TOWN_BUILDING") and "townBuilding" or "other"
		local name = entityName(e)
		if not name and industry then name = entityName(industry.construction) end
		return {entity=e, name=name, kind=kind, exists=api.engine.entityExists(e)}
	end

	local function describe(v, status, t, dms, yms)
		local d = v.data or {}
		local kind = type(v.id) == "string" and v.id:match("subventions/([%w_]+)/") or tostring(v.id)
		local up, upOther = effects(d.upfront)
		local done, doneOther = effects(d.complete)
		local fail, failOther = effects(d.failure)
		local cargo = cargoIds(d)
		local names = {}
		for _, c in ipairs(cargo) do names[#names + 1] = tryField(function() return api.res.cargoTypeRep.getName(c) end) end
		local row = {uid=v.uid, status=status, kind=kind, resource=v.id, name=d.name, cargo=cargo, cargoNames=names,
			toDeliver=d.toDeliver, delivered=d.delivered, upfrontMoney=up, completeMoney=done, failureMoney=fail,
			otherEffects={upfront=upOther, complete=doneOther, failure=failOther},
			spawnTime=v.spawnTime, acceptedTime=v.acceptedTime, completedTime=v.completedTime,
			durationAfterAcceptMs=d.expireDuration, effectDurationMs=d.effectDuration,
			target=describeEntity(ref(d.stockListEntity) or ref(d.townEntity) or ref(d.to)),
			from=describeEntity(ref(d.from))}
		local deadline
		if status == "Proposed" and d.expireDurationProposed and d.expireDurationProposed > -1 then
			row.offerDeadline = v.spawnTime + d.expireDurationProposed
			deadline = row.offerDeadline
		elseif status == "Active" and v.acceptedTime and d.expireDuration then
			row.deadline = v.acceptedTime + d.expireDuration
			deadline = row.deadline
		end
		if deadline then
			row.remainingMs = deadline - t
			if dms and dms > 0 then row.remainingDays = math.floor(row.remainingMs / dms) end
		end
		-- Proposed: average rate over the full contract; Active: rate still needed before the deadline.
		local span = status == "Proposed" and d.expireDuration or status == "Active" and row.remainingMs or nil
		if yms and d.toDeliver and span and span > 0 then
			row.requiredPerYear = (d.toDeliver - (d.delivered or 0)) / (span / yms)
		end
		return row
	end

	local function catchables(station)
		local set = {}
		local list = tryField(function() return api.engine.system.catchmentAreaSystem.getStationCatchables(station, true) end)
		for _, e in ipairs(listOf(list)) do set[e] = true end
		return set
	end
	local function servesTarget(set, target, cargo)
		if target.kind == "industry" then return set[target.entity] == true end
		if target.kind ~= "town" then return false end
		for e in pairs(set) do
			local tb = getComponent(e, "TOWN_BUILDING")
			if tb and tb.town == target.entity and type(tb.stockList)=="number" and api.engine.entityExists(tb.stockList) and getComponent(tb.stockList,"STOCK_LIST") then
				local demand = tryField(function() return api.engine.util.stock.getCargoMaxConsumptionPerYear(tb.stockList, cargo) end)
				if (demand or 0) > 0 then return true end
			end
		end
		return false
	end
	local function sourcesIn(set, cargo)
		local out = {}
		for e in pairs(set) do
			local ind = getComponent(e, "INDUSTRY")
			if ind and type(ind.stockList)=="number" and api.engine.entityExists(ind.stockList) and getComponent(ind.stockList,"STOCK_LIST") then
				local maxP = tryField(function() return api.engine.util.stock.getCargoMaxProductionPerYear(ind.stockList, cargo) end) or 0
				if maxP > 0 then
					out[#out + 1] = {industry=e, name=entityName(e) or entityName(ind.construction), maxPerYear=maxP,
						actualPerYear=tryField(function() return api.engine.util.stock.getCargoProducedPerYear(ind.stockList, cargo) end) or 0}
				end
			end
		end
		return out
	end
	local function terminalNode(station, terminal)
		local st = getComponent(station, "STATION")
		local term = st and listOf(st.terminals)[terminal + 1]
		return term and term.vehicleNodeId, term
	end
	local function pathLength(a, b, mode)
		local steps = listOf(tryField(function() return api.engine.util.pathfinding.findPathNodeToNode({a}, {b}, {mode}) end))
		if #steps == 0 then return nil end
		local len = 0
		for _, step in ipairs(steps) do
			local s = step[1]
			local net = getComponent(s.entity, "TRANSPORT_NETWORK")
			local edge = net and listOf(net.edges)[s.index + 1]
			len = len + (edge and tryField(function() return edge.geometry.length end) or 0)
		end
		return len
	end
	local function fleet(line)
		local count, capacity, speed, carrier = 0, 0, nil, nil
		for _, v in ipairs(listOf(api.engine.system.transportVehicleSystem.getLineVehicles(line))) do
			local tv = getComponent(v, "TRANSPORT_VEHICLE")
			local parts = listOf(tv and tryField(function() return tv.transportVehicleConfig.vehicles end))
			for _, part in ipairs(parts) do
				local info = modelInfo(part.part.modelId)
				if info then
					capacity = capacity + (info.capacity or 0)
					if info.topSpeed then speed = math.min(speed or info.topSpeed, info.topSpeed) end
					carrier = carrier or info.carrier
				end
			end
			if #parts > 0 then count = count + 1 end
		end
		return count, capacity, speed, carrier
	end

	-- Which player lines already load the cargo from a producing industry and unload it at the target.
	local function assess(row, yms)
		local out = {supported=false, served=false, lines={}}
		if row.kind ~= "deliver_cargo" and row.kind ~= "deliver_cargo_town" then out.reason = "unsupported_kind"; return out end
		local cargo = row.cargo[1]
		if cargo == nil or row.target == nil or not row.target.exists then out.reason = "unknown_cargo_or_target"; return out end
		out.supported = true
		local player = api.engine.util.getPlayer()
		local counted, capacity, supplyActual, supplyMax = {}, 0, 0, 0
		for _, line in ipairs(listOf(api.engine.system.lineSystem.getLines())) do
			local comp = ownerOf(line) == player and getComponent(line, "LINE") or nil
			local custom = comp and tryField(function() return comp.customFilters end) == true
			local loading, unloading = {}, {}
			for i, s in ipairs(listOf(comp and comp.stops)) do
				local group = getComponent(s.stationGroup, "STATION_GROUP")
				local station = group and listOf(group.stations)[s.station + 1]
				if station then
					local stop = {index=i - 1, station=station, terminal=s.terminal}
					local set = catchables(station)
					local loads = not custom or tryField(function() return s.stopConfig.load[cargo + 1] end) == true
					local fraction = 1
					if custom then fraction = tryField(function() return s.stopConfig.maxLoad[cargo + 1] end) end
					-- Missing/invalid custom limits are unknown, never unrestricted capacity.
					if type(fraction) ~= "number" or fraction ~= fraction or fraction < 0 or fraction > 1 then fraction = 0 end
					stop.maxLoadFraction = fraction
					if loads and fraction > 0 then
						stop.sources = sourcesIn(set, cargo)
						if #stop.sources > 0 then loading[#loading + 1] = stop end
					end
					local _, term = terminalNode(station, s.terminal)
					local unloads = term ~= nil and tryField(function() return term.cargoUnload end) ~= false
					if unloads and servesTarget(set, row.target, cargo) then unloading[#unloading + 1] = stop end
				end
			end
			local a, b
			for _, x in ipairs(loading) do for _, y in ipairs(unloading) do
				if not a and x.index ~= y.index then a, b = x, y end
			end end
			if a then
				local count, cap, speed, carrier = fleet(line)
				cap = cap * a.maxLoadFraction
				local r = {line=line, name=entityName(line), loadStop=a.index, unloadStop=b.index, vehicles=count,
					capacityPerTrip=cap, maxLoadFraction=a.maxLoadFraction, topSpeed=speed, sources=a.sources}
				local mode = MODES[carrier or ""]
				local modeId = mode and tryField(function() return api.type.enum.TransportMode[mode] end)
				local na, nb = terminalNode(a.station, a.terminal), terminalNode(b.station, b.terminal)
				if modeId and na and nb and speed and speed > 0 then
					local there, back = pathLength(na, nb, modeId), pathLength(nb, na, modeId)
					if there and back then
						r.roundTripMeters = math.floor(there + back)
						-- +30% for acceleration, grades and junctions, plus a minute for loading
						r.roundTripSeconds = math.floor((there + back) / speed * 1.3 + 60)
						if yms then r.capacityPerYear = cap * (yms / 1000) / r.roundTripSeconds end
					else r.routeProblem = "no path between terminals" end
				end
				capacity = capacity + (r.capacityPerYear or 0)
				for _, s in ipairs(a.sources) do
					if not counted[s.industry] then
						counted[s.industry] = true
						supplyActual, supplyMax = supplyActual + s.actualPerYear, supplyMax + s.maxPerYear
					end
				end
				out.lines[#out.lines + 1] = r
			end
		end
		out.served = #out.lines > 0
		out.capacityPerYear, out.supplyActualPerYear, out.supplyMaxPerYear = capacity, supplyActual, supplyMax
		out.estimatedPerYear = math.min(capacity, supplyActual)
		if row.requiredPerYear and row.requiredPerYear > 0 then out.margin = out.estimatedPerYear / row.requiredPerYear end
		out.basis = "load-limited vehicle capacity, pathfinding round trip, actual source output; estimates only"
		return out
	end

 local function confirmAcceptance(row,player)
  if row.acceptedTime==nil or not ({Active=true,Complete=true,Failed=true})[row.status] then return end
  local sent=submitted[tostring(row.uid)]
  if not sent then return end
  -- UID alone is insufficient. Older submissions may recover identity from their operation.
  local matches=false
  if sent.player==player and sent.resource==row.resource and sent.spawnTime==row.spawnTime then matches=true end
  for _,op in pairs(operations) do
   if op.uid==row.uid and op.player==player and op.resource==row.resource and op.spawnTime==row.spawnTime then
    op.acceptanceEvidence={uid=row.uid,player=player,resource=row.resource,spawnTime=row.spawnTime,acceptedTime=row.acceptedTime,status=row.status}
    op.phase="confirmed";matches=true
   end
  end
  if matches then
   sent.resolved=true;sent.phase="confirmed"
   sent.acceptanceEvidence={uid=row.uid,player=player,resource=row.resource,spawnTime=row.spawnTime,acceptedTime=row.acceptedTime,status=row.status}
   checkpoint()
  end
 end
	commands.get_subventions = function(args)
		local state, entity = readState()
		local t, dms, yms = now(), dayMs(), yearMs()
		local out = {scriptEntity=entity, gameTime=t, dayMs=dms, yearMs=yms, maxActive=MAX_ACTIVE,
			nativePaused=state.pause == true, activeCount=#listOf(state.activeSubventions), tasks={},
			balance=tryField(function() return api.engine.util.finance.getPlayersBalance(api.engine.util.getPlayer()) end)}
		for _, l in ipairs(LISTS) do
			for _, v in ipairs(listOf(state[l[1]])) do
				local row = describe(v, l[2], t, dms, yms)
                confirmAcceptance(row,api.engine.util.getPlayer())
				if args.assess ~= false and l[2] == "Proposed" then row.assessment = assess(row, yms) end
				local op = submitted[tostring(v.uid)]
				if op then row.submission = {gameTime=op.gameTime, callbackAccepted=op.callbackAccepted, dispatchError=op.dispatchError} end
				out.tasks[#out.tasks + 1] = row
			end
		end
		return out
	end

	commands.accept_subvention = function(args)
		local uid = args.uid
		if type(uid) ~= "number" or uid % 1 ~= 0 then error("uid must be an integer from get_subventions", 0) end
		if submitted[tostring(uid)] then error("accept already submitted for this uid; inspect get_subventions and never resend", 0) end
		local state = readState()
		-- Explicit acceptance is scoped to this UID. Old contract history is not
		-- a prerequisite for accepting a different currently available offer.
		local t = now()
		local found
		for _, v in ipairs(listOf(state.proposedSubventions)) do if v.uid == uid then found = v end end
		if not found then error("subvention is not proposed (expired, declined or already accepted); query again", 0) end
		local row = describe(found, "Proposed", t, dayMs(), yearMs())
		if row.offerDeadline and row.offerDeadline < t then error("offer expired", 0) end
		if #listOf(state.activeSubventions) >= MAX_ACTIVE then error("maximum active subventions reached", 0) end
		if args.expect ~= nil then
			if type(args.expect) ~= "table" then error("expect must be an object", 0) end
			local actual = {kind=row.kind, toDeliver=row.toDeliver, target=row.target and row.target.entity,
				upfrontMoney=row.upfrontMoney, failureMoney=row.failureMoney}
			for k, v in pairs(args.expect) do
				if not EXPECTABLE[k] then error("unknown expectation: " .. tostring(k), 0) end
				if actual[k] ~= v then error("subvention terms changed: " .. k, 0) end
			end
		end
		local op = {uid=uid, gameTime=t,player=api.engine.util.getPlayer(),resource=row.resource,spawnTime=row.spawnTime,phase="dispatch_started"}
		submitted[tostring(uid)] = op
        if args.operation_id then operations[args.operation_id].phase="dispatch_started" end
        checkpoint() -- Durable uncertainty begins BEFORE touching the native command API.
		local ok, err = pcall(function()
			api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", "Subvention", "onAccept", {uid=uid}),
				function(_, success) op.callbackAccepted = success end)
		end)
		if not ok then op.dispatchError = tostring(err) end
        checkpoint()
		return {uid=uid, submitted=ok, callbackAccepted=op.callbackAccepted, dispatchError=op.dispatchError, task=row,
			instruction="The native script applies the accept on its own update. Confirm with get_subventions "
				.. "(status Active, acceptedTime set). Never resend; the bridge refuses a second accept for this uid."}
	end
 local function terms(uid)
  local state=commands.get_subventions({assess=false});local found
  for _,row in ipairs(state.tasks) do if row.uid==uid then assert(not found,"Ambiguous native UID");found=row end end
  assert(found and found.status=="Proposed","Offer is no longer proposed")
  assert(not found.offerDeadline or found.offerDeadline>=state.gameTime,"Offer expired")
  local immutable={player=api.engine.util.getPlayer(),scriptEntity=state.scriptEntity}
  for _,key in ipairs({"uid","resource","kind","cargo","toDeliver","upfrontMoney","completeMoney","failureMoney","otherEffects","spawnTime","offerDeadline","durationAfterAcceptMs","effectDurationMs","target","from"}) do immutable[key]=found[key] end
  return found,stableDataSignature(immutable)
 end
 commands.preview_subvention=function(args)
  local row,signature=terms(args.uid)
  assert(not submitted[tostring(args.uid)],"UID already submitted; read current status, never resend")
  local token="subvention:"..tostring(sessionEpoch)..":"..tostring(args.uid)..":"..tostring(wallClock())
  previews[token]={uid=args.uid,signature=signature,clock=assert(wallClock())};checkpoint()
  return {preview=true,preview_token=token,task=row,networkFeasibilityVerified=false,
   warning="Terms only; explicit user acceptance may proceed directly without a network assessment or historical contract reconciliation"}
 end
 commands.get_subvention_operation=function(args)
  local op=assert(operations[args.operation_id],"Unknown subvention operation")
  local state=commands.get_subventions({assess=false});local found
  for _,row in ipairs(state.tasks) do if row.uid==op.uid then found=row end end
  local verified=found and op.player==api.engine.util.getPlayer() and found.resource==op.resource and found.spawnTime==op.spawnTime and found.acceptedTime~=nil and (found.status=="Active" or found.status=="Complete" or found.status=="Failed") or false
  local evidence=op.acceptanceEvidence
  if not verified and evidence and op.player==api.engine.util.getPlayer() and evidence.uid==op.uid
   and evidence.player==op.player and evidence.resource==op.resource and evidence.spawnTime==op.spawnTime and evidence.acceptedTime~=nil then verified=true end
  return {operation_id=args.operation_id,uid=op.uid,verified=verified,submitted=submitted[tostring(op.uid)]~=nil,task=found,
   phase=op.phase,acceptanceEvidence=evidence,
   status=verified and "verified" or (op.phase=="rejected_before_dispatch" and op.phase or "needs_reconciliation"),verificationScope="native acceptance, not successful contract completion",do_not_resubmit=true}
 end
 commands.commit_subvention=function(args)
  local t=previews[args.preview_token];previews[args.preview_token]=nil;checkpoint()
  assert(t,"Unknown or consumed subvention preview")
  local operation={uid=t.uid,player=api.engine.util.getPlayer(),phase="prepared",gameTime=now()}
  operations[args.preview_token]=operation;checkpoint()
  local clock=assert(wallClock());assert(clock>=t.clock and clock-t.clock<=60,"Subvention preview expired")
  local _,signature=terms(t.uid);assert(signature==t.signature,"Subvention terms changed")
  local row=terms(t.uid)
  operation.resource=row.resource;operation.spawnTime=row.spawnTime;checkpoint()
  commands.accept_subvention({uid=t.uid,operation_id=args.preview_token})
  checkpoint()
  return commands.get_subvention_operation({operation_id=args.preview_token})
 end
 for _,name in ipairs({"preview_subvention","commit_subvention","get_subvention_operation"}) do ENGINE_COMMANDS[name]=true end
	for _, name in ipairs({"get_subventions","accept_subvention"}) do ENGINE_COMMANDS[name]=true end
end

commands.build_depot = function(args)
	local carrier = string.upper(args.carrier or "ROAD")
	local fileName = DEPOT_FILES[carrier]
	if fileName == nil then error("carrier must be one of ROAD, TRAM, RAIL, WATER", 0) end
	local out = placeConstruction(args, fileName, function()
		local params = { seed = math.random(1, 100000), year = currentYear() or 1900, modules = {} }
		-- Native tram depots need an explicit catenary parameter for electric vehicles.
		if carrier == "TRAM" then params.tramCatenary = 2 end
		return params
	end, { carrier = carrier })
	if out.con then
		out.depot = listOf(out.con.depots)[1]
		out.con = nil
	end
	return out
end
ENGINE_COMMANDS.build_depot = true

-- The station template the game's UI uses for a new street terminal (createTemplateFn),
-- with each module given as a full module entry (plain file names make the game throw).
do -- private street terminal template helpers
local function terminalModules(platforms, cargo)
	local function mangle(i, j, variant) return 200000 * (j + 100) + 100 * (i + 100) + variant end
	local function entry(file)
		local name = TERMINAL_DIR .. file
		local id = api.res.moduleRep.find(name)
		if id == nil or id < 0 then error("module not found: " .. name, 0) end
		local desc = api.res.moduleRep.get(id)
		return { name = name, variant = 0, metadata = desc.metadata,
			updateScript = { fileName = desc.updateScript.fileName, params = desc.updateScript.params } }
	end
	local platformFile = cargo and "cargo_platform.module" or "passenger_platform.module"
	local variant = cargo and 1 or 0
	local modules = {}
	local columns = { 0 }
	if platforms >= 2 then columns[#columns + 1] = -1 end
	if platforms >= 3 then columns[#columns + 1] = 1; columns[#columns + 1] = -2 end
	for _, i in ipairs(columns) do
		modules[mangle(i, 0, variant)] = entry(platformFile)
		modules[mangle(i, 1, variant)] = entry(platformFile)
	end
	modules[mangle(55, 0, 3)] = entry("entrance_exit.module")
	return modules
end

commands.build_station = function(args)
	local platforms = math.max(1, math.min(3, math.floor(tonumber(args.size) or 1)))
	local cargo = args.cargo == true
	local out = placeConstruction(args, TERMINAL_CON, function()
		return { seed = math.random(1, 100000), year = currentYear() or 1900, modules = terminalModules(platforms, cargo) }
	end, { kind = cargo and "cargo" or "passenger", size = platforms })
	if out.con then
		for _, s in ipairs(listOf(out.con.stations)) do
			local g = stationGroupOfStation(s)
			if g then out.stationGroup = g; out.name = entityName(g); break end
		end
		out.con = nil
	end
	return out
end
ENGINE_COMMANDS.build_station = true
end

do -- private rail station template helpers
local RAIL_STATION = "::/stations/rail/modular_station/modular_station.con"
local RAIL_DIR = "::/stations/rail/modular_station/"
local function railModule(name)
	local id = api.res.moduleRep.find(name)
	if not id or id < 0 then error("rail station module unavailable: " .. name, 0) end
	local desc = api.res.moduleRep.get(id)
	return { name = name, variant = 0, metadata = desc.metadata,
		updateScript = { fileName = desc.updateScript.fileName, params = desc.updateScript.params } }
end

-- Official modular station slot layout: 40 m modules, paired tracks with cargo platforms.
local function cargoRailModules(tracks, length, specialization, year)
	local era = year >= 1990 and "c" or year >= 1950 and "b" or "a"
	local suffix = specialization == "universal" and "" or "_" .. specialization
	local span = length / 40 - 1
	local first, last = -math.floor(span / 2), math.ceil(span / 2)
	local modules = {}
	local function column(base, col, name)
		for j = first, last do modules[base + 1000 * col + 10 * j] = railModule(name) end
	end
	local platform = RAIL_DIR .. "platform_cargo_era_" .. era .. suffix .. ".module"
	local track = "::/trainstation___/infrastructure/track/simple/simple.street_template"
	column(6400000, 0, platform)
	local columns = { 2, 3, 6, 7 }
	for n = 1, tracks do
		column(8400000, columns[n], track)
		if n % 2 == 0 then column(6400000, columns[n] + 1, platform) end
	end
	modules[3400000 + (span % 2 == 1 and 20 or 0)] = railModule(RAIL_DIR .. "main_building_" .. (tracks < 3 and "1" or "2") .. "_cargo.module")
	return modules
end

-- Minimal native through passenger layout: 5 m platform columns, stairs and
-- era-specific roofs/main building; optional side wings are omitted.
local function passengerRailModules(tracks,length,year)
 local era=year>=1990 and "c" or year>=1950 and "b" or "a"
 local span=length/40-1;local first,last=-math.floor(span/2),math.ceil(span/2)
 local center=math.floor(span/2)+first;local modules={}
 local function platform(col)
  for j=first,last do
   local offset=1000*col+10*j
   modules[7400000+offset]=railModule(RAIL_DIR.."platform_passenger_era_"..era..".module")
   if j==center or (span>3 and (j==first+1 or j==last-1)) then
    modules[10800000+offset]=railModule(RAIL_DIR.."addon_platform_passenger_stairs_era_"..era..".module")
   end
   if (j~=first and j~=last) or span<=3 then
    modules[10400000+offset]=railModule(RAIL_DIR.."platform_passenger_roof_era_"..era..".module")
   end
  end
 end
 platform(0)
 local columns={1,2,4,5}
 for n=1,tracks do
  for j=first,last do modules[8400000+1000*columns[n]+10*j]=railModule("::/trainstation___/infrastructure/track/simple/simple.street_template") end
  if n%2==0 then platform(columns[n]+1) end
 end
 modules[3400000+(span%2==1 and 20 or 0)]=railModule(RAIL_DIR.."main_building_"..(tracks<3 and "1" or "2").."_era_"..era..".module")
 return modules
end

commands.build_rail_station = function(args)
	local x, y = roadNumber(args.x, "x"), roadNumber(args.y, "y")
	if not api.engine.terrain.isValidCoordinate(V2(x,y)) then error("station is outside the map", 0) end
	local tracks = roadNumber(args.tracks == nil and 2 or args.tracks, "tracks", 1, 4)
	if tracks % 1 ~= 0 then error("tracks must be an integer", 0) end
	local length = roadNumber(args.length == nil and 160 or args.length, "length")
	if not ({[80]=true,[120]=true,[160]=true,[240]=true,[320]=true})[length] then error("length must be 80, 120, 160, 240 or 320 metres", 0) end
	local rotation = roadNumber(args.rotation == nil and 0 or args.rotation, "rotation") % 360
	local specialization = args.specialization or "universal"
	if args.cargo~=nil and type(args.cargo)~="boolean" then error("cargo must be boolean",0) end
	local cargo=args.cargo~=false
	if not cargo and specialization~="universal" then error("Passenger rail station cannot have cargo specialization",0) end
	if not ({universal=true,liquid=true,bulk=true,flatbed=true,goods=true})[specialization] then error("invalid cargo specialization", 0) end
	for _,key in ipairs({"preview", "allow_collisions"}) do
		if args[key] ~= nil and type(args[key]) ~= "boolean" then error(key .. " must be boolean", 0) end
	end
	local year = currentYear() or 1900
	-- Do not use connectEntrance: a mixed rail/road construction has multiple entrances.
	local placement = {x=x,y=y,rotation=rotation,connect=false,preview=args.preview ~= false,
		allow_collisions=args.allow_collisions == true,name=args.name}
	local out = placeConstruction(placement, RAIL_STATION, function()
		return {seed=1,year=year,modules=cargo and cargoRailModules(tracks,length,specialization,year) or passengerRailModules(tracks,length,year)}
	end, {carrier="RAIL",kind=cargo and "cargo" or "passenger",tracks=tracks,length=length,specialization=specialization,
		preview=placement.preview,externalConnectionsBuilt=false})
	if out.con then
		local con = out.con
		out.stations, out.stationGroups = listOf(con.stations), {}
		local groups = {}
		for _,station in ipairs(out.stations) do
			local group = stationGroupOfStation(station)
			if group and not groups[group] then groups[group]=true;out.stationGroups[#out.stationGroups+1]=group end
		end
		out.railPorts, out.roadPorts = {}, {}
		local frozen, seen = {}, {}
		for _,n in ipairs(listOf(con.frozenNodes)) do frozen[n]=true end
		for _,e in ipairs(listOf(con.frozenEdges)) do
			local be = getComponent(e, "BASE_EDGE")
			if be then
				for _,n in ipairs({be.node0,be.node1}) do
					if not frozen[n] and not seen[n] then
						seen[n]=true
						local ports = be.roadType == api.type.enum.RoadType.TRACK and out.railPorts or out.roadPorts
						ports[#ports+1]={node=n,edge=e,position=roundPos(nodePosition(n)),
							tangent=toPlain(be.node0 == n and be.tangent0 or be.tangent1)}
					end
				end
			end
		end
		out.verified = #out.stations > 0 and #out.railPorts > 0
		out.con = nil
	elseif out.built then
		out.verified = false
		out.verificationWarning = "construction command succeeded but station entity could not be located; inspect before retrying"
	end
	return out
end
ENGINE_COMMANDS.build_rail_station = true
end


------------------------------------------------------------------------------
-- street stops (edge-object constructions placed on a street segment)

do -- private roadside stop geometry helpers
local STOP_KINDS = { "new", "mid", "old" }

local function pickStopConstruction(kind, twoSided)
	local year = currentYear() or 1900
	local suffix = twoSided and "_twosided" or ""
	local explicit = kind ~= nil and kind ~= "auto"
	for _, k in ipairs(explicit and { kind } or STOP_KINDS) do
		local name = "::/stations/street/small_stops/small_" .. k .. suffix .. ".con"
		local id = api.res.constructionRep.find(name)
		if id ~= nil and id >= 0 then
			if explicit then return name end
			local av = tryField(function() return api.res.constructionRep.get(id).availability end)
			local from = av and tryField(function() return av.yearFrom end) or 0
			local to = av and tryField(function() return av.yearTo end) or 0
			if (from == 0 or from <= year) and (to == 0 or to >= year) then return name end
		end
	end
	error("no street stop available for year " .. year, 0)
end

local function hermite(be, t)
	local p0, p1, t0, t1 = be.position0, be.position1, be.tangent0, be.tangent1
	local t2, t3 = t * t, t * t * t
	local h00, h10, h01, h11 = 2 * t3 - 3 * t2 + 1, t3 - 2 * t2 + t, -2 * t3 + 3 * t2, t3 - t2
	return {
		x = h00 * p0.x + h10 * t0.x + h01 * p1.x + h11 * t1.x,
		y = h00 * p0.y + h10 * t0.y + h01 * p1.y + h11 * t1.y,
		z = h00 * p0.z + h10 * t0.z + h01 * p1.z + h11 * t1.z,
	}
end

local function closestParam(be, point)
	local best, bestD = 0.5, nil
	for i = 0, 40 do
		local t = i / 40
		local d = dist2d(hermite(be, t), point)
		if bestD == nil or d < bestD then best, bestD = t, d end
	end
	return best, bestD
end

local function nearestStreetEdge(x, y, radius)
	local best, bestD, bestT
	for _, e in ipairs(listOf(api.engine.util.octree.findEntitiesInCircle(V2(x, y), radius, componentTypes().BASE_EDGE))) do
		local be = getComponent(e, "BASE_EDGE")
		if be and be.roadType == api.type.enum.RoadType.STREET and constructionOfEdge(e) == nil then
			local t, d = closestParam(be, { x = x, y = y })
			if bestD == nil or d < bestD then best, bestD, bestT = e, d, t end
		end
	end
	return best, bestT
end

local function makeStopProposal(edgeEntity, be, tplName, tpl, param, left, model, name)
	-- Like the official electrify task: reuse the existing component wholesale. Building the
	-- component field by field makes the game assert when the old segment is removed.
	local edge = api.type.SegmentAndEntity.new()
	edge.entity = -1
	edge.type = 0
	edge.comp = api.engine.getComponent(edgeEntity, api.type.ComponentType.BASE_EDGE)
	pcall(function() edge.streetEdge = api.engine.getComponent(edgeEntity, api.type.ComponentType.BASE_EDGE_STREET) end)
	-- Native edge-object IDs are reserved separately from new road/node IDs.
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
	-- Replacing a segment also replaces every endpoint reference to it, including crosswalks.
	local configs, removed = {}, {}
	for _, node in ipairs({ be.node0, be.node1 }) do
		local old = getComponent(node, "BASE_NODE_CONFIG")
		if old == nil then
			-- New free road ends normally have no explicit lane configuration.
			-- Omit only a verified unfrozen degree-one end; never erase a junction config.
			local segments = listOf(api.engine.system.streetSystem.getNodeSegments(node))
			assert(getComponent(node, "BASE_NODE") and #segments == 1 and segments[1] == edgeEntity
				and not isFrozenStreetNode(node), "Missing endpoint lane configuration outside a free road end")
		else
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
	end
	p.streetProposal.nodeConfigsToAdd, p.streetProposal.nodeConfigsToRemove = configs, removed
	return p
end

commands.build_street_stop = function(args)
	-- Legacy experimental mode never bypasses validation.
	if args.experimental == true then
		return { built = false, supported = false, mutationAttempted = false,
			code = "street_stop_apply_unavailable", hint = "Use preview=false with mandatory topology validation; experimental bypass is disabled." }
	end
	if args.kind ~= nil and args.kind ~= "auto" and args.kind ~= "old" and args.kind ~= "mid" and args.kind ~= "new" then error("invalid stop kind", 0) end
	if args.side ~= nil and args.side ~= "left" and args.side ~= "right" then error("side must be left or right", 0) end
	local edgeEntity, param = tonumber(args.edge), tonumber(args.param)
	if edgeEntity == nil then
		local x, y = tonumber(args.x), tonumber(args.y)
		if x == nil or y == nil then error("give 'edge' or 'x' and 'y'", 0) end
		local t
		edgeEntity, t = nearestStreetEdge(x, y, tonumber(args.radius) or 50)
		if edgeEntity == nil then error("no street within reach of (" .. x .. ", " .. y .. ")", 0) end
		param = param or t
	end
	local be = getComponent(edgeEntity, "BASE_EDGE")
	if be == nil then error("edge " .. edgeEntity .. " is not a street segment", 0) end
	if be.roadType ~= api.type.enum.RoadType.STREET then error("edge " .. edgeEntity .. " is not a street", 0) end
	if constructionOfEdge(edgeEntity) then error("edge " .. edgeEntity .. " belongs to a construction", 0) end
	if #listOf(be.objects) > 0 then
		error("edge " .. edgeEntity .. " already has stops or signals; pick another segment (see find_nearby)", 0)
	end
	local tplName, tpl = resolveStreetTemplate(be.roadTemplate)
	local model = pickStopConstruction(args.kind, args.two_sided == true)
	local name = type(args.name) == "string" and args.name or nil

	param = param or 0.5
	if param ~= param or param < 0.15 or param > 0.85 then error("param must be between 0.15 and 0.85", 0) end
	local left = args.side == "left"
	local proposal = makeStopProposal(edgeEntity, be, tplName, tpl, param, left, model, name)
	local check, pd = previewProposal(proposal)
	local tn = pd and pd.entity2tn and pd.entity2tn[-1] or nil
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
	check.preview = true
	check.built = false
	check.applySupported = true
	check.mutationAttempted = false
	check.edge, check.model, check.param = edgeEntity, model, param
	check.position = roundPos(hermite(be, param))
	check.side = left and "left" or "right"
	check.twoSided = args.two_sided == true
	check.hint = "Terminal topology checked; preview=false submits one strict proposal."
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
	end
	return check
end
ENGINE_COMMANDS.build_street_stop = true
end

------------------------------------------------------------------------------
-- bulldoze

-- Failed native stop construction can leave an EDGE_OBJECT without a parent road
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

commands.bulldoze = function(args)
	local entity = requireEntity(args, "entity")
	local sc = api.engine.system.streetConnectorSystem
	local target, proposal, what = entity, nil, nil
	local function owner(fn) local c = tryField(fn); if c ~= nil and c >= 0 then return c end end
	if getComponent(entity, "VEHICLE_DEPOT") then
		target = owner(function() return sc.getConstructionEntityForDepot(entity) end) or entity
	elseif getComponent(entity, "STATION_GROUP") then
		local first = listOf(getComponent(entity, "STATION_GROUP").stations)[1]
		target = first and owner(function() return sc.getConstructionEntityForStation(first) end) or first or entity
	elseif getComponent(entity, "STATION") then
		target = owner(function() return sc.getConstructionEntityForStation(entity) end) or entity
	end
	if getComponent(target, "EDGE_OBJECT") then
		error("roadside stops can't be removed by script yet; bulldoze it in the game", 0)
	elseif getComponent(target, "CONSTRUCTION") then
		proposal = api.engine.util.proposal.createProposalRemove(target, api.type.Context.new())
		what = "construction " .. target
	elseif getComponent(target, "BASE_EDGE") then
		proposal = api.engine.util.proposal.makeSegmentsRemoveProposal({ target })
		what = "street segment " .. target
	else
		error("entity " .. entity .. " is not a construction, depot, station or street segment", 0)
	end
	if proposal == nil then error("the game refused to plan removing " .. what, 0) end
	local out = { entity = entity, removed = what, done = false }
	applyProposal(proposal, true, function(success) out.done = success end)
	out.done = out.done and not api.engine.entityExists(target)
	return out
end
ENGINE_COMMANDS.bulldoze = true

-- Throttle by wall clock when os.clock exists, otherwise by update count.
local function due(last, interval)
	local now = wallClock()
	if now == nil then
		return (updateCount - last) >= math.max(1, math.floor(interval * 5)), updateCount
	end
	return (now - last) >= interval, now
end

-- Names of every global in this Lua state, to discover what each state exposes.
local function globalNames()
	local names = {}
	for k in pairs(_G) do names[#names + 1] = tostring(k) end
	table.sort(names)
	return table.concat(names, ",")
end

-- The engine runs update() from a pool of Lua states (one per "Sim Pool" worker) that
-- do not share module state and have no app module. The single GUI state (guiUpdate)
-- has app.saveUserdata/loadUserdata, so it runs the request loop; the others stay idle.
local function bridgeTick(dt, stateLabel, state)
	updateCount = updateCount + 1

	if not startedLogged then
		startedLogged = true
		probe.state = stateLabel
		log("started in " .. stateLabel .. " state, probe:", json.encode(probe))
		if stateLabel == "gui" then log("gui globals:", globalNames()) end
	end
	-- only the single GUI state serves requests; the engine pool states must stay idle
	if stateLabel ~= "gui" or not transportAvailable() then return end
	if not transportLogged then
		transportLogged = true
		probe.state = stateLabel
		-- sample file so the external side can verify the on-disk format
		local okW, errW = writeMessage("probe", json.encode(probe))
		local okR, errR = pcall(app.loadUserdata, USERDATA_DIR, "probe")
		log("userdata transport in " .. stateLabel .. " state:",
			"save=" .. tostring(okW) .. (errW and (" (" .. errW .. ")") or ""),
			"load=" .. tostring(okR) .. " -> " .. (okR and type(errR) or tostring(errR)),
			"saveUserdata=" .. describe(app.saveUserdata),
			"folder=" .. tostring(userdataFolder()))
	end

	local okAll, err = pcall(function()
		local pollDue, now = due(lastPoll, POLL_INTERVAL)
		if pollDue then
			lastPoll = now
			pollRequest()
			collectEngineResponses(state)
		end
		local hbDue, now2 = due(lastHeartbeat, HEARTBEAT_INTERVAL)
		if hbDue then
			lastHeartbeat = now2
			writeHeartbeat(dt)
		end
	end)
	if not okAll then
		lastError = tostring(err)
		log("update error:", lastError)
	end
end

-- Read-only UI fallback: explicit allowlist, bounded request ledger, framed logs.
-- Independent of userdata transport; never evaluates input as Lua.
local uiReadRequests, uiReadCount = {}, 0
local uiReadAllowed = {
	get_game_state={}, get_finances={}, get_map_info={}, list_towns={limit="limit"},
	list_lines={limit="limit",mine_only="bool"}, list_vehicles={limit="limit",mine_only="bool"},
	list_stations={limit="limit",mine_only="bool"}, list_depots={limit="limit",mine_only="bool"},
	list_vehicle_models={limit="limit",year="year",carrier="carrier",include_unavailable="bool"},
}
local uiReadOrder = {}
local function handleUiRead(text, continualRead)
	if type(text) ~= "string" or #text > 512 then return "Invalid request" end
	local id, cmd = text:match("^([0-9a-f]+) ([a-z_]+)$")
	local rawArgs
	if not id then id,cmd,rawArgs=text:match("^([0-9a-f]+) ([a-z_]+) (.+)$") end
	if not id or #id ~= 32 then return "Expected request ID and command" end
	if not uiReadAllowed[cmd] then return "Read-only command not allowed" end
	local args = {}
	if rawArgs then
		if not rawArgs:match("^%s*{") then return "Arguments must be an object" end
		args=json.decode(rawArgs)
		if type(args)~="table" then return "Invalid arguments JSON" end
	end
	for key,value in pairs(args) do
		local kind=uiReadAllowed[cmd][key]
		local valid=(kind=="bool" and type(value)=="boolean")
			or ((kind=="limit" or kind=="year") and type(value)=="number" and value%1==0
				and value>=1 and value<=(kind=="limit" and 500 or 9999))
			or (kind=="carrier" and type(value)=="string" and
				({ROAD=true,RAIL=true,TRAM=true,WATER=true,AIR=true})[value])
		if not valid then return "Invalid or unsupported argument: "..tostring(key) end
	end
	if uiReadRequests[id] then return "Duplicate request; inspect existing log" end
	if continualRead and uiReadCount>=256 then
		local oldest=table.remove(uiReadOrder,1)
		if oldest then uiReadRequests[oldest]=nil;uiReadCount=uiReadCount-1 end
	end
	if uiReadCount >= 256 then return "Session request limit reached" end
	uiReadRequests[id] = true
	uiReadOrder[#uiReadOrder+1]=id
	uiReadCount = uiReadCount + 1
	local ok, value = pcall(commands[cmd], args)
	local response = {id=id, cmd=cmd, ok=ok}
	if ok then response.result=value else response.error=tostring(value) end
	local encodedOk, encoded = pcall(json.encode, response)
	if not encodedOk or #encoded > 65536 then
		ok=false
		encoded=json.encode({id=id,cmd=cmd,ok=false,error=encodedOk and "Response too large" or "Response encoding failed"})
	end
	local payload = hexEncode(encoded)
	local total = math.max(1, math.ceil(#payload / 1500))
	for part=1,total do
		print("[TNJ_UI_READ_V1] id="..id.." part="..part.." total="..total.." hex="..payload:sub((part-1)*1500+1,part*1500))
	end
	return ok and "Result logged" or "Error logged"
end

-- Small, fixed survey for initial UI construction acceptance; never changes terrain.
commands.survey_build_site=function(args)
 local x=roadNumber(args.x,"x");local y=roadNumber(args.y,"y")
 local points={};local low,high
 for _,dy in ipairs({-40,0,40}) do for _,dx in ipairs({-40,0,40}) do
  local p=V2(x+dx,y+dy)
  assert(api.engine.terrain.isValidCoordinate(p),"survey extends outside map")
  local z=roadNumber(api.engine.terrain.getHeightAt(p),"terrain height")
  low=low and math.min(low,z) or z;high=high and math.max(high,z) or z
  points[#points+1]={x=x+dx,y=y+dy,z=z,on_water=api.engine.terrain.isOnWater(p)}
 end end
 return {points=points,center=points[5],height_range=high-low,spacing=40,
  basis="nine surface samples; not a collision or full-footprint preview"}
end
ENGINE_COMMANDS.survey_build_site=true

-- UI road requests use one-shot short-lived previews; the original file API stays unchanged.
do
 local previews,serial={},0
 local checkpoint=function()end
 workflowStateBinders.road=function(state,epoch)
  assert(type(epoch)=="string","Road GUI session epoch required")
  local saved=(state:get() or {}).uiRoadAdapter or {}
  previews=saved.epoch==epoch and (saved.previews or {}) or {}
  serial=saved.serial or 0
  checkpoint=function()
   local root=state:get() or {}
   root.uiRoadAdapter={epoch=epoch,previews=previews,serial=serial}
   state:set(root)
  end
  checkpoint()
  return checkpoint
 end
 local function endpointSignature(point)
  if not point.node then return "coordinate" end
  local node=getComponent(point.node,"BASE_NODE")
  assert(node,"Road endpoint was removed")
  local p=node.position
  local edges={}
  for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(point.node))) do
   local e=getComponent(id,"BASE_EDGE")
   assert(e,"Road endpoint edge was removed")
   edges[#edges+1]=table.concat({id,e.node0,e.node1,tostring(e.roadTemplate)},":")
  end
  table.sort(edges)
  return table.concat({p.x,p.y,p.z,table.concat(edges,",")},"|")
 end
 local function roadPreviewAllowed(result)
  return result.ok == true and result.buildable == true and result.commitSupported ~= false
   and not result.critical and not result.blocked and not result.placementBlocked
   and next(result.collisions or {}) == nil
 end
 commands.preview_road=function(args)
  local now=wallClock();assert(now,"Road preview requires a monotonic clock")
  local request={start=args.start,["end"]=args["end"],street_type=args.street_type,preview=true,snap_radius=0,allow_collisions=false}
  local signatures={endpointSignature(request.start),endpointSignature(request["end"])}
  local result=commands.build_road(request)
  result.preview=true
  if roadPreviewAllowed(result) then
   serial=serial+1
   local token="ui-road:"..terrainEpoch..":"..serial
   previews[token]={args=request,signatures=signatures,created=now}
   result.preview_token=token
   checkpoint()
  end
  return result
 end
 commands.commit_road=function(args)
  local record=previews[args.preview_token]
  previews[args.preview_token]=nil -- consume before validation or native dispatch
  checkpoint()
  assert(record,"Unknown or consumed road preview; do not retry")
  local now=wallClock()
  assert(now and now>=record.created and now-record.created<=60,"Road preview expired")
  assert(endpointSignature(record.args.start)==record.signatures[1] and endpointSignature(record.args["end"])==record.signatures[2],"Road endpoints changed; investigate again")
  local check=commands.build_road(record.args)
  assert(roadPreviewAllowed(check),"Road preview no longer buildable")
  record.args.preview=false
  return commands.build_road(record.args)
 end
end


-- Bounded native network construction. No implicit junction rewrites, bridge/tunnel guesses,
-- auto repair or pathfinding fan-out. Geometry receipt is distinct from service access.
do
 local previews,serial={},0;local epoch,requestId;local operations={};local checkpoint=function()end
 workflowStateBinders.network=function(state,session,id)
  local saved=(state:get() or {}).uiNetworkAdapter or {};epoch=session;requestId=id
  previews=saved.epoch==session and (saved.previews or {}) or {};serial=saved.serial or 0;operations=saved.operations or {}
  checkpoint=function()
   local root=state:get() or {};root.uiNetworkAdapter={epoch=epoch,previews=previews,serial=serial,operations=operations};state:set(root)
  end
  return checkpoint
 end
 commands.list_network_templates=function(args)
  local ids={};for id,name in pairs(api.res.streetTemplateRep.getAll()) do
   if not args.search or name:find(args.search,1,true) then ids[#ids+1]=id end
  end;table.sort(ids)
  local offset,limit=args.offset or 0,args.limit or 30;local out={}
  for i=offset+1,math.min(#ids,offset+limit) do
   local id=ids[i];local tpl=api.res.streetTemplateRep.get(id)
   out[#out+1]={id=id,resource=api.res.streetTemplateRep.getName(id),roadType=enumName("RoadType",tpl.roadType),
    catenaryAdd=tpl.catenaryAdd,catenaryRemove=tpl.catenaryRemove,transportModes=toPlain(tpl.transportModesStreet)}
  end
  return {items=out,total=#ids,offset=offset,hasMore=offset+#out<#ids}
 end

 -- Opt-in degree-two road branches: add the branch AND its complete node
 -- configuration in one proposal. Never mutate a live component or clear it
 -- as a preliminary operation. Legacy build_road remains closed for junctions.
 local function junctionLaneIndices(node,edge)
  local lanes=listOf(edge.laneConfigs);local incoming,outgoing={},{}
  assert(#lanes==4 or #lanes==6,"Junction requires a simple small/medium two-way road")
  for i,lane in ipairs(lanes)do
   local modes=lane.transportModes
   assert(type(lane.forward)=="boolean","Road lane direction unavailable")
   assert(not modes[api.type.enum.TransportMode.TRAM] and not modes[api.type.enum.TransportMode.ELECTRIC_TRAM],"Tram junction unsupported")
   if modes[api.type.enum.TransportMode.CAR] or modes[api.type.enum.TransportMode.TRUCK] then
    assert(modes[api.type.enum.TransportMode.CAR] and modes[api.type.enum.TransportMode.TRUCK],"Restricted road lanes unsupported")
    local index=edge.node0==node and i-1 or #lanes-i
    local target=lane.forward==(edge.node1==node) and incoming or outgoing
    target[#target+1]=index
   end
  end
  assert(#incoming==#outgoing and (#incoming==1 or #incoming==2),"Junction requires balanced vehicle lanes")
  return incoming,outgoing
 end
 local function junctionEndpoint(id,n,adjacent)
  assert(#adjacent==2,"Only a degree-two road node can gain one branch")
  assert(not constructionOfNode(id),"Junction refuses construction-owned nodes")
  table.sort(adjacent)
  local edges,identity={},{}
  for _,eid in ipairs(adjacent)do
   local e=assert(getComponent(eid,"BASE_EDGE"),"Junction road missing")
   assert(e.node0==id or e.node1==id,"Junction adjacency changed")
   assert(e.roadType==api.type.enum.RoadType.STREET and e.type==api.type.enum.BaseEdgeType.NORMAL,"Junction requires normal ground roads")
   assert(not constructionOfEdge(eid) and #listOf(e.objects)==0,"Junction refuses construction roads and edge objects")
   local owner=ownerOf(eid);assert(not owner or owner<0 or owner==api.engine.util.getPlayer(),"Foreign junction road")
   local incoming,outgoing=junctionLaneIndices(id,e)
   edges[#edges+1]={id=eid,signature=stableDataSignature(toPlain(e,0,nil,"Network.BaseEdge")),incoming=incoming,outgoing=outgoing}
   identity[#identity+1]={eid,toPlain(e,0,nil,"Network.BaseEdge"),owner}
  end
  assertStreetNetworkHealthy(id,"junction")
  local cfg=assert(getComponent(id,"BASE_NODE_CONFIG"),"Explicit junction configuration required")
  local snapshot=networkNodeConfigSnapshot(cfg)
  assert(cfg.doubleSlipSwitch==false and cfg.userModifiedTrafficLightStates==false
   and cfg.trafficLightPreference==api.type.enum.TrafficLightPreference.AUTO
   and cfg.trafficLightConfig.trafficLightType==-1 and #listOf(cfg.trafficLightConfig.states)==0,"Custom junction signals unsupported")
  local custom=readField(cfg,"userModifiedLaneConnections")
  assert(custom==nil or custom==false,"Custom junction turns unsupported")
  local allowed={[adjacent[1]]=edges[1],[adjacent[2]]=edges[2]};local walks={}
  for _,eid in ipairs(cfg.crosswalks)do assert(allowed[eid] and not walks[eid],"Unknown or duplicate crosswalk");walks[eid]=true end
  local directed,seen={},{}
  local function contains(values,value)for _,v in ipairs(values)do if v==value then return true end end;return false end
  for _,l in ipairs(cfg.laneConnections)do
   local a,b=allowed[l.segment0],allowed[l.segment1]
   assert(a and b and a~=b and l.withRoad==true and l.withTram==false,"Unexpected existing junction turn")
   assert(contains(a.incoming,l.lane0) and contains(b.outgoing,l.lane1),"Existing turn has invalid directional lane")
   local key=table.concat({l.segment0,l.segment1,l.lane0,l.lane1},":")
   assert(not seen[key],"Duplicate junction turn");seen[key]=true;directed[l.segment0]=true
  end
  assert(directed[adjacent[1]] and directed[adjacent[2]],"Existing two-way turns missing")
  local p=n.position
  return {node=id,pos={x=p.x,y=p.y,z=p.z},junction=true,junctionEdges=edges,junctionConfig=snapshot,
   signature=stableDataSignature({id,{x=p.x,y=p.y,z=p.z},identity,snapshot})}
 end
 local function junctionConfig(pt,newId,newEdge,readback)
  local old=pt.junctionConfig;local row=readback and {comp={}} or api.type.BaseNodeLaneConnectionAndEntity.new();row.entity=pt.node
  local turns={}
  local function add(a,b,i,j)
   local l=readback and {} or api.type.LaneConnection.new();l.segment0=a;l.segment1=b;l.lane0=i;l.lane1=j;l.withRoad=true;l.withTram=false
   turns[#turns+1]=l
  end
  for _,l in ipairs(old.laneConnections)do add(l.segment0,l.segment1,l.lane0,l.lane1)end
  local incoming,outgoing=junctionLaneIndices(pt.node,newEdge)
  for _,edge in ipairs(pt.junctionEdges)do
   for _,i in ipairs(edge.incoming)do for _,j in ipairs(outgoing)do add(edge.id,newId,i,j)end end
   for _,i in ipairs(incoming)do for _,j in ipairs(edge.outgoing)do add(newId,edge.id,i,j)end end
  end
  row.comp.laneConnections=turns;row.comp.crosswalks=listOf(old.crosswalks)
  row.comp.trafficLightPreference=old.trafficLightPreference
  if readback then row.comp.trafficLightConfig=old.trafficLightConfig
  else row.comp.trafficLightConfig=assert(getComponent(pt.node,"BASE_NODE_CONFIG"),"Junction config removed").trafficLightConfig end
  row.comp.doubleSlipSwitch=old.doubleSlipSwitch;row.comp.userModifiedTrafficLightStates=old.userModifiedTrafficLightStates
  return row
 end
 local function junctionConfigSignature(cfg)
  local turns,walks={},listOf(cfg.crosswalks)
  for _,l in ipairs(cfg.laneConnections)do
   turns[#turns+1]=table.concat({l.segment0,l.segment1,l.lane0,l.lane1,tostring(l.withRoad),tostring(l.withTram)},":")
  end
  table.sort(turns);table.sort(walks)
  return stableDataSignature({turns,walks,cfg.trafficLightPreference,cfg.doubleSlipSwitch,
   cfg.userModifiedTrafficLightStates,cfg.trafficLightConfig.trafficLightType})
 end
 -- AUTO regenerates phases when degree/lanes change. Preserve the policy and
 -- custom flags exactly, then validate generated phase structure independently.
 -- Preview identity still includes the complete original phase snapshot.
 local function junctionAutoSignalsValid(cfg)
  if cfg.trafficLightPreference~=api.type.enum.TrafficLightPreference.AUTO
   or cfg.userModifiedTrafficLightStates~=false or cfg.doubleSlipSwitch~=false
   or cfg.trafficLightConfig.trafficLightType~=-1 then return false end
  local custom=readField(cfg,"userModifiedLaneConnections")
  if custom~=nil and custom~=false then return false end
  local function finite(n)return type(n)=="number" and n==n and n~=math.huge and n~=-math.huge end
  local count=#listOf(cfg.laneConnections)
  for _,phase in ipairs(cfg.trafficLightConfig.states)do
   if not finite(phase.duration) or not finite(phase.minDuration) or phase.minDuration<0
    or phase.duration<phase.minDuration or type(phase.canSkip)~="boolean" then return false end
   local seen={}
   for _,index in ipairs(phase.lockedLanes)do
    if not finite(index) or index%1~=0 or index<0 or index>=count or seen[index] then return false end
    seen[index]=true
   end
  end
  return true
 end
 local function endpoint(spec,roadType,resetEmptyRail,resetEmptyRoad,connectJunctions)
  if spec.node then
   local id=spec.node;local n=assert(getComponent(id,"BASE_NODE"),"Network endpoint missing")
   assert(not isFrozenStreetNode(id),"Frozen internal node; resolve external port")
   local adjacent=listOf(api.engine.system.streetSystem.getNodeSegments(id))
   if #adjacent~=1 and connectJunctions==true then
    assert(roadType==api.type.enum.RoadType.STREET,"Road junction flag cannot modify rail")
    return junctionEndpoint(id,n,adjacent)
   end
   assert(#adjacent==1,"Only a current external dead end is supported")
   local e=assert(getComponent(adjacent[1],"BASE_EDGE"),"Endpoint edge missing")
   assert(e.roadType==roadType,"Endpoint transport type mismatch")
   assert(getComponent(id,"TRANSPORT_NETWORK") and getComponent(adjacent[1],"TRANSPORT_NETWORK"),"Endpoint transport network missing")
   local cfg=getComponent(id,"BASE_NODE_CONFIG")
   -- Default stays closed. An explicit rail-port reset is part of the SAME
   -- connect proposal, never a preliminary mutation or an automatic repair.
   local reset,resetRoad,portIdentity=false,false,nil
   if cfg and #listOf(cfg.laneConnections)==0 then
    if resetEmptyRoad==true then
     assert(roadType==api.type.enum.RoadType.STREET,"Road reset requires an ordinary street")
     assert(not constructionOfNode(id) and not constructionOfEdge(adjacent[1]),"Road reset refuses construction ports")
     assert(e.type==api.type.enum.BaseEdgeType.NORMAL and #listOf(e.objects)==0,"Road reset refuses structures or edge objects")
     local owner=ownerOf(adjacent[1]);assert(not owner or owner<0 or owner==api.engine.util.getPlayer(),"Foreign road endpoint")
     local walks=listOf(cfg.crosswalks)
     assert(#walks<=1 and (#walks==0 or walks[1]==adjacent[1]),"Non-default road crosswalks must be preserved")
     resetRoad=true;portIdentity={road=adjacent[1],owner=owner,crosswalks=walks}
    else
     assert(resetEmptyRail==true,"Endpoint has explicit empty lane configuration; investigate before connection")
     assert(roadType==api.type.enum.RoadType.TRACK,"Empty config reset is rail-only")
     local conId=constructionOfEdge(adjacent[1]);local con=conId and getComponent(conId,"CONSTRUCTION")
     assert(con and ownerOf(conId)==api.engine.util.getPlayer(),"Reset requires an owned construction external rail port")
     assert(con.fileName:match("^::/stations/rail/") or con.fileName:match("^::/depots/rail/"),"Unsupported rail-port construction")
     local frozenEdge=false;for _,edgeId in pairs(con.frozenEdges) do if edgeId==adjacent[1] then frozenEdge=true end end
     assert(frozenEdge,"Rail-port edge must belong to construction frozen edges")
     assert(#listOf(cfg.crosswalks)==0,"Non-default rail node configuration must be preserved")
     portIdentity={construction=conId,resource=con.fileName,position=assert(constructionPosition(conId),"Rail-port construction position unavailable"),owner=ownerOf(conId),
      frozenNodes=toPlain(con.frozenNodes),frozenEdges=toPlain(con.frozenEdges)}
     reset=true
    end
    assert(#listOf(cfg.trafficLightConfig.states)==0 and cfg.trafficLightConfig.trafficLightType==-1
     and cfg.trafficLightPreference==api.type.enum.TrafficLightPreference.AUTO
     and cfg.doubleSlipSwitch==false and cfg.userModifiedTrafficLightStates==false,"Non-default node configuration must be preserved")
    local flag=readField(cfg,"userModifiedLaneConnections")
    assert(flag==nil or flag==false,"Custom node configuration must be preserved")
   end
   local p=n.position;return {node=id,pos={x=p.x,y=p.y,z=p.z},edge=e,resetEmptyRail=reset,resetEmptyRoad=resetRoad,requiredCrosswalks=resetRoad and listOf(cfg.crosswalks) or nil,oldRoad=resetRoad and adjacent[1] or nil,
    signature=stableDataSignature({id,adjacent[1],toPlain(e,0,nil,"Network.BaseEdge"),networkNodeConfigSnapshot(cfg),portIdentity})}
  end
  local x,y=roadNumber(spec.x,"x"),roadNumber(spec.y,"y")
  assert(api.engine.terrain.isValidCoordinate(V2(x,y)),"Network point outside map")
  assert(not api.engine.terrain.isOnWater(V2(x,y)),"Network adapter requires dry land")
  return {pos={x=x,y=y,z=spec.z or terrainHeight(x,y)},signature="coordinate"}
 end
 -- A default two-way street end needs explicit lane links when retaining its
 -- crosswalk configuration. Native LaneConnection indexes look outward from the node.
 local function roadPortLinks(node,oldId,oldEdge,newId,newEdge)
  local function lanes(edge)
   local incoming,outgoing;local configs=listOf(edge.laneConfigs)
   assert(#configs>0,"Road lane definitions unavailable")
   for i,lane in ipairs(configs)do
    local modes=lane.transportModes
    assert(not modes[api.type.enum.TransportMode.TRAM] and not modes[api.type.enum.TransportMode.ELECTRIC_TRAM],"Tram street-end configuration needs separate support")
    if modes[api.type.enum.TransportMode.CAR] or modes[api.type.enum.TransportMode.TRUCK] then
     assert(modes[api.type.enum.TransportMode.CAR] and modes[api.type.enum.TransportMode.TRUCK],"Restricted street lanes unsupported")
     local index=edge.node0==node and i-1 or #configs-i
     if lane.forward==(edge.node1==node)then assert(incoming==nil,"Multiple incoming road lanes unsupported");incoming=index
     else assert(outgoing==nil,"Multiple outgoing road lanes unsupported");outgoing=index end
    end
   end
   assert(incoming~=nil and outgoing~=nil,"Two-way road lanes required")
   return incoming,outgoing
  end
  local ai,ao=lanes(oldEdge);local bi,bo=lanes(newEdge)
  return {{segment0=oldId,lane0=ai,segment1=newId,lane1=bo,withRoad=true,withTram=false},
   {segment0=newId,lane0=bi,segment1=oldId,lane1=ao,withRoad=true,withTram=false}}
 end
 local function prepare(args)
  assert(not (args.reset_empty_road_ports and args.reset_empty_rail_ports),"Select only one scoped endpoint reset")
  assert(not (args.connect_road_junctions and args.reset_empty_rail_ports),"Road junctions cannot use rail-port reset")
  local name,tpl=resolveStreetTemplate(args.template)
  assert(tpl.roadType==api.type.enum.RoadType.STREET or tpl.roadType==api.type.enum.RoadType.TRACK,"Unsupported network type")
  local points={endpoint(args.start,tpl.roadType,args.reset_empty_rail_ports,args.reset_empty_road_ports,args.connect_road_junctions)}
  for _,p in ipairs(args.via or {}) do assert(not p.node,"Interior junctions unsupported");points[#points+1]=endpoint(p,tpl.roadType) end
  points[#points+1]=endpoint(args["end"],tpl.roadType,args.reset_empty_rail_ports,args.reset_empty_road_ports,args.connect_road_junctions)
  assert(not points[1].node or points[1].node~=points[#points].node,"Network self-loop refused")
  local tangents,lengths={},{};local total=0
  for i=1,#points-1 do
   local a,b=points[i].pos,points[i+1].pos;local len=dist2d(a,b)
   assert(len>=10 and len<=200,"Each network span must be 10 to 200 metres")
   -- Grade is decided by the mandatory native network preview, not a fixed percentage.
   lengths[i]=len;total=total+len
  end
  assert(total<=600,"Network test exceeds 600 metres")
  for i,p in ipairs(points) do
   local a,b=points[math.max(1,i-1)].pos,points[math.min(#points,i+1)].pos
   local dx,dy,dz=b.x-a.x,b.y-a.y,b.z-a.z
   if p.edge then
    local e=p.edge;local t=e.node1==p.node and e.tangent1 or e.tangent0
    local sign=e.node1==p.node and 1 or -1;if i==#points then sign=-sign end
    dx,dy,dz=t.x*sign,t.y*sign,t.z*sign
   end
   local len=math.sqrt(dx*dx+dy*dy);assert(len>=1,"Reversing or degenerate curve refused")
   tangents[i]={x=dx/len,y=dy/len,z=dz/len}
  end
  local p=api.type.SimpleProposal.new();local nodes,edges,ids={},{},{};local nextId=-1
  local function newId()local id=nextId;nextId=nextId-1;return id end
  for i,pt in ipairs(points) do
   ids[i]=pt.node
   if not ids[i] then local n=api.type.NodeAndEntity.new();n.entity=newId();n.comp.position=V3(pt.pos.x,pt.pos.y,pt.pos.z);ids[i]=n.entity;nodes[#nodes+1]=n end
  end
  for i=1,#points-1 do
   local len=lengths[i];local a,b=tangents[i],tangents[i+1]
   local delta={x=points[i+1].pos.x-points[i].pos.x,y=points[i+1].pos.y-points[i].pos.y}
   assert((a.x*delta.x+a.y*delta.y)/len>.5 and (b.x*delta.x+b.y*delta.y)/len>.5,"Sharp/reversing endpoint tangent refused")
   local e=newStreetEdge(newId(),ids[i],ids[i+1],points[i].pos,points[i+1].pos,
    {x=a.x*len,y=a.y*len,z=a.z*len},{x=b.x*len,y=b.y*len,z=b.z*len},name,tpl)
   if tpl.roadType==api.type.enum.RoadType.TRACK then e.type=1;e.comp.roadType=api.type.enum.RoadType.TRACK end
   edges[#edges+1]=e
  end
  p.streetProposal.nodesToAdd=nodes;p.streetProposal.edgesToAdd=edges
  local resetNodes={};for _,pt in ipairs(points) do if pt.resetEmptyRail or pt.resetEmptyRoad or pt.junction then resetNodes[#resetNodes+1]=pt.node end end
  p.streetProposal.nodeConfigsToRemove=resetNodes
  local addedConfigs={}
  for i,pt in ipairs(points)do if pt.resetEmptyRoad then
   local edge=edges[i==1 and 1 or #edges]
   local config=api.type.BaseNodeLaneConnectionAndEntity.new();config.entity=pt.node
   local links={};for _,row in ipairs(roadPortLinks(pt.node,pt.oldRoad,pt.edge,edge.entity,edge.comp))do
    local link=api.type.LaneConnection.new();link.segment0=row.segment0;link.segment1=row.segment1
    link.lane0=row.lane0;link.lane1=row.lane1;link.withRoad=true;link.withTram=false;links[#links+1]=link
   end
   config.comp.laneConnections=links;config.comp.crosswalks=pt.requiredCrosswalks
   config.comp.trafficLightPreference=api.type.enum.TrafficLightPreference.AUTO
   config.comp.trafficLightConfig=getComponent(pt.node,"BASE_NODE_CONFIG").trafficLightConfig
   config.comp.doubleSlipSwitch=false;addedConfigs[#addedConfigs+1]=config
  end end
  for i,pt in ipairs(points)do if pt.junction then
   local edge=edges[i==1 and 1 or #edges]
   addedConfigs[#addedConfigs+1]=junctionConfig(pt,edge.entity,edge.comp)
  end end
  p.streetProposal.nodeConfigsToAdd=addedConfigs
  local geometry={};for _,pt in ipairs(points) do geometry[#geometry+1]=pt.pos end
  local signature={name,points[1].signature,points[#points].signature,toPlain(tpl.laneConfigs,0,nil,{element="LaneConfig"}),tpl.roadType,tpl.streetStyle,geometry}
  return p,points,name,stableDataSignature(signature),total
 end
 commands.preview_network=function(args)
  local proposal,points,name,signature,length=prepare(args)
  local check=previewProposal(proposal,roadIgnoreSet(points))
  check.preview=true;check.template=name;check.length=length;check.segments=#points-1
  check.serviceConnectivityVerified=false
  check.junctions={};for _,pt in ipairs(points)do if pt.junction then
   check.junctions[#check.junctions+1]={node=pt.node,existingEdges={pt.junctionEdges[1].id,pt.junctionEdges[2].id},atomicLaneConfiguration=true}
  end end
  check.resetEmptyRailPorts={};for _,pt in ipairs(points) do if pt.resetEmptyRail then check.resetEmptyRailPorts[#check.resetEmptyRailPorts+1]=pt.node end end
  check.resetEmptyRoadPorts={};for _,pt in ipairs(points) do if pt.resetEmptyRoad then check.resetEmptyRoadPorts[#check.resetEmptyRoadPorts+1]={node=pt.node,requiredCrosswalks=pt.requiredCrosswalks} end end
  if check.ok==true and not check.critical and not check.blocked and not check.placementBlocked and #check.collisions==0 then
   serial=serial+1;local token="ui-network:"..tostring(epoch)..":"..serial
   previews[token]={args=args,signature=signature,clock=assert(wallClock()),player=api.engine.util.getPlayer()}
   checkpoint();check.preview_token=token
  end
  return check
 end
 commands.commit_network=function(args)
  local op={id=requestId,cmd="commit_network",token=args.preview_token,epoch=epoch,phase="pre_dispatch"}
  if requestId then operations[requestId]=op end
  local r=previews[args.preview_token];previews[args.preview_token]=nil;checkpoint()
  assert(r,"Unknown or consumed network preview")
  local now=assert(wallClock());assert(now>=r.clock and now-r.clock<=60,"Network preview expired")
  assert(r.player==api.engine.util.getPlayer(),"Player changed")
  local proposal,points,name,signature=prepare(r.args);assert(signature==r.signature,"Network endpoints or template changed")
  local check=previewProposal(proposal,roadIgnoreSet(points))
  assert(check.ok==true and not check.critical and not check.blocked and not check.placementBlocked and #check.collisions==0,"Network no longer buildable")
  local out={built=false,verified=false,edges={},nodes={},serviceConnectivityVerified=false}
  -- BASE_EDGE is not accepted by forEachEntityWithComponent in the native engine.
  -- Use the complete adjacency index, as in list_map_entities; shared endpoints
  -- cause duplicate edge IDs and must be deduplicated before receipt checking.
  local existing={}
  for _,segments in pairs(api.engine.system.streetSystem.getNode2SegmentMap()) do
   for _,id in pairs(segments) do existing[id]=true end
  end
  op.phase="dispatching";checkpoint() -- any later exception/timeout stays blocked
  applyProposal(proposal,false,function(ok,res)
   out.built=ok==true
   if out.built then
    local endpoints={};for _,pt in ipairs(points) do if pt.node then endpoints[#endpoints+1]=pt.node end end
    local result=addedStreetEntities(res,endpoints)
    out.edges=result.edges;out.nodes=result.nodes
   end
  end)
  if out.built then
   local matched=0
   for _,id in ipairs(out.edges) do
    local e=getComponent(id,"BASE_EDGE");assert(not existing[id],"Network receipt contains an existing edge")
    if e and e.roadTemplate==name and getComponent(id,"TRANSPORT_NETWORK") then matched=matched+1 end
   end
   out.verified=matched==#points-1 and #out.edges==matched
   out.resetEmptyRailPorts={}
   for _,pt in ipairs(points) do if pt.resetEmptyRail then
    local cfg=getComponent(pt.node,"BASE_NODE_CONFIG")
    local count=cfg and #listOf(cfg.laneConnections) or 0
    local verified=not cfg or count>0
    out.resetEmptyRailPorts[#out.resetEmptyRailPorts+1]={node=pt.node,explicitConfigPresent=cfg~=nil,laneConnections=count,verified=verified}
    if not verified then out.verified=false end
   end end
   out.resetEmptyRoadPorts={}
   for _,pt in ipairs(points) do if pt.resetEmptyRoad then
    local cfg=getComponent(pt.node,"BASE_NODE_CONFIG")
    local walks=cfg and listOf(cfg.crosswalks) or {};local present={};for _,id in ipairs(walks)do present[id]=true end
    local laneRows=cfg and listOf(cfg.laneConnections) or {}
    local verified=#laneRows==2;local freshEdge
    for _,id in ipairs(out.edges)do local edge=getComponent(id,"BASE_EDGE")
     if edge and (edge.node0==pt.node or edge.node1==pt.node)then assert(not freshEdge,"Ambiguous new endpoint road");freshEdge=id end
    end
    if freshEdge then
     local expected=roadPortLinks(pt.node,pt.oldRoad,getComponent(pt.oldRoad,"BASE_EDGE"),freshEdge,getComponent(freshEdge,"BASE_EDGE"))
     for _,wanted in ipairs(expected)do local found=false
      for _,got in ipairs(laneRows)do if got.segment0==wanted.segment0 and got.segment1==wanted.segment1 and got.lane0==wanted.lane0 and got.lane1==wanted.lane1 and got.withRoad==true and got.withTram==false then found=true end end
      if not found then verified=false end
     end
    else verified=false end
    for _,id in ipairs(pt.requiredCrosswalks)do if not present[id]then verified=false end end
    out.resetEmptyRoadPorts[#out.resetEmptyRoadPorts+1]={node=pt.node,verified=verified,requiredCrosswalks=pt.requiredCrosswalks,observedCrosswalks=walks}
    if not verified then out.verified=false end
   end end
  end
  out.junctions={}
  if out.built then for _,pt in ipairs(points)do if pt.junction then
   local freshEdge;local current={};for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(pt.node)))do current[id]=true end
   for _,id in ipairs(out.edges)do local edge=getComponent(id,"BASE_EDGE")
    if edge and (edge.node0==pt.node or edge.node1==pt.node)then assert(not freshEdge,"Ambiguous new junction branch");freshEdge=id end
   end
   local cfg=getComponent(pt.node,"BASE_NODE_CONFIG");local verified=freshEdge~=nil and cfg~=nil
   local count=0;for _ in pairs(current)do count=count+1 end
   verified=verified and count==3 and getComponent(pt.node,"TRANSPORT_NETWORK")~=nil
   for _,e in ipairs(pt.junctionEdges)do
    local edge=getComponent(e.id,"BASE_EDGE")
    if not current[e.id] or not edge or not getComponent(e.id,"TRANSPORT_NETWORK")
     or stableDataSignature(toPlain(edge,0,nil,"Network.BaseEdge"))~=e.signature then verified=false end
   end
   if verified then
    local expected=junctionConfig(pt,freshEdge,getComponent(freshEdge,"BASE_EDGE"),true)
    verified=junctionConfigSignature(cfg)==junctionConfigSignature(expected.comp) and junctionAutoSignalsValid(cfg)
   end
   out.junctions[#out.junctions+1]={node=pt.node,branch=freshEdge,configurationVerified=verified,
    existingEdges={pt.junctionEdges[1].id,pt.junctionEdges[2].id},directedPathsVerified=false}
   if not verified then out.verified=false end
  end end end
  op.phase=out.verified and "verified" or "unconfirmed";checkpoint()
  out.verificationScope="new edge count/template, transport-network components, and opted-in port/junction configuration and preserved-road readback; directed connections and service need separate acceptance"
  return out
 end
 for _,name in ipairs({"list_network_templates","preview_network","commit_network"}) do ENGINE_COMMANDS[name]=true end
end

-- Explicit road graphs (v35). New topology is experimental until isolated native
-- acceptance. No implicit crossing, deletion of objects, or frozen-node surgery.
do
 local saved,epoch,requestId,checkpoint
 workflowStateBinders.roadGraph=function(state,session,id)
  epoch=session;requestId=id;saved=(state:get() or {}).roadGraphAdapter
  if not saved or saved.epoch~=session then saved={epoch=session,serial=0,previews={},operations={}} end
  checkpoint=function()local root=state:get() or {};root.roadGraphAdapter=saved;state:set(root)end
  return checkpoint
 end
 local function finite(n)return type(n)=="number" and n==n and math.abs(n)~=math.huge end
 local function keys(t,allowed)
  assert(type(t)=="table","Object required");for k in pairs(t)do assert(allowed[k],"Unknown graph field: "..tostring(k))end
 end
 local function array(t,low,high)
  assert(type(t)=="table" and #t>=low and #t<=high,"Graph array exceeds bounds")
  local count=0;for i in pairs(t)do assert(type(i)=="number" and i%1==0 and i>=1 and i<=#t,"Invalid array index");count=count+1 end
  assert(count==#t,"Sparse graph array")
 end
 local function vec(v)
  keys(v,{x=true,y=true,z=true});assert(finite(v.x) and finite(v.y) and finite(v.z),"Explicit finite xyz required")
  return {x=v.x,y=v.y,z=v.z}
 end
 local function entity(v)assert(finite(v) and v%1==0 and v>=0 and v<2147483647,"Invalid entity");return v end
 local function text(v)assert(type(v)=="string" and #v>0 and #v<=160,"Invalid resource");return v end
 local function snapshot(id)return toPlain(assert(getComponent(id,"BASE_EDGE"),"Road missing"),0,nil,"Network.BaseEdge")end
 local function edgeSet()
  local out={};for _,ids in pairs(api.engine.system.streetSystem.getNode2SegmentMap())do for _,id in pairs(ids)do out[id]=true end end;return out
 end
 local function adjacencySignature()
  local nodes={}
  for id,ids in pairs(api.engine.system.streetSystem.getNode2SegmentMap())do
   local edges={};for _,eid in pairs(ids)do edges[#edges+1]=eid end;table.sort(edges);nodes[id]=edges
  end
  return stableDataSignature(nodes)
 end
 local function road(id,split,allowRail)
  local e=assert(getComponent(id,"BASE_EDGE"),"Road missing")
  assert(e.roadType==api.type.enum.RoadType.STREET or (allowRail and e.roadType==api.type.enum.RoadType.TRACK),"Rail edges require an explicit crossing resource")
  local owner=ownerOf(id);assert(not owner or owner<0 or owner==api.engine.util.getPlayer(),"Foreign road")
  assert(getComponent(id,"TRANSPORT_NETWORK"),"Road transport network missing")
  if split then
   assert(not constructionOfEdge(id),"Cannot split construction-owned roads")
   assert(#listOf(e.objects)==0 or split.preserve_objects==true,"Object split requires explicit preserve_objects")
   if e.type~=api.type.enum.BaseEdgeType.NORMAL then
    assert(split.allow_structure==true,"Structure split requires explicit allow_structure")
    local rep=e.type==api.type.enum.BaseEdgeType.BRIDGE and api.res.bridgeTypeRep or e.type==api.type.enum.BaseEdgeType.TUNNEL and api.res.tunnelTypeRep
    assert(rep and e.typeIndex>=0 and rep.get(e.typeIndex),"Unknown existing structure resource")
    assert(#listOf(e.objects)==0,"Objects on structure splits require separate acceptance")
   end
  end
  return e
 end
 local function lanes(id,e)
  local all=listOf(e.laneConfigs);assert(#all>0 and #all<=32,"Native lane definitions unavailable")
  local incoming,outgoing={},{}
  for i,l in ipairs(all)do
   assert(type(l.forward)=="boolean","Lane direction unavailable")
   local modes={};for m=2,6 do if l.transportModes[m] then modes[m]=true end end
   if next(modes) then
    local target=l.forward==(e.node1==id) and incoming or outgoing
    target[#target+1]={index=e.node0==id and i-1 or #all-i,modes=modes}
   end
  end
  assert(#incoming+#outgoing>0,"No supported road/tram vehicle lanes")
  return incoming,outgoing
 end
 local function compatible(a,b)
  local r,t=false,false;for m=2,6 do if a.modes[m] and b.modes[m] then if m<=4 then r=true else t=true end end end
  return r,t
 end
 local function hermite(e,u)
  local p,t={},{};local u2,u3=u*u,u*u*u
  for _,k in ipairs({"x","y","z"})do
   p[k]=(2*u3-3*u2+1)*e.position0[k]+(u3-2*u2+u)*e.tangent0[k]+(-2*u3+3*u2)*e.position1[k]+(u3-u2)*e.tangent1[k]
   t[k]=(6*u2-6*u)*e.position0[k]+(3*u2-4*u+1)*e.tangent0[k]+(-6*u2+6*u)*e.position1[k]+(3*u2-2*u)*e.tangent1[k]
  end
  return p,t
 end
 local function scale(v,s)return {x=v.x*s,y=v.y*s,z=v.z*s}end
 local function defaultConfig(node)
  local r=api.type.BaseNodeLaneConnectionAndEntity.new();r.entity=node
  r.comp.trafficLightPreference=api.type.enum.TrafficLightPreference.AUTO
  r.comp.doubleSlipSwitch=false;r.comp.userModifiedTrafficLightStates=false
  return r
 end
 local function configSignature(c,map)
  map=map or {};local turns,walks={},{}
  for _,l in ipairs(c.laneConnections)do
   turns[#turns+1]=table.concat({map[l.segment0] or l.segment0,map[l.segment1] or l.segment1,l.lane0,l.lane1,tostring(l.withRoad),tostring(l.withTram)},":")
  end
  for _,e in ipairs(c.crosswalks)do walks[#walks+1]=map[e] or e end;table.sort(turns);table.sort(walks)
  return stableDataSignature({turns,walks,c.trafficLightPreference,c.doubleSlipSwitch,c.userModifiedTrafficLightStates,c.trafficLightConfig.trafficLightType})
 end
 local function remapObjectReferences(value,oldEdge,newEdge)
  if type(value)~="table" then return value end
  local out={};for k,v in pairs(value)do
   out[k]=k=="entity" and v==oldEdge and newEdge or remapObjectReferences(v,oldEdge,newEdge)
  end;return out
 end
 local function sameObjectValue(a,b,key)
  if type(a)~=type(b)then return false end
  if type(a)=="number" and (key=="x" or key=="y" or key=="z" or key=="w")then return math.abs(a-b)<.002 end
  if type(a)~="table" then return a==b end
  for k,v in pairs(a)do if not sameObjectValue(v,b[k],k)then return false end end
  for k in pairs(b)do if a[k]==nil then return false end end;return true
 end
 -- Street-stop parameters are retained metadata, not recomputed after a split.
 -- Resolve the real terminal anchor from native lane geometry (not opaque Node data).
 local function stopAnchor(station,edge)
  local net=assert(getComponent(edge,"TRANSPORT_NETWORK"),"Stop network missing")
  local anchor
  local function at(ref,mode)
   assert(ref.entity==edge,"Stop terminal references another edge")
   local found
   for _,lane in ipairs(net.edges)do if lane.transportModes[mode] then
    for i,conn in ipairs(lane.conns)do if conn.entity==edge and conn.index==ref.index then
     local g=lane.geometry;assert(g.type==3,"Unverified stop network geometry type")
     local v=g.cubicOffsetSpline.pos[i];local z=i==1 and g.height.x or g.height.y
     assert(v and finite(v.x) and finite(v.y) and finite(z),"Stop network anchor unavailable")
     local p={x=v.x,y=v.y,z=z}
     if found then assert(sameObjectValue(found,p),"Inconsistent stop network anchor")else found=p end
    end end
   end end
   assert(found,"Stop terminal has no native lane")
   if anchor then assert(sameObjectValue(anchor,found),"Stop terminal anchors disagree")else anchor=found end
  end
  local terminals=listOf(station.terminals);assert(#terminals>0 and #terminals<=8,"Unsupported stop terminal count")
  for _,t in ipairs(terminals)do
   at(t.vehicleNodeId,api.type.enum.TransportMode.BUS)
   for _,ref in ipairs(t.personNodes)do at(ref,api.type.enum.TransportMode.PERSON)end
  end
  return assert(anchor)
 end
 local function projectStop(e,anchor)
  local function distance(u)local p=hermite(e,u);return (p.x-anchor.x)^2+(p.y-anchor.y)^2 end
  local best,score=0,math.huge
  for i=0,64 do local u=i/64;local d=distance(u);if d<score then best,score=u,d end end
  local lo,hi=math.max(0,best-1/64),math.min(1,best+1/64)
  for _=1,40 do local a,b=lo+(hi-lo)/3,hi-(hi-lo)/3;if distance(a)<distance(b)then hi=b else lo=a end end
  local u=(lo+hi)/2;assert(u>0 and u<1 and distance(u)<.03^2,"Stop anchor does not project onto road")
  return u
 end
 local function preservedStopPlacement(station,edge,value,wanted)
  local anchor=stopAnchor(station,edge);local before=wanted.anchor
  if math.abs(anchor.x-before.x)>=.002 or math.abs(anchor.y-before.y)>=.002 or math.abs(anchor.z-before.z)>.25 then return false end
  -- Ground alignment can change height: require exactly the same vertical shift
  -- in the model and its native terminal, plus bounded XY and orientation changes.
  local expected=remapObjectReferences(wanted.before.transf,-1,-1)
  assert(expected.columns and expected.columns[4],"Stop model transform missing")
  expected.columns[4].z=expected.columns[4].z+anchor.z-before.z
  return sameObjectValue(value.transf,expected)
 end
 local function signalPlan(spec,count)
  keys(spec,{preference=true,traffic_light_type=true,states=true})
  assert(spec.preference=="YES","Explicit signals require YES preference")
  assert(finite(spec.traffic_light_type) and spec.traffic_light_type%1==0 and spec.traffic_light_type>=-1 and spec.traffic_light_type<10000,"Invalid signal type")
  if spec.traffic_light_type>=0 then assert(api.res.trafficLightTypeRep and api.res.trafficLightTypeRep.get(spec.traffic_light_type),"Unknown signal resource")end
  array(spec.states,1,64);local cfg=api.type.TrafficLightConfig.new();cfg.trafficLightType=spec.traffic_light_type;local phases={}
  for _,v in ipairs(spec.states)do
   keys(v,{locked_lanes=true,duration=true,min_duration=true,can_skip=true});array(v.locked_lanes,0,544)
   assert(finite(v.duration) and finite(v.min_duration) and v.duration>0 and v.min_duration>=0 and v.duration>=v.min_duration and v.duration<=300 and type(v.can_skip)=="boolean","Invalid signal phase")
   local seen={};for _,i in ipairs(v.locked_lanes)do assert(entity(i)<count and not seen[i],"Invalid or duplicate locked lane");seen[i]=true end
   local phase=api.type.TrafficLightState.new();phase.lockedLanes=v.locked_lanes;phase.duration=v.duration;phase.minDuration=v.min_duration;phase.canSkip=v.can_skip;phases[#phases+1]=phase
  end
  cfg.states=phases;return cfg
 end
 local function extendSignals(old,oldCount,newCount,walkCount,duration)
  assert(finite(duration) and duration>=3 and duration<=120,"Extension phase duration must be 3-120 seconds")
  local count=newCount+walkCount;local phases={};local delta=newCount-oldCount
  assert(#listOf(old.states)>0,"Custom signal states unavailable; supply an explicit signal plan")
  for _,v in ipairs(old.states)do
   local locks,seen={},{};for _,i in ipairs(v.lockedLanes)do
    assert(entity(i)<oldCount+walkCount and not seen[i],"Old signal index invalid");seen[i]=true
    locks[#locks+1]=i>=oldCount and i+delta or i
   end
   for i=oldCount,newCount-1 do locks[#locks+1]=i end
   phases[#phases+1]={locked_lanes=locks,duration=v.duration,min_duration=v.minDuration,can_skip=v.canSkip}
  end
  -- Each new turn gets its own phase. Old timings/turns/crosswalk phases stay
  -- intact and all conflicting old movements are locked during new phases.
  for active=oldCount,newCount-1 do
   local locks={};for i=0,count-1 do if i~=active then locks[#locks+1]=i end end
   phases[#phases+1]={locked_lanes=locks,duration=duration,min_duration=1.5,can_skip=true}
  end
  return signalPlan({preference="YES",traffic_light_type=old.trafficLightType,states=phases},count)
 end
 local function prepare(args)
  -- isolated_test is retained for client compatibility; current-map use is authorized.
  local g=args.graph;keys(g,{nodes=true,edges=true});array(g.nodes,1,32);array(g.edges,0,48)
  local p=api.type.SimpleProposal.new();local sp=p.streetProposal
  local nodes,edges,remove,configs,removeConfigs={},{},{},{},{}
  local pts,byId,oldEdges,oldConfigs,identities,splitEdges,remap={},{},{},{},{},{},{}
  local objects,crossings,clones,explicitEdges={},{},{},{};local allowRail,preserveCrossings=false,false
  for _,n in ipairs(g.nodes)do
   if n.crossing_resource then allowRail=true end
   if n.split and n.split.preserve_crossings==true then allowRail=true;preserveCrossings=true end
  end
  local serial=0;local function newId()serial=serial-1;return serial end
  local function touch(id)
   if byId[id] then return byId[id] end
   local n=assert(getComponent(id,"BASE_NODE"),"Node missing")
   assert(not isFrozenStreetNode(id),"Frozen internal node; use the external port")
   assert(getComponent(id,"TRANSPORT_NETWORK"),"Node network missing")
   local pt={id=id,pos={x=n.position.x,y=n.position.y,z=n.position.z},old={},added={}}
   byId[id]=pt
   if preserveCrossings then
    local sys=api.engine.system.railRoadCrossingSystem
    local rcid=sys and sys.getRailroadCrossingForNode(id)
    if rcid and rcid>=0 then
     local rc=assert(getComponent(rcid,"RAILROAD_CROSSING"),"Existing crossing component missing")
     local rep=api.res.railroadCrossingTypeRep;local resource=rep.getAll()[rc.typeIndex]
     assert(type(resource)=="string" and rep.get(rc.typeIndex),"Existing crossing resource unavailable")
     assert(#listOf(rc.nodes)==1 and listOf(rc.nodes)[1]==id,"Multi-node crossing preservation not supported")
     pt.crossing=rc.typeIndex;pt.preservedCrossing=true
     crossings[id]={index=rc.typeIndex,resource=resource,originalEntity=rcid}
    end
   end
   for _,eid in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(id)))do
    local e=road(eid,nil,allowRail);assert(e.node0==id or e.node1==id,"Adjacency mismatch")
    pt.old[#pt.old+1]={entity=eid,comp=e};oldEdges[eid]={value=snapshot(eid),owner=ownerOf(eid),street=toPlain(getComponent(eid,"BASE_EDGE_STREET"),0,nil,"Engine.Component.BaseEdgeStreet")}
   end
   assert(#pt.old>=1 and #pt.old<=8,"Unsupported existing road degree")
   local cfg=getComponent(id,"BASE_NODE_CONFIG");pt.cfg=cfg
   oldConfigs[id]={position=pt.pos,config=networkNodeConfigSnapshot(cfg)}
   return pt
  end
  local function fresh(pos)
   assert(api.engine.terrain.isValidCoordinate(V2(pos.x,pos.y)),"Graph node outside map")
   local id=newId();local n=api.type.NodeAndEntity.new();n.entity=id;n.comp.position=V3(pos.x,pos.y,pos.z);nodes[#nodes+1]=n
   local pt={id=id,pos=pos,old={},added={}};byId[id]=pt;return pt
  end
  for i,n in ipairs(g.nodes)do
   keys(n,{node=true,position=true,split=true,junction=true,crossing_resource=true})
   local count=(n.node~=nil and 1 or 0)+(n.position~=nil and 1 or 0)+(n.split~=nil and 1 or 0);assert(count==1,"Select exactly one graph node source")
   local key,pt
   if n.node~=nil then key="n"..entity(n.node);pt=touch(n.node)
   elseif n.position then local pos=vec(n.position);key="p"..stableDataSignature(pos);pt=fresh(pos)
   else
    keys(n.split,{edge=true,param=true,preserve_objects=true,allow_structure=true,preserve_crossings=true,preserve_tunnel_chain=true});
    for _,key in ipairs({"preserve_objects","allow_structure","preserve_crossings","preserve_tunnel_chain"})do assert(n.split[key]==nil or type(n.split[key])=="boolean","Invalid split opt-in")end;local id=entity(n.split.edge);local u=n.split.param
    assert(finite(u) and u>=.05 and u<=.95,"Split param must be 0.05-0.95");key="s"..id
    assert(not splitEdges[id],"Only one split per old edge")
    local e=road(id,n.split,allowRail);touch(e.node0);touch(e.node1)
    if n.split.preserve_tunnel_chain then
     assert(n.split.allow_structure==true and e.type==api.type.enum.BaseEdgeType.TUNNEL,"Tunnel-chain preservation requires a tunnel split")
     local queue,seen={id},{};local cursor=1
     while cursor<=#queue do
      local eid=queue[cursor];cursor=cursor+1
      if not seen[eid] then
       seen[eid]=true;assert(cursor<=18,"Tunnel chain exceeds 16 segments")
       local part=road(eid,{allow_structure=true},allowRail);assert(#listOf(part.objects)==0,"Tunnel chain has objects")
       touch(part.node0);touch(part.node1);clones[eid]=part
       for _,nodeId in ipairs({part.node0,part.node1})do
        local count=0
        for _,neighbor in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(nodeId)))do
         local other=assert(getComponent(neighbor,"BASE_EDGE"))
         if other.type==api.type.enum.BaseEdgeType.TUNNEL then
          count=count+1;assert(other.typeIndex==e.typeIndex and other.roadType==e.roadType,"Mixed tunnel chain resources")
          if not seen[neighbor] then queue[#queue+1]=neighbor end
         end
        end
        assert(count<=2,"Branched tunnel chain not supported")
       end
      end
     end
    end
    local pos,tan=hermite(e,u);pt=fresh(pos);splitEdges[id]={point=pt,edge=e,param=u,tangent=tan};remove[#remove+1]=id
   end
   assert(not identities[key],"Duplicate graph node");identities[key]=true;pts[i]=pt
   if n.junction then
    keys(n.junction,{extend=true,phase_duration=true,signals=true,blocked_turns=true,crosswalk_edges=true});assert(next(n.junction),"Empty junction policy")
    if n.junction.phase_duration~=nil then assert(finite(n.junction.phase_duration) and n.junction.phase_duration>=3 and n.junction.phase_duration<=120,"Invalid extension duration")end
    assert(n.junction.extend==nil or n.junction.extend=="preserve","Unknown junction extension policy")
    assert(n.junction.phase_duration==nil or n.junction.extend=="preserve","Phase duration requires preserve policy")
    if n.junction.blocked_turns~=nil or n.junction.crosswalk_edges~=nil then
     assert(pt.id<0 and not n.split and n.junction.signals and not n.junction.extend,"Initial turn/crosswalk plan requires a new road junction and explicit signals")
     array(n.junction.blocked_turns or {},0,56);array(n.junction.crosswalk_edges or {},0,8)
    end
    pt.junction=n.junction
   end
   if n.crossing_resource then
    assert(not n.junction and pt.id<0,"Crossing must use a fresh/split node and no custom junction plan")
    local rep=assert(api.res.railroadCrossingTypeRep,"Railroad crossing resources unavailable")
    local resource=text(n.crossing_resource);local index=rep.find(resource)
    assert(index and index>=0 and rep.get(index),"Unknown railroad crossing resource")
    pt.crossing=index;crossings[pt.id]={resource=resource,index=index}
   end
  end
  local function attach(row)
   local a,b=byId[row.comp.node0],byId[row.comp.node1]
   assert(a and b,"Missing road endpoint");assert(dist2d(a.pos,b.pos)>=5,"Road fragment too short")
   edges[#edges+1]=row;a.added[#a.added+1]=row;b.added[#b.added+1]=row
  end
  for id,s in pairs(splitEdges)do
   local e,u=s.edge,s.param;local a,b=newId(),newId();local refs={[a]={},[b]={}}
   for _,pair in ipairs(listOf(e.objects))do
    local oid,kind=pair[1],pair[2];assert(not objects[oid],"Duplicate edge object")
    assert(e.roadType==api.type.enum.RoadType.STREET and (kind==api.type.enum.EdgeObjectType.STOP_LEFT or kind==api.type.enum.EdgeObjectType.STOP_RIGHT),"Only existing street-stop objects accepted")
    local eo=assert(getComponent(oid,"EDGE_OBJECT"),"Edge object component missing")
    local station=assert(getComponent(oid,"STATION"),"Stop station missing")
    local owner=ownerOf(oid);assert(not owner or owner<0 or owner==api.engine.util.getPlayer(),"Foreign stop object")
    local group=api.engine.system.stationGroupSystem.getStationGroup(oid);assert(group and group>=0 and getComponent(group,"STATION_GROUP"),"Station group missing")
    local lines={};local serving=listOf(api.engine.system.lineSystem.getLinesForStationGroup(group));assert(#serving<=32,"Stop has too many serving lines for atomic verification")
    for _,line in ipairs(serving)do lines[line]=toPlain(assert(getComponent(line,"LINE"),"Serving line disappeared"),0,nil,"Engine.Component.Line")end
    assert(api.engine.system.streetSystem.getEdgeForEdgeObject(oid)==id,"Edge object owner mismatch")
    assert(finite(eo.param) and eo.param>0 and eo.param<1,"Invalid edge object parameter")
    local anchor=stopAnchor(station,id);local projected=projectStop(e,anchor)
    assert(dist2d(anchor,s.point.pos)>=20,"Split too close to stop; preserve at least 20 metres")
    local target=projected<u and a or b;refs[target][#refs[target]+1]={oid,kind}
    objects[oid]={edge=target,sourceEdge=id,group=group,lines=lines,param=eo.param,anchor=anchor,
     projectedSourceParam=projected,projectedChildParam=projected<u and projected/u or (projected-u)/(1-u),
     before=toPlain(eo,0,nil,"Engine.Component.EdgeObject"),station=toPlain(station,0,nil,"Station"),owner=ownerOf(oid)}
   end
   -- Value-copy native component before replacing geometry; never edit live userdata.
   for _,r in ipairs({{id=a,node0=e.node0,node1=s.point.id,p0=vec(toPlain(e.position0,0,nil,"Vec3f")),p1=s.point.pos,t0=scale(e.tangent0,u),t1=scale(s.tangent,u)},
    {id=b,node0=s.point.id,node1=e.node1,p0=s.point.pos,p1=vec(toPlain(e.position1,0,nil,"Vec3f")),t0=scale(s.tangent,1-u),t1=scale(e.tangent1,1-u)}})do
    local row=api.type.SegmentAndEntity.new();row.entity=r.id;row.type=e.roadType==api.type.enum.RoadType.TRACK and 1 or 0
    -- Assign fields rather than aliasing Lua-table fixtures or an engine component.
    row.comp.node0=r.node0;row.comp.node1=r.node1;row.comp.position0=V3(r.p0.x,r.p0.y,r.p0.z);row.comp.position1=V3(r.p1.x,r.p1.y,r.p1.z)
    row.comp.tangent0=V3(r.t0.x,r.t0.y,r.t0.z);row.comp.tangent1=V3(r.t1.x,r.t1.y,r.t1.z)
    row.comp.type=e.type;row.comp.typeIndex=e.typeIndex;row.comp.laneConfigs=e.laneConfigs;row.comp.roadTemplate=e.roadTemplate
    row.comp.roadStyle=e.roadStyle;row.comp.roadType=e.roadType;row.comp.roadDevelopmentLocked=e.roadDevelopmentLocked
    row.comp.edgeDecorations=e.edgeDecorations;row.comp.objects=refs[r.id]
    local street=getComponent(id,"BASE_EDGE_STREET");if street then row.streetEdge=street end
    attach(row)
   end
   remap[e.node0]=remap[e.node0] or {};remap[e.node0][id]=a
   remap[e.node1]=remap[e.node1] or {};remap[e.node1][id]=b
  end
  -- Replace connected tunnel neighbors without moving or splitting them. Their
  -- geometry participates in the same native collision/structure proposal.
  for id,e in pairs(clones)do if not splitEdges[id] then
   local row=api.type.SegmentAndEntity.new();row.entity=newId();row.type=e.roadType==api.type.enum.RoadType.TRACK and 1 or 0
   row.comp.node0=e.node0;row.comp.node1=e.node1;row.comp.position0=e.position0;row.comp.position1=e.position1
   row.comp.tangent0=e.tangent0;row.comp.tangent1=e.tangent1;row.comp.type=e.type;row.comp.typeIndex=e.typeIndex
   row.comp.laneConfigs=e.laneConfigs;row.comp.roadTemplate=e.roadTemplate;row.comp.roadStyle=e.roadStyle
   row.comp.roadType=e.roadType;row.comp.roadDevelopmentLocked=e.roadDevelopmentLocked;row.comp.edgeDecorations=e.edgeDecorations;row.comp.objects={}
   local street=getComponent(id,"BASE_EDGE_STREET");if street then row.streetEdge=street end
   attach(row);remove[#remove+1]=id;splitEdges[id]={preservedNeighbor=true}
   for _,nodeId in ipairs({e.node0,e.node1})do remap[nodeId]=remap[nodeId] or {};remap[nodeId][id]=row.entity end
  end end
  assert(#edges<=48,"Expanded structure proposal exceeds 48 segments")
  local used,pairsSeen,resources={},{},{};local total=0
  for specIndex,spec in ipairs(g.edges)do
   keys(spec,{from=true,to=true,template=true,tangent0=true,tangent1=true,structure=true,structure_resource=true})
   local ai,bi=entity(spec.from)+1,entity(spec.to)+1;local a,b=pts[ai],pts[bi];assert(a and b and ai~=bi,"Invalid graph edge indices")
   local pair=math.min(ai,bi)..":"..math.max(ai,bi);assert(not pairsSeen[pair],"Duplicate graph edge");pairsSeen[pair]=true;used[ai]=true;used[bi]=true
   for _,old in ipairs(a.old)do assert(not ((old.comp.node0==a.id and old.comp.node1==b.id) or (old.comp.node1==a.id and old.comp.node0==b.id)),"Graph duplicates an existing road edge")end
   local len=dist2d(a.pos,b.pos);assert(len>=10 and len<=200,"Each graph span must be 10-200 metres")
   -- Replacement graphs deliberately have no native preview. They cannot be
   -- used to introduce an unpreviewed steep new span; put that span in a
   -- separate native-preview batch. Pure curve-preserving splits add no span.
   if #remove>0 then assert(math.abs(b.pos.z-a.pos.z)/len<=.12,
    "Steep new span requires a separate native-preview graph without removals") end
   total=total+len
   local name,tpl=resolveStreetTemplate(text(spec.template));assert(tpl.roadType==api.type.enum.RoadType.STREET or (allowRail and tpl.roadType==api.type.enum.RoadType.TRACK),"Rail templates require an explicit crossing")
   resources[name]={lanes=toPlain(tpl.laneConfigs,0,nil,{element="LaneConfig"}),style=tpl.streetStyle}
   local delta={x=b.pos.x-a.pos.x,y=b.pos.y-a.pos.y,z=b.pos.z-a.pos.z}
   local t0,t1=spec.tangent0 and vec(spec.tangent0) or delta,spec.tangent1 and vec(spec.tangent1) or delta
   for _,t in ipairs({t0,t1})do local l=math.sqrt(t.x*t.x+t.y*t.y);assert(l>=len*.25 and l<=len*2 and (t.x*delta.x+t.y*delta.y)/(l*len)>.5,"Sharp or reversing graph tangent")end
   local row=newStreetEdge(newId(),a.id,b.id,a.pos,b.pos,t0,t1,name,tpl)
   if tpl.roadType==api.type.enum.RoadType.TRACK then row.type=1;row.comp.roadType=api.type.enum.RoadType.TRACK end
   local structure=spec.structure or "ground"
   if structure=="ground" then
    assert(spec.structure_resource==nil,"Ground road has structure resource")
    assert(not api.engine.terrain.isOnWater(V2(a.pos.x,a.pos.y)) and not api.engine.terrain.isOnWater(V2(b.pos.x,b.pos.y)),"Ground road node in water")
   else
    assert(structure=="bridge" or structure=="tunnel","Unknown road structure")
    local rep=assert(structure=="bridge" and api.res.bridgeTypeRep or api.res.tunnelTypeRep,"Structure repository unavailable")
    local resource=text(spec.structure_resource);local index=rep.find(resource);assert(index and index>=0 and rep.get(index),"Unknown native structure resource")
    row.comp.type=structure=="bridge" and api.type.enum.BaseEdgeType.BRIDGE or api.type.enum.BaseEdgeType.TUNNEL;row.comp.typeIndex=index
    resources[structure..":"..resource]={index=index}
   end
   attach(row);explicitEdges[specIndex]=row
  end
  assert(#edges<=48,"Expanded graph exceeds 48 segments")
  for i=1,#pts do assert(used[i] or g.nodes[i].split,"Unused graph node")end
  assert(total<=3000,"Graph batch exceeds 3000 metres")
  -- At every affected node: retain old turns (remapping split references), then
  -- add only the turns involving genuinely new arms. Implicit old config is
  -- materialized from native lane directions. Pedestrian routing remains native.
  for id,pt in pairs(byId)do
   local adjacent,existing={},{};local replacements=remap[id] or {}
   for _,row in ipairs(pt.old)do if not splitEdges[row.entity] then adjacent[#adjacent+1]=row;existing[row.entity]=true end end
   for _,row in ipairs(pt.added)do adjacent[#adjacent+1]=row end
   assert(#adjacent<=8,"Road junction exceeds eight arms")
   table.sort(adjacent,function(a,b)return a.entity<b.entity end)
   local roads,tracks={},{}
   for _,row in ipairs(adjacent)do local target=row.comp.roadType==api.type.enum.RoadType.TRACK and tracks or roads;target[#target+1]=row end
   if #tracks>0 and #roads>0 then
    assert(pt.crossing~=nil and #tracks==2 and #roads==2 and not pt.cfg,"Mixed networks require an explicit two-road/two-track crossing")
    if pt.preservedCrossing then
     assert(#pt.old==4,"Existing crossing topology changed")
     local expected={};for _,r in ipairs(pt.old)do expected[replacements[r.entity] or r.entity]=true end
     for _,r in ipairs(adjacent)do assert(expected[r.entity],"Cannot add arms to a preserved crossing")end
    end
    local function direction(row)
     local e=row.comp;assert(e.type==api.type.enum.BaseEdgeType.NORMAL,"Level crossing must be ground infrastructure")
     local t=id==e.node0 and e.tangent0 or e.tangent1;local sign=id==e.node0 and 1 or -1
     local len=math.sqrt(t.x*t.x+t.y*t.y);assert(len>0 and math.abs(t.z)/len<=.03,"Crossing slope exceeds 3 percent")
     return {x=sign*t.x/len,y=sign*t.y/len}
    end
    local function dot(a,b)return a.x*b.x+a.y*b.y end
    local ra,rb,ta,tb=direction(roads[1]),direction(roads[2]),direction(tracks[1]),direction(tracks[2])
    assert(dot(ra,rb)<-.98 and dot(ta,tb)<-.98 and math.abs(dot(ra,ta))<.71,"Crossing requires straight pairs and 45-135 degree intersection")
    crossings[id].edges=adjacent
   elseif pt.crossing~=nil then error("Crossing requires both road and railway",0)end
   if #tracks>0 then
    -- Native railway/crossing connectivity is generated from topology. Only
    -- default empty rail endpoint configs may be removed; custom ones stay blocked.
    if pt.cfg then
     local cfg=pt.cfg
     assert(#listOf(cfg.laneConnections)==0 and #listOf(cfg.crosswalks)==0 and not cfg.doubleSlipSwitch and not cfg.userModifiedTrafficLightStates,"Custom rail node config not accepted")
     removeConfigs[#removeConfigs+1]=id
    end
    assert(not pt.junction,"Road signal plan cannot target rail nodes")
   elseif #adjacent>=2 or pt.cfg then
    local cfg=pt.cfg;local out=defaultConfig(id);local turns,walks,seen={},{},{}
    local incoming,outgoing={},{}
    for _,r in ipairs(adjacent)do incoming[r.entity],outgoing[r.entity]=lanes(id,r.comp) end
    local function add(a,b,i,j,r,t)
     local key=table.concat({a,b,i,j},":");assert(not seen[key],"Duplicate turn");seen[key]=true
     assert(#turns<512,"Junction exceeds 512 explicit vehicle turns")
     local l=api.type.LaneConnection.new();l.segment0=a;l.segment1=b;l.lane0=i;l.lane1=j;l.withRoad=r;l.withTram=t;turns[#turns+1]=l
    end
    local function lane(list,index)for _,l in ipairs(list or {})do if l.index==index then return l end end end
    if cfg then
     assert(#pt.old<2 or #listOf(cfg.laneConnections)>0,"Existing multi-arm node has explicit empty turns; investigate before editing")
     local hasNewArm=#adjacent>#pt.old
     if hasNewArm and not(pt.junction and pt.junction.extend=="preserve") then
      assert(cfg.doubleSlipSwitch==false and cfg.userModifiedTrafficLightStates==false and cfg.trafficLightPreference==api.type.enum.TrafficLightPreference.AUTO
       and cfg.trafficLightConfig.trafficLightType==-1,"Adding arms to custom signals requires an explicit signal plan")
      local custom=readField(cfg,"userModifiedLaneConnections");assert(custom==nil or custom==false,"Adding arms to custom turns requires explicit turn plan")
     end
     out.comp.trafficLightPreference=cfg.trafficLightPreference;out.comp.trafficLightConfig=cfg.trafficLightConfig
     out.comp.doubleSlipSwitch=cfg.doubleSlipSwitch;out.comp.userModifiedTrafficLightStates=cfg.userModifiedTrafficLightStates
     local custom=readField(cfg,"userModifiedLaneConnections");if custom~=nil then out.comp.userModifiedLaneConnections=custom end
     for _,l in ipairs(cfg.laneConnections)do
      local a,b=replacements[l.segment0] or l.segment0,replacements[l.segment1] or l.segment1
      local la,lb=lane(incoming[a],l.lane0),lane(outgoing[b],l.lane1);assert(la and lb and a~=b,"Old turn does not match native lanes")
      local r,t=compatible(la,lb);assert((not l.withRoad or r) and (not l.withTram or t),"Old turn mode mismatch")
      add(a,b,l.lane0,l.lane1,l.withRoad,l.withTram)
     end
     local walkSeen={};for _,e in ipairs(cfg.crosswalks)do local v=replacements[e] or e;assert(incoming[v] and not walkSeen[v],"Unknown or duplicate crosswalk");walkSeen[v]=true;walks[#walks+1]=v end
     removeConfigs[#removeConfigs+1]=id
    end
    for old,new in pairs(replacements)do existing[new]=true end
    for _,a in ipairs(adjacent)do for _,b in ipairs(adjacent)do if a.entity~=b.entity and (not cfg or not(existing[a.entity] and existing[b.entity])) then
     for _,i in ipairs(incoming[a.entity])do for _,j in ipairs(outgoing[b.entity])do
      local r,t=compatible(i,j);if r or t then local k=table.concat({a.entity,b.entity,i.index,j.index},":");if not seen[k] then add(a.entity,b.entity,i.index,j.index,r,t)end end
     end end
    end end end
    local policy=pt.junction
    if policy and (policy.blocked_turns~=nil or policy.crosswalk_edges~=nil) then
     local function arm(index)
      assert(finite(index) and index%1==0 and index>=0,"Invalid explicit edge index")
      local row=assert(explicitEdges[index+1],"Unknown explicit edge index")
      assert(row.comp.node0==id or row.comp.node1==id,"Explicit edge is not incident to junction")
      assert(row.comp.roadType==api.type.enum.RoadType.STREET,"Road-only junction policy")
      return row
     end
     local blocked={}
     for _,pair in ipairs(policy.blocked_turns or {})do
      keys(pair,{from_edge=true,to_edge=true});local a,b=arm(pair.from_edge).entity,arm(pair.to_edge).entity
      local key=a..":"..b;assert(a~=b and not blocked[key],"Duplicate or self blocked turn");blocked[key]=true
     end
     local kept,found={},{}
     for _,turn in ipairs(turns)do local key=turn.segment0..":"..turn.segment1
      if blocked[key] then found[key]=true else kept[#kept+1]=turn end
     end
     for key in pairs(blocked)do assert(found[key],"Blocked turn does not exist")end
     assert(#kept>0,"Cannot block all junction turns");turns=kept
     local seenWalk={}
     for _,index in ipairs(policy.crosswalk_edges or {})do
      local row=arm(index);assert(not seenWalk[row.entity],"Duplicate crosswalk")
      local directions={}
      for _,lane in ipairs(row.comp.laneConfigs)do if lane.transportModes[api.type.enum.TransportMode.PERSON]then directions[tostring(lane.forward)]=true end end
      assert(directions['true'] and directions['false'],"Crosswalk needs pedestrian lanes on both sides")
      seenWalk[row.entity]=true;walks[#walks+1]=row.entity
     end
    end
    out.comp.laneConnections=turns;out.comp.crosswalks=walks
    assert(not cfg or not cfg.doubleSlipSwitch,"Double slip switch is not a road junction")
    if policy and policy.signals then
     out.comp.trafficLightPreference=api.type.enum.TrafficLightPreference.YES
     out.comp.trafficLightConfig=signalPlan(policy.signals,#turns+#walks);out.comp.userModifiedTrafficLightStates=true
    elseif cfg and #turns>#listOf(cfg.laneConnections) and policy and policy.extend=="preserve" and
      (cfg.userModifiedTrafficLightStates or cfg.trafficLightPreference==api.type.enum.TrafficLightPreference.YES or cfg.trafficLightConfig.trafficLightType~=-1) then
     assert(not cfg.doubleSlipSwitch,"Double slip switch is not a road junction")
     out.comp.trafficLightConfig=extendSignals(cfg.trafficLightConfig,#listOf(cfg.laneConnections),#turns,#walks,policy.phase_duration or 10)
     out.comp.userModifiedTrafficLightStates=true
    end
    configs[#configs+1]=out
   end
  end
  local rc={};for id,v in pairs(crossings)do rc[id]=v.index end;if next(rc)then sp.node2rcType=rc end
  sp.nodesToAdd=nodes;sp.edgesToAdd=edges;if #remove>0 then sp.edgesToRemove=remove end;sp.nodeConfigsToAdd=configs;sp.nodeConfigsToRemove=removeConfigs
  -- Deterministic ordering is part of the token identity, irrespective of hash iteration.
  table.sort(edges,function(a,b)return a.entity<b.entity end);table.sort(configs,function(a,b)return a.entity<b.entity end);table.sort(remove);table.sort(removeConfigs)
  local crossingIdentity={};for id,c in pairs(crossings)do crossingIdentity[id]={index=c.index,resource=c.resource,originalEntity=c.originalEntity}end
  local identity={graph=g,edges=oldEdges,configs=oldConfigs,resources=resources,objects=objects,crossings=crossingIdentity}
  return {proposal=p,points=byId,oldEdges=oldEdges,oldConfigs=oldConfigs,splitEdges=splitEdges,objects=objects,crossings=crossings,signature=stableDataSignature(identity),length=total}
 end
 local function check(design)
  if #listOf(design.proposal.streetProposal.edgesToRemove)>0 then
   -- Known engine assertion: do not call makeProposalData with removed segments.
   return {ok=true,structural_only=true,nativePreviewPassed=false,collisionsUnchecked=true,collisions={}}
  end
  local r=previewProposal(design.proposal);r.nativePreviewPassed=r.ok==true;return r
 end
 commands.get_network_template=function(args)
  local name,tpl=resolveStreetTemplate(args.template)
  return {resource=name,roadType=enumName("RoadType",tpl.roadType),laneConfigs=toPlain(tpl.laneConfigs,0,nil,{element="LaneConfig"}),streetStyle=tpl.streetStyle}
 end
 commands.list_road_structures=function(args)
  local result={};for _,kind in ipairs({"bridge","tunnel","crossing"})do
   local rep=kind=="bridge" and api.res.bridgeTypeRep or kind=="tunnel" and api.res.tunnelTypeRep or api.res.railroadCrossingTypeRep;local rows={}
   if rep then for id,name in pairs(rep.getAll())do rows[#rows+1]={id=id,resource=name}end;table.sort(rows,function(a,b)return a.id<b.id end)end
   result[kind]=rows
  end;return result
 end
 commands.preview_road_graph=function(args)
  local d=prepare(args);local r=check(d);r.preview=true;r.serviceConnectivityVerified=false
  r.specialCases={objects={},crossings={},preservedTunnelNeighbors={}};for id,v in pairs(d.splitEdges)do if v.preservedNeighbor then r.specialCases.preservedTunnelNeighbors[#r.specialCases.preservedTunnelNeighbors+1]=id end end;for id,o in pairs(d.objects)do r.specialCases.objects[#r.specialCases.objects+1]={id=id,targetEdge=o.edge,nativeParam=o.param,projectedSourceParam=o.projectedSourceParam,projectedChildParam=o.projectedChildParam}end
  for id,c in pairs(d.crossings)do r.specialCases.crossings[#r.specialCases.crossings+1]={node=id,resource=c.resource,index=c.index}end
  r.junctionPlans={};for _,c in ipairs(d.proposal.streetProposal.nodeConfigsToAdd)do
   r.junctionPlans[#r.junctionPlans+1]={node=c.entity,turnCount=#listOf(c.comp.laneConnections),crosswalkCount=#listOf(c.comp.crosswalks),customSignals=c.comp.userModifiedTrafficLightStates}
  end
  r.length=d.length;r.segments=#d.proposal.streetProposal.edgesToAdd;r.replacedEdges=#listOf(d.proposal.streetProposal.edgesToRemove)
  if r.ok and not r.critical and not r.blocked and not r.placementBlocked and #r.collisions==0 then
   saved.serial=saved.serial+1;local token="road-graph:"..epoch..":"..saved.serial
   saved.previews[token]={args=args,signature=d.signature,clock=assert(wallClock()),player=api.engine.util.getPlayer()};checkpoint();r.preview_token=token
  end;return r
 end
 commands.commit_road_graph=function(args)
  local r=saved.previews[args.preview_token];saved.previews[args.preview_token]=nil
  local op={id=requestId,phase="pre_dispatch",built=false,verified=false,directedPathsVerified=false,serviceConnectivityVerified=false}
  saved.operations[args.preview_token]=op;checkpoint();assert(r,"Unknown or consumed road graph preview")
  local now=assert(wallClock());assert(now>=r.clock and now-r.clock<=60,"Road graph preview expired");assert(r.player==api.engine.util.getPlayer(),"Player changed")
  local d=prepare(r.args);assert(d.signature==r.signature,"Road graph identity changed")
  local c=check(d);assert(c.ok and not c.critical and not c.blocked and not c.placementBlocked and #c.collisions==0,"Road graph no longer buildable")
  assert(type(args.backup_save)=="string" and #args.backup_save>0,"Record preconstruction backup slot")
  local expectedConfigs={};for _,row in ipairs(d.proposal.streetProposal.nodeConfigsToAdd)do expectedConfigs[row.entity]=networkNodeConfigSnapshot(row.comp)end
  local before=edgeSet();local adjacencyBefore=adjacencySignature()
  op.phase="dispatching";op.backup_save=args.backup_save;checkpoint()
  local callbackSeen,nativeRejected=false,false
  applyProposal(d.proposal,false,function(ok,res)
   callbackSeen=true;nativeRejected=ok==false;op.built=ok==true
   -- Bounded fields from the callback only; never evaluate a second removal proposal.
   local pd=tryField(function()return res.data end) or tryField(function()return res.proposalData end) or res
   local errors=tryField(function()return pd.errorState end)
   op.nativeResult={callbackSeen=true,success=ok==true,explicitRejection=ok==false,
    critical=tryField(function()return errors.critical end),messages={},collisions={}}
   for i,v in ipairs(listOf(tryField(function()return errors.messages end)))do
    if i>32 then break end;if type(v)=="string" then op.nativeResult.messages[#op.nativeResult.messages+1]=v:sub(1,512)end
   end
   for i,v in ipairs(listOf(tryField(function()return pd.collisionInfo.collisionEntities end)))do
    if i>64 then break end;local id=tryField(function()return v.entity end)
    if finite(id) and id%1==0 then op.nativeResult.collisions[#op.nativeResult.collisions+1]=id end
   end
  end)
  if callbackSeen and nativeRejected then
   -- A negative callback alone is not rollback proof. Re-read the complete touched
   -- graph (including stops/lines/configs), and require global edge/adjacency identity.
   local readOk,unchanged=pcall(function()
    return stableDataSignature(edgeSet())==stableDataSignature(before)
     and adjacencySignature()==adjacencyBefore
     and prepare(r.args).signature==d.signature
   end)
   if readOk and unchanged then
    op.phase="rejected_unchanged";op.rejectionVerified=true;op.retryAllowed=false
    op.verificationScope="explicit native rejection; original touched graph and global street adjacency unchanged"
    checkpoint();return op
   end
  end
  if op.built then
   local after=edgeSet();local fresh={};for id in pairs(after)do if not before[id] then fresh[#fresh+1]=id end end
   local map,used={},{};local sp=d.proposal.streetProposal;local verified=#fresh==#sp.edgesToAdd
   local function close(a,b)return a and b and math.abs(a.x-b.x)<.02 and math.abs(a.y-b.y)<.02 and math.abs(a.z-b.z)<.02 end
   for _,n in ipairs(sp.nodesToAdd)do
    local found
    for id in pairs(api.engine.system.streetSystem.getNode2SegmentMap())do local comp=getComponent(id,"BASE_NODE")
     if comp and close(comp.position,n.comp.position)then assert(not found,"Ambiguous graph node receipt");found=id end
    end
    if not found or not getComponent(found,"TRANSPORT_NETWORK") then verified=false else map[n.entity]=found end
   end
   for _,row in ipairs(sp.edgesToAdd)do
    local e=row.comp;local found
    for _,id in ipairs(fresh)do local got=getComponent(id,"BASE_EDGE")
     if got and got.node0==(map[e.node0] or e.node0) and got.node1==(map[e.node1] or e.node1)
      and got.roadTemplate==e.roadTemplate and got.type==e.type and got.typeIndex==e.typeIndex
      and got.roadStyle==e.roadStyle and got.roadDevelopmentLocked==e.roadDevelopmentLocked
      and stableDataSignature(toPlain(got.edgeDecorations))==stableDataSignature(toPlain(e.edgeDecorations))
      and stableDataSignature(toPlain(got.objects))==stableDataSignature(toPlain(e.objects))
      and close(got.position0,e.position0) and close(got.position1,e.position1) and close(got.tangent0,e.tangent0) and close(got.tangent1,e.tangent1)
      and stableDataSignature(toPlain(got.laneConfigs,0,nil,{element="LaneConfig"}))==stableDataSignature(toPlain(e.laneConfigs,0,nil,{element="LaneConfig"})) then
       assert(not found and not used[id],"Ambiguous graph edge receipt");found=id
     end
    end
    if not found or not getComponent(found,"TRANSPORT_NETWORK") then verified=false else map[row.entity]=found;used[found]=true end
   end
   for id,old in pairs(d.oldEdges)do
    if d.splitEdges[id] then if getComponent(id,"BASE_EDGE") then verified=false end
    elseif not getComponent(id,"BASE_EDGE") or stableDataSignature(snapshot(id))~=stableDataSignature(old.value) or ownerOf(id)~=old.owner
     or stableDataSignature(toPlain(getComponent(id,"BASE_EDGE_STREET"),0,nil,"Engine.Component.BaseEdgeStreet"))~=stableDataSignature(old.street) then verified=false end
   end
   op.junctions={}
   for _,row in ipairs(sp.nodeConfigsToAdd)do
    local id=map[row.entity] or row.entity;local cfg=getComponent(id,"BASE_NODE_CONFIG")
    local good=cfg~=nil and getComponent(id,"TRANSPORT_NETWORK")~=nil
    local expected=expectedConfigs[row.entity]
    if good then
     good=configSignature(cfg)==configSignature(expected,map)
     local custom=readField(cfg,"userModifiedLaneConnections");local wanted=expected.userModifiedLaneConnections
     if (custom==true)~=(wanted==true) then good=false end
     if expected.userModifiedTrafficLightStates then
      local actualTurns={};for _,l in ipairs(cfg.laneConnections)do actualTurns[#actualTurns+1]={l.segment0,l.segment1,l.lane0,l.lane1,l.withRoad,l.withTram}end
      local wantedTurns={};for _,l in ipairs(expected.laneConnections)do wantedTurns[#wantedTurns+1]={map[l.segment0] or l.segment0,map[l.segment1] or l.segment1,l.lane0,l.lane1,l.withRoad,l.withTram}end
      if stableDataSignature(actualTurns)~=stableDataSignature(wantedTurns)then good=false end
     end
     if expected.userModifiedTrafficLightStates or expected.trafficLightPreference~=api.type.enum.TrafficLightPreference.AUTO then
      if stableDataSignature(toPlain(cfg.trafficLightConfig,0,nil,"Engine.Component.TrafficLightConfig"))~=stableDataSignature(expected.trafficLightConfig)then good=false end
     end
     local pt=d.points[row.entity];local adjacency={};local count=0
     for _,e in ipairs(pt.old)do if not d.splitEdges[e.entity] then adjacency[e.entity]=true;count=count+1 end end
     for _,e in ipairs(pt.added)do adjacency[map[e.entity] or e.entity]=true;count=count+1 end
     local actual=listOf(api.engine.system.streetSystem.getNodeSegments(id));if #actual~=count then good=false end
     for _,eid in ipairs(actual)do if not adjacency[eid] then good=false end end
    end
    if good then
     local count=#listOf(cfg.laneConnections)+#listOf(cfg.crosswalks)
     for _,phase in ipairs(cfg.trafficLightConfig.states)do
      if not finite(phase.duration) or not finite(phase.minDuration) or phase.minDuration<0 or phase.duration<phase.minDuration or type(phase.canSkip)~="boolean" then good=false end
      local seen={};for _,v in ipairs(phase.lockedLanes)do if not finite(v) or v%1~=0 or v<0 or v>=count or seen[v]then good=false end;seen[v]=true end
     end
    end
    op.junctions[#op.junctions+1]={node=id,configurationVerified=good,directedPathsVerified=false};if not good then verified=false end
   end
   op.preservedObjects={}
   for id,wanted in pairs(d.objects)do
    local eo=getComponent(id,"EDGE_OBJECT");local st=getComponent(id,"STATION");local good=eo~=nil and st~=nil
    if good then
     local value=toPlain(eo,0,nil,"Engine.Component.EdgeObject");local old=wanted.before
     local placementRead,placementGood=pcall(preservedStopPlacement,st,map[wanted.edge],value,wanted)
     good=math.abs(value.param-wanted.param)<.0001 and value.edgeObjectConstruction==old.edgeObjectConstruction
      and placementRead and placementGood and stableDataSignature(value.params)==stableDataSignature(old.params)
      and sameObjectValue(toPlain(st,0,nil,"Station"),remapObjectReferences(wanted.station,wanted.sourceEdge,map[wanted.edge])) and ownerOf(id)==wanted.owner
      and api.engine.system.stationGroupSystem.getStationGroup(id)==wanted.group
      and api.engine.system.streetSystem.getEdgeForEdgeObject(id)==map[wanted.edge]
    end
    for line,beforeLine in pairs(wanted.lines)do
     local currentLine=getComponent(line,"LINE")
     if not currentLine or stableDataSignature(toPlain(currentLine,0,nil,"Engine.Component.Line"))~=stableDataSignature(beforeLine)then good=false end
    end
    op.preservedObjects[#op.preservedObjects+1]={id=id,edge=map[wanted.edge],stationGroup=wanted.group,verified=good};if not good then verified=false end
   end
   op.railroadCrossings={}
   for node,wanted in pairs(d.crossings)do
    local actual=map[node] or node;local rcid=api.engine.system.railRoadCrossingSystem.getRailroadCrossingForNode(actual)
    local rc=rcid and rcid>=0 and getComponent(rcid,"RAILROAD_CROSSING");local good=rc and rc.typeIndex==wanted.index or false
    local current={};for _,e in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(actual)))do current[e]=true end
    local count=0;for _ in pairs(current)do count=count+1 end;good=good and count==4
    for _,e in ipairs(wanted.edges)do if not current[map[e.entity] or e.entity]then good=false end end
    op.railroadCrossings[#op.railroadCrossings+1]={node=actual,entity=rcid,verified=good,directedPathsVerified=false};if not good then verified=false end
   end
   op.edges=fresh;op.entityMap=map;op.verified=verified
  end
  op.phase=op.verified and "verified" or "unconfirmed";checkpoint();return op
 end
 commands.get_road_graph_operation=function(args)
  local op=saved.operations[args.operation_id]
  if not op then for _,candidate in pairs(saved.operations)do if candidate.id==args.operation_id then assert(not op,"Ambiguous graph operation");op=candidate end end end
  return assert(op,"Unknown graph operation")
 end
 for _,name in ipairs({"get_network_template","list_road_structures","preview_road_graph","commit_road_graph","get_road_graph_operation"})do ENGINE_COMMANDS[name]=true end
end


-- Engine-side UI construction transport. Deliberately separate from read queries.
local uiBuild = {}
do
 local SAVED_MUTATION_LIMIT=1024 -- active receipts; reset retires terminal IDs without forgetting them
 local QUOTA_LIMIT=256
 local REPLAY_ID_LIMIT=65536 -- finite storage guard, never reset or silently evict
 local schemas={get_town_cargo_supply={town="entity",include_passengers="bool"},get_industry_bonuses={industry="entity"},get_town_population={town="entity"},get_town_building_stats={ids="entity_ids"},
  get_component_collection={id="entity",component="text",field="text",offset="offset",limit="page_limit"},
  begin_snapshot={snapshot_kind="snapshot_kind",bounds="bounds",spacing="snapshot_spacing",start_construction="entity",end_construction="entity",whole_map="bool"},
  read_snapshot_page={snapshot="token",offset="byte_offset"},release_snapshot={snapshot="token"},
  preview_line_edit={line="entity",stops="line_edits"},
  preview_line_terminal={line="entity",stop_index="stop_index",station_index="stop_index",terminal="terminal_index"},
  preview_headquarters_access={town="entity",road="entity",x="number",y="number",z="number",rotation="number"},
  preview_subvention={uid="entity"},commit_subvention={preview_token="token"},get_subvention_operation={operation_id="token"},
  get_facility_layout={entity="entity",offset="offset",limit="page_limit"},get_facility_inventory={entity="entity"},
  preview_depot_removal={entity="entity"},commit_depot_removal={preview_token="token",backup_save="save_slot"},get_depot_removal_operation={operation_id="token"},
  preview_test_removal={entity="entity"},commit_test_removal={preview_token="token"},
  get_validation_state={},
  reset_operation_quota={expected_round="offset",expected_used="offset",expected_count="offset"},
  preview_flatten_terrain={bounds="bounds",target_height="number",max_height_change="number",max_edge_grade="number",transition_width="number"},
  commit_flatten_terrain={preview_token="token",backup_save="save_slot"},get_terrain_operation={operation_id="token"},

  get_stock_activity={stock_list="entity",cargo="entity"},get_town_deliveries={town="entity"},
  preview_road_upgrade={edge="entity",street_type="text"},
  preview_street_stop={edge="entity",param="stop_param",side="stop_side",two_sided="bool"},commit_edge_edit={preview_token="token"},
  preview_facility_module={entity="entity",slot="entity",resource="text"},
  preview_facility_parameter={entity="entity",key="text",value="number"},
  build_headquarters={town="entity",x="number",y="number",z="number",rotation="number"},
  preview_industry={resource="text",x="number",y="number",rotation="number",on_water="bool",seed="text"},
  commit_industry={preview_token="token"},get_industry_operation={operation_id="token"},
  preview_town_cargo_needs={town="entity",residential="cargo_ids",commercial="cargo_ids",industrial="cargo_ids",update_buildings="bool"},
  commit_town_cargo_needs={preview_token="token"},get_town_cargo_operation={operation_id="token"},
  preview_prospection={town="entity",resource="text"},commit_prospection={preview_token="token"},get_prospection_operation={operation_id="token"},
  preview_loan={action="loan_action",offer_type="text",loan_id="entity"},commit_loan={preview_token="token"},get_loan_operation={operation_id="token"},

  get_network_template={template="text"},list_road_structures={},preview_road_graph={graph="road_graph",isolated_test="bool"},commit_road_graph={preview_token="token",backup_save="save_slot"},get_road_graph_operation={operation_id="token"},
  list_network_templates={search="text",offset="offset",limit="page_limit"},preview_network={start="endpoint",["end"]="endpoint",via="via_points",template="text",reset_empty_rail_ports="bool",reset_empty_road_ports="bool",connect_road_junctions="bool"},commit_network={preview_token="token"},
  get_vehicle_cargo={vehicle="entity",cargo="entity",include_entities="bool",offset="offset",limit="page_limit"},get_sim_entity={id="entity"},get_stop_cargo={line="entity",stop_index="stop_index",cargo="entity"},get_stock_cargo={stock_list="entity",cargo="entity",stock_quality="bool",diagnostic="bool"},
  list_multiple_units={offset="offset",limit="page_limit"},preview_multiple_unit={depot="entity",resource="text"},
  preview_consist={depot="entity",models="model_ids"},commit_consist={preview_token="token"},
  preview_depot={x="number",y="number",z="number",rotation="number",carrier="depot_carrier",frontage_node="entity"},
  preview_station={x="number",y="number",z="number",rotation="number",cargo="bool",size="station_size",frontage_node="entity"},
  preview_rail_station={x="number",y="number",rotation="number",tracks="tracks",length="rail_length",specialization="specialization",cargo="bool"},
  commit_structure={preview_token="token"},
  delete_line={line="entity"},sell_vehicles={vehicles="one_entity"},list_cargo_types={},
  preview_line_stop={line="entity",stop_index="stop_index",loads="cargo_ids",max_load="ratio",force_unload="bool",extra_wait="wait"},
  commit_line_stop={preview_token="token"},
  get_terrain={x="number",y="number"},find_nearby={x="number",y="number",radius="radius",limit="page_limit"},
  list_facility_resources={kind="text",search="text",offset="offset",limit="page_limit"},
  list_industry_resources={},list_prospections={},get_prospections={},get_notifications={include_history="bool",offset="offset",limit="page_limit"},get_loans={},get_subventions={assess="bool"},
  get_town_cargo_needs={town="entity"},get_terrain_operation_capabilities={},
  list_map_entities={kind="text",offset="offset",limit="page_limit",snapshot="token",ids_only="bool"},release_map_snapshot={snapshot="token"},
  get_terrain_grid={x="number",y="number",spacing="spacing",columns="page_limit",rows="page_limit",offset="offset",limit="page_limit",mode="text"},
  get_map_data={layer="text",offset="offset",limit="page_limit"},get_terrain_tile={tile_x="signed_integer",tile_y="signed_integer"},
  create_line={station_groups="groups",name="line_name"},
  buy_vehicles={depot="entity",model="text",count="one"},
  assign_vehicles={vehicles="one_entity",line="entity",stop_index="stop_index"},
  set_vehicle_stopped={vehicle="entity",stopped="bool"},set_game_speed={speed="game_speed",expected_speed="game_speed"},
  send_to_depot={vehicle="entity"},get_vehicle_motion={vehicle="entity",resolve_native_path="bool"},
  build_helipad={x="number",y="number",z="number",rotation="number"},
  build_heliport={x="number",y="number",z="number",rotation="number"},
  build_airfield={x="number",y="number",z="number",rotation="number"},
  preview_road={start="endpoint",["end"]="endpoint",street_type="text"},
  reconcile_road_rejection={request_id="request_id"},reconcile_network_rejection={request_id="request_id"},reconcile_depot_rejection={request_id="request_id"},reconcile_assignment_rejection={request_id="request_id",vehicle="entity",line="entity"},reconcile_town_cargo_rejection={request_id="request_id"},reconcile_subvention_rejection={request_id="request_id"},reconcile_facility_rejection={request_id="request_id"},
  commit_road={preview_token="token"},get_entity={id="entity",components="component_names"},list_street_types={filter="text"},
  survey_build_site={x="number",y="number"},list_facilities={},
  build_water_facility={x="number",y="number",z="number",rotation="number",kind="water_facility_kind",harbor_size="harbor_size"},
  build_warehouse={x="number",y="number",z="number",rotation="number",module_count="modules"},
  build_facility={source_entity="entity",x="number",y="number",z="number",rotation="number"},
  commit_facility={preview_token="token"},get_facility_config={entity="entity",offset="offset",limit="page_limit"},get_facility_access={entity="entity",person_graph="bool",person_geometry="bool"},check_road_junction_path={node="entity",from_edge="entity",to_edge="entity",mode="text"},
  check_network_junction_path={node="entity",from_edge="entity",to_edge="entity",mode="text"},
 }
 -- Only audited world-read commands may release incorrectly charged legacy slots.
 -- Previews, mutations, unknown commands and unresolved non-read requests stay protected.
 local pureEngineReads={get_town_cargo_supply=true,get_notifications=true,get_industry_bonuses=true,get_depot_removal_operation=true,get_network_template=true,list_road_structures=true,get_road_graph_operation=true,get_town_population=true,get_town_building_stats=true,get_component_collection=true,begin_snapshot=true,read_snapshot_page=true,release_snapshot=true,preview_headquarters_access=true,get_subvention_operation=true,get_facility_layout=true,get_validation_state=true,get_terrain_operation=true,get_stock_activity=true,get_town_deliveries=true,get_industry_operation=true,get_town_cargo_operation=true,get_prospection_operation=true,get_loan_operation=true,list_network_templates=true,list_multiple_units=true,get_vehicle_cargo=true,get_sim_entity=true,get_stop_cargo=true,get_stock_cargo=true,get_vehicle_motion=true,get_entity=true,list_street_types=true,survey_build_site=true,
  list_facilities=true,get_facility_config=true,get_facility_access=true,get_facility_inventory=true,check_road_junction_path=true,check_network_junction_path=true,
  list_cargo_types=true,get_terrain=true,find_nearby=true,list_facility_resources=true,
  list_industry_resources=true,list_prospections=true,get_prospections=true,get_loans=true,
  get_subventions=true,get_town_cargo_needs=true,get_terrain_operation_capabilities=true,
  list_map_entities=true,release_map_snapshot=true,get_terrain_grid=true,get_map_data=true,get_terrain_tile=true}
 local sent={};local sentReadOrder={}
 local function endpoint(value)
  if type(value)~="table" then return false end
  if value.node~=nil then
   for k in pairs(value) do if k~="node" then return false end end
   return type(value.node)=="number" and value.node%1==0 and value.node>=0 and value.node<2147483647
  end
  if value.x==nil or value.y==nil then return false end
  for k,v in pairs(value) do
   if (k~="x" and k~="y" and k~="z") or type(v)~="number" or v~=v or math.abs(v)==math.huge then return false end
  end
  return true
 end
 function uiBuild.validLineEdits(value)
  if type(value)~="table" or #value<2 or #value>32 then return false end
  local count=0
  for index,stop in pairs(value) do
   count=count+1
   if type(index)~="number" or index%1~=0 or index<1 or index>#value or type(stop)~="table" then return false end
   if (stop.source_index~=nil)==(stop.station_group~=nil) then return false end
   local allowed={source_index=true,station_group=true,station=true,terminal=true,loads=true,max_load=true,force_unload=true,extra_wait=true}
   for k,v in pairs(stop) do
    if not allowed[k] then return false end
    if k=="source_index" or k=="station_group" or k=="station" or k=="terminal" or k=="extra_wait" then
     local max=k=="source_index" and 31 or k=="station_group" and 2147483646 or k=="extra_wait" and 600 or 63
     if type(v)~="number" or v%1~=0 or v<0 or v>max then return false end
    elseif k=="force_unload" then if type(v)~="boolean" then return false end
    elseif k=="max_load" then if type(v)~="number" or v~=v or v<0 or v>1 then return false end
    elseif k=="loads" then
     if type(v)~="table" or #v>8 then return false end
     local seen,n={},0
     for i,c in pairs(v) do
      n=n+1
      if type(i)~="number" or i%1~=0 or i<1 or i>#v or type(c)~="number" or c%1~=0 or c<0 or c>255 or seen[c] then return false end
      seen[c]=true
     end
     if n~=#v then return false end
    end
   end
   if stop.station_group~=nil and (stop.station==nil or stop.terminal==nil or stop.loads==nil) then return false end
  end
  return count==#value
 end
 local function validate(cmd,args)
  local schema=schemas[cmd]
  assert(schema and type(args)=="table","Unsupported UI construction command or arguments")
  for key,value in pairs(args) do
   local kind=schema[key]
   local groups=false
   if kind=="model_ids" and type(value)=="table" and #value>=2 and #value<=8 then
    groups=true;local count=0
    for k,v in pairs(value) do
     count=count+1
     if type(k)~="number" or k%1~=0 or k<1 or k>#value or type(v)~="number" or v%1~=0 or v<0 or v>=2147483647 then groups=false end
    end
    groups=groups and count==#value
   end
   if kind=="cargo_ids" and type(value)=="table" and #value<=8 then
    groups=true;local count=0;local seen={}
    for k,v in pairs(value) do
     count=count+1
     if type(k)~="number" or k%1~=0 or k<1 or k>#value or type(v)~="number" or v%1~=0 or v<0 or v>255 or seen[v] then groups=false else seen[v]=true end
    end
    groups=groups and count==#value
   end
   if ((kind=="groups" and type(value)=="table" and #value>=2 and #value<=8) or (kind=="one_entity" and type(value)=="table" and #value==1)) then
    groups=true;local count=0
    for k,v in pairs(value) do
     count=count+1
     if type(k)~="number" or k%1~=0 or k<1 or k>#value or type(v)~="number" or v%1~=0 or v<0 or v>=2147483647 then groups=false end
    end
    groups=groups and count==#value
   end
   if kind=="via_points" and type(value)=="table" and #value<=3 then
    groups=true;local count=0
    for k,p in pairs(value) do count=count+1;if type(k)~="number" or k%1~=0 or k<1 or k>#value or not endpoint(p) or p.node then groups=false end end
    groups=groups and count==#value
   end
   if kind=="bounds" and type(value)=="table" and type(value.min)=="table" and type(value.max)=="table" then
    groups=true;local count=0;for k in pairs(value) do count=count+1;if k~="min" and k~="max" then groups=false end end
    for _,v in ipairs({value.min,value.max}) do local n=0;for k,x in pairs(v) do n=n+1;if (k~="x" and k~="y") or type(x)~="number" or x~=x or math.abs(x)==math.huge then groups=false end end;if n~=2 then groups=false end end
    groups=groups and count==2 and value.min.x<value.max.x and value.min.y<value.max.y
   end
   local componentNames=false
   if kind=="component_names" and type(value)=="table" and #value>=1 and #value<=16 then
    componentNames=true;local n,seen=0,{}
    for i,v in pairs(value) do
     n=n+1
     if type(i)~="number" or i%1~=0 or i<1 or i>#value or type(v)~="string" or #v>64 or not v:match("^[A-Z][A-Z0-9_]*$") or seen[v] then componentNames=false end
     seen[v]=true
    end
    componentNames=componentNames and n==#value
   end
   local entityIds=false
   if kind=="entity_ids" and type(value)=="table" and #value>=1 and #value<=16 then
    entityIds=true;local n,seen=0,{}
    for i,v in pairs(value) do
     n=n+1
     if type(i)~="number" or i%1~=0 or i<1 or i>#value or type(v)~="number" or v%1~=0 or v<0 or v>=2147483647 or seen[v] then entityIds=false end
     seen[v]=true
    end
    entityIds=entityIds and n==#value
   end
   local valid=entityIds or componentNames or (kind=="line_edits" and uiBuild.validLineEdits(value))
    or (kind=="snapshot_kind" and (value=="planning" or value=="route"))
    or (kind=="snapshot_spacing" and type(value)=="number" and value>=25 and value<=2000)
    or (kind=="byte_offset" and type(value)=="number" and value%1==0 and value>=0 and value<=8388608)
    or (kind=="game_speed" and type(value)=="number" and ({[0]=true,[1]=true,[2]=true,[4]=true})[value])
    or (kind=="terminal_index" and type(value)=="number" and value%1==0 and value>=0 and value<=63)
    or (kind=="save_slot" and type(value)=="string" and #value>=1 and #value<=80 and value:match("^[%w_-]+$"))
    or (kind=="loan_action" and (value=="borrow" or value=="repay"))
    or (kind=="stop_side" and (value=="left" or value=="right"))
    or (kind=="stop_param" and type(value)=="number" and value>=.15 and value<=.85)
    or (kind=="number" and type(value)=="number" and value==value and math.abs(value)<math.huge)
    or (kind=="depot_carrier" and type(value)=="string" and ({ROAD=true,TRAM=true,RAIL=true,WATER=true})[value])
    or (kind=="water_facility_kind" and type(value)=="string" and ({harbor=true,shipyard=true,maintenance=true})[value])
    or (kind=="harbor_size" and type(value)=="string" and ({small=true,large=true})[value])
    or (kind=="specialization" and type(value)=="string" and ({universal=true,liquid=true,bulk=true,flatbed=true,goods=true})[value])
    or (kind=="station_size" and type(value)=="number" and value%1==0 and value>=1 and value<=3)
    or (kind=="tracks" and type(value)=="number" and value%1==0 and value>=1 and value<=4)
    or (kind=="rail_length" and type(value)=="number" and ({[80]=true,[120]=true,[160]=true,[240]=true,[320]=true})[value])
    or (kind=="ratio" and type(value)=="number" and value>=0 and value<=1)
    or (kind=="offset" and type(value)=="number" and value%1==0 and value>=0 and value<=1000000)
    or (kind=="wait" and type(value)=="number" and value%1==0 and value>=0 and value<=600)
    or (kind=="signed_integer" and type(value)=="number" and value%1==0 and value>=-100000 and value<=100000)
    or (kind=="page_limit" and type(value)=="number" and value%1==0 and value>=1 and value<=100)
    or ((kind=="spacing" or kind=="radius") and type(value)=="number" and value>=1 and value<=1000)
    or (kind=="one" and value==1)
    or (kind=="stop_index" and type(value)=="number" and value%1==0 and value>=0 and value<=7)
    or (kind=="bool" and type(value)=="boolean")
    or groups or (kind=="line_name" and type(value)=="string" and #value>=1 and #value<=80)
    or (kind=="entity" and type(value)=="number" and value%1==0 and value>=0 and value<2147483647)
    or (kind=="modules" and (value==1 or value==4))
    or (kind=="text" and type(value)=="string" and #value>=1 and #value<=160)
    or (kind=="request_id" and type(value)=="string" and #value==32 and value:match("^[0-9a-f]+$"))
    or (kind=="road_graph" and type(value)=="table")
    or (kind=="endpoint" and endpoint(value))
    or (kind=="token" and type(value)=="string" and #value>=1 and #value<=128)
   assert(valid,"Invalid construction argument: "..tostring(key))
  end
  local required=cmd=="create_line" and {"station_groups","name"} or (cmd=="build_warehouse" or cmd=="build_helipad" or cmd=="build_heliport" or cmd=="build_airfield") and {"x","y","z"} or cmd=="build_water_facility" and {"x","y","z","kind"} or cmd=="build_facility" and {"source_entity","x","y","z"}
   or cmd=="buy_vehicles" and {"depot","model","count"} or cmd=="assign_vehicles" and {"vehicles","line","stop_index"}
   or cmd=="set_vehicle_stopped" and {"vehicle","stopped"} or (cmd=="send_to_depot" or cmd=="get_vehicle_motion") and {"vehicle"}
   or (cmd=="commit_facility" or cmd=="commit_road") and {"preview_token"}
   or (cmd=="reconcile_road_rejection" or cmd=="reconcile_network_rejection" or cmd=="reconcile_depot_rejection" or cmd=="reconcile_town_cargo_rejection" or cmd=="reconcile_subvention_rejection" or cmd=="reconcile_facility_rejection") and {"request_id"}
   or cmd=="preview_road" and {"start","end","street_type"} or cmd=="get_entity" and {"id"}
   or cmd=="survey_build_site" and {"x","y"} or (cmd=="list_facilities" or cmd=="list_street_types") and {} or {"entity"}
  local extraRequired={get_town_cargo_supply={"town"},reconcile_assignment_rejection={"request_id","vehicle","line"},get_industry_bonuses={"industry"},preview_depot_removal={"entity"},commit_depot_removal={"preview_token","backup_save"},get_depot_removal_operation={"operation_id"},get_town_population={"town"},get_town_building_stats={"ids"},get_component_collection={"id","component","field","offset","limit"},begin_snapshot={"snapshot_kind"},read_snapshot_page={"snapshot","offset"},release_snapshot={"snapshot"},preview_line_edit={"line","stops"},set_game_speed={"speed","expected_speed"},preview_headquarters_access={"town","road","x","y","z"},preview_line_terminal={"line","stop_index","station_index","terminal"},preview_subvention={"uid"},commit_subvention={"preview_token"},get_subvention_operation={"operation_id"},get_facility_layout={"entity"},preview_test_removal={"entity"},commit_test_removal={"preview_token"},get_validation_state={},reset_operation_quota={"expected_round","expected_used","expected_count"},preview_flatten_terrain={"bounds","target_height"},commit_flatten_terrain={"preview_token","backup_save"},get_terrain_operation={"operation_id"},get_stock_activity={"stock_list","cargo"},get_town_deliveries={"town"},
   check_network_junction_path={"node","from_edge","to_edge","mode"},
   preview_road_upgrade={"edge","street_type"},preview_street_stop={"edge","param","side","two_sided"},commit_edge_edit={"preview_token"},
   preview_facility_module={"entity","slot","resource"},preview_facility_parameter={"entity","key","value"},build_headquarters={"town","x","y","z"},
   preview_industry={"resource","x","y"},commit_industry={"preview_token"},get_industry_operation={"operation_id"},
   preview_town_cargo_needs={"town"},commit_town_cargo_needs={"preview_token"},get_town_cargo_operation={"operation_id"},
   preview_prospection={"town","resource"},commit_prospection={"preview_token"},get_prospection_operation={"operation_id"},
   preview_loan={"action"},commit_loan={"preview_token"},get_loan_operation={"operation_id"},
get_network_template={"template"},list_road_structures={},preview_road_graph={"graph"},commit_road_graph={"preview_token","backup_save"},get_road_graph_operation={"operation_id"},list_network_templates={},preview_network={"start","end","template"},commit_network={"preview_token"},list_multiple_units={},preview_multiple_unit={"depot","resource"},get_vehicle_cargo={"vehicle","cargo"},get_sim_entity={"id"},get_stop_cargo={"line","stop_index","cargo"},get_stock_cargo={"stock_list","cargo"},preview_consist={"depot","models"},commit_consist={"preview_token"},check_road_junction_path={"node","from_edge","to_edge","mode"},delete_line={"line"},sell_vehicles={"vehicles"},list_cargo_types={},
   preview_depot={"x","y","rotation","carrier"},preview_station={"x","y","rotation","cargo","size"},
   preview_rail_station={"x","y","rotation","tracks","length","specialization"},commit_structure={"preview_token"},
   preview_line_stop={"line","stop_index","loads","max_load","force_unload","extra_wait"},commit_line_stop={"preview_token"},
   get_terrain={"x","y"},find_nearby={"x","y","radius","limit"},list_facility_resources={},
   list_industry_resources={},list_prospections={},get_prospections={},get_notifications={},get_loans={},get_subventions={},
   get_town_cargo_needs={"town"},get_terrain_operation_capabilities={},list_map_entities={},release_map_snapshot={"snapshot"},
   get_terrain_grid={},get_map_data={},get_terrain_tile={"tile_x","tile_y"}}
  required=extraRequired[cmd] or required
  for _,key in ipairs(required) do assert(args[key]~=nil,"Missing construction argument: "..key) end
 end
 local function emit(req,ok,value)
  local r={id=req.id,cmd=req.cmd,ok=ok}
  if ok then r.result=value else r.error=tostring(value) end
  if not ok and type(value)=="table" and value.rejectedBeforeDispatch==true then
   r.error=value.message;r.rejectedBeforeDispatch=true;r.code=value.code
  end
  local good,text=pcall(json.encode,r)
  if not good or #text>65536 then
   text=json.encode({id=req.id,cmd=req.cmd,ok=false,error="Construction result unavailable; reconcile, never retry",
    resultFailureReason=good and "encoded_size_limit" or "encoding_failed",
    encodedBytes=good and #text or nil,maxEncodedBytes=65536})
  end
  local payload=hexEncode(text);local total=math.max(1,math.ceil(#payload/1500))
  for part=1,total do print("[TNJ_UI_READ_V1] id="..req.id.." part="..part.." total="..total.." hex="..payload:sub((part-1)*1500+1,part*1500)) end
 end
 uiBuild.recognizes=function(text)
  local cmd=type(text)=="string" and text:match("^[0-9a-f]+ ([a-z_]+)")
  return cmd and schemas[cmd]~=nil
 end
 uiBuild.forward=function(text,continualRead)
  if type(text)~="string" or #text>uiBuild.inputLimit(text) then return "Invalid construction request" end
  local id,cmd,raw=text:match("^([0-9a-f]+) ([a-z_]+) (.+)$")
  if not id then id,cmd=text:match("^([0-9a-f]+) ([a-z_]+)$");raw="{}" end
  if not id or #id~=32 or not raw:match("^%s*{") then return "Invalid construction request" end
  local ok,args=pcall(json.decode,raw)
  if not ok then return "Invalid construction JSON" end
  local valid,err=pcall(validate,cmd,args)
  if not valid then return tostring(err) end
  if sent[id] then return "Duplicate request; inspect existing log" end
  local rollingRead=continualRead==true and pureEngineReads[cmd]==true
  -- The engine owns the durable round quota. GUI admission must not stop
  -- heartbeats or prevent the free reset/read commands at the boundary.
  if rollingRead then
   if #sentReadOrder>=256 then sent[table.remove(sentReadOrder,1)]=nil end
   sentReadOrder[#sentReadOrder+1]=id
  end
  sent[id]=true -- reserve before dispatch; mutation IDs are never evicted
  local req={id=id,cmd=cmd,args=args,facilityEpoch=terrainEpoch}
  if cmd:find("terrain",1,true) then req.terrainEpoch=terrainEpoch end
  local good,why=pcall(function()
   api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("tf3_mcp_bridge","tnj_bridge_build","tnj_bridge_build.request",json.encode(req)))
  end)
  return good and "Submitted; inspect log" or "Dispatch unknown; do not retry"
 end
 local stopFields={"stationGroup","station","terminal","loadMode","minWaitingTime","maxWaitingTime","maxAdditionalWaitingTime"}
 local configFields={"forceUnload","destroyForConfigChange","destroyForRefresh"}
 local function orderedVector(v)
  local out,count={},0
  for k,x in pairs(v) do
   assert(type(k)=="number" and k%1==0 and k>=1,"Unsupported vector indices")
   out[k]=x;count=count+1
  end
  assert(#out==count,"Sparse vector not supported")
  return out
 end
 local function lineSnapshot(id)
  requireEntity({line=id},"line","LINE")
  assert(ownerOf(id)==api.engine.util.getPlayer(),"Line is not owned by current player")
  local old=getComponent(id,"LINE")
  local snap={customFilters=old.customFilters,reservationPriority=old.reservationPriority,stops={}}
  local signature={tostring(old.customFilters),tostring(old.reservationPriority)}
  for _,s in ipairs(orderedVector(old.stops)) do
   assert(#orderedVector(s.waypoints)==0 and #orderedVector(s.alternativeTerminals)==0,"Complex line stops require a separate adapter")
   local t={config={}};local c=s.stopConfig
   assert(c,"Missing stop config")
   for _,k in ipairs(stopFields) do t[k]=s[k];signature[#signature+1]=k..":"..tostring(s[k]) end
   for _,k in ipairs(configFields) do t.config[k]=c[k];signature[#signature+1]=k..":"..tostring(c[k]) end
   t.config.load=orderedVector(c.load);t.config.maxLoad=orderedVector(c.maxLoad)
   signature[#signature+1]=json.encode(t.config.load);signature[#signature+1]=json.encode(t.config.maxLoad)
   snap.stops[#snap.stops+1]=t
  end
  assert(#snap.stops>=2 and #snap.stops<=8,"Line adapter supports 2 to 8 simple stops")
  return snap,table.concat(signature,"|")
 end
 local function lineWithConfig(snap,args)
  local c=api.type.Line.new();c.customFilters=true
  if snap.reservationPriority~=nil then c.reservationPriority=snap.reservationPriority end
  local stops={};local allowed={}
  for id in pairs(api.res.cargoTypeRep.getAll(true)) do allowed[id]=true end
  for _,id in ipairs(args.loads or {}) do assert(allowed[id],"Unknown cargo ID") end
  for i,t in ipairs(snap.stops) do
   local s=api.type.Line.Stop.new();local cfg=api.type.Line.StopConfig.new()
   for _,k in ipairs(stopFields) do if t[k]~=nil then s[k]=t[k] end end
   for _,k in ipairs(configFields) do if t.config[k]~=nil then cfg[k]=t.config[k] end end
   local loads,maximum={},{}
   for j,v in ipairs(t.config.load) do loads[j]=v end
   for j,v in ipairs(t.config.maxLoad) do maximum[j]=v end
   if i==args.stop_index+1 and args.loads~=nil then
    loads={};maximum={}
    for id in pairs(allowed) do loads[id+1]=false;maximum[id+1]=args.max_load end
    for _,id in ipairs(args.loads) do loads[id+1]=true end
    cfg.forceUnload=args.force_unload;s.maxAdditionalWaitingTime=args.extra_wait
   end
   if i==args.stop_index+1 and args.terminal~=nil then s.station=args.station_index;s.terminal=args.terminal end
   cfg.load=loads;cfg.maxLoad=maximum;s.stopConfig=cfg;stops[i]=s
  end
  c.stops=stops;return c
 end
 local function terminalSelection(snap,args)
  if args.terminal==nil then return nil end
  local stop=assert(snap.stops[args.stop_index+1],"Stop no longer exists")
  local group=assert(getComponent(stop.stationGroup,"STATION_GROUP"),"Station group missing")
  local station=listOf(group.stations)[args.station_index+1]
  assert(station,"Station index outside current group")
  local st=assert(getComponent(station,"STATION"),"Station component missing")
  local terminal=listOf(st.terminals)[args.terminal+1]
  assert(terminal and terminal.vehicleNodeId,"Terminal index outside current station")
  local node=terminal.vehicleNodeId
  assert(api.engine.entityExists(node.entity),"Terminal network entity missing")
  return stableDataSignature({group=stop.stationGroup,station=station,terminal=args.terminal,
   vehicleNode=toPlain(node,0,nil,"NodeId"),personNodes=toPlain(terminal.personNodes,0,nil,{element="NodeId"}),cargoLoad=terminal.cargoLoad,cargoUnload=terminal.cargoUnload,
   passengersLoad=terminal.passengersLoad,passengersUnload=terminal.passengersUnload})
 end
 function uiBuild.lineSignature(line)
  local out={customFilters=line.customFilters,reservationPriority=line.reservationPriority,stops={}}
  local stops=orderedVector(line.stops);assert(#stops>=2 and #stops<=32,"Line edit supports 2 to 32 stops")
  for _,stop in ipairs(stops) do
   assert(#orderedVector(stop.waypoints)<=64 and #orderedVector(stop.alternativeTerminals)<=64,"Complex stop exceeds bound")
   out.stops[#out.stops+1]=toPlain(stop,0,nil,"Engine.Component.Line.Stop")
  end
  return stableDataSignature(out)
 end
 function uiBuild.editLine(args)
  requireEntity(args,"line","LINE");assert(ownerOf(args.line)==api.engine.util.getPlayer(),"Line is not owned")
  local old=getComponent(args.line,"LINE");local signature=uiBuild.lineSignature(old)
  local previous=orderedVector(old.stops);local c=api.type.Line.new();c.customFilters=true;c.reservationPriority=old.reservationPriority
  local stops,terminals={},{}
  local cargos=api.res.cargoTypeRep.getAll(true)
  for _,edit in ipairs(args.stops) do
   local s=api.type.Line.Stop.new();local cfg=api.type.Line.StopConfig.new()
   if edit.source_index~=nil then
    local source=assert(previous[edit.source_index+1],"Source stop index out of range")
    for _,k in ipairs(stopFields) do if source[k]~=nil then s[k]=source[k] end end
    for _,k in ipairs(configFields) do if source.stopConfig[k]~=nil then cfg[k]=source.stopConfig[k] end end
    cfg.load=orderedVector(source.stopConfig.load);cfg.maxLoad=orderedVector(source.stopConfig.maxLoad)
    s.waypoints=orderedVector(source.waypoints);s.alternativeTerminals=orderedVector(source.alternativeTerminals)
   else
    s.stationGroup=edit.station_group;s.station=edit.station;s.terminal=edit.terminal
    s.waypoints={};s.alternativeTerminals={};s.maxAdditionalWaitingTime=0
    cfg.load={};cfg.maxLoad={};cfg.forceUnload=false;cfg.destroyForConfigChange=false;cfg.destroyForRefresh=false
   end
   if edit.station~=nil then s.station=edit.station end
   if edit.terminal~=nil then s.terminal=edit.terminal end
   if edit.extra_wait~=nil then s.maxAdditionalWaitingTime=edit.extra_wait end
   if edit.force_unload~=nil then cfg.forceUnload=edit.force_unload end
   if edit.loads~=nil then
    local loads={};for id in pairs(cargos) do loads[id+1]=false end
    for _,id in ipairs(edit.loads) do assert(cargos[id]~=nil,"Unknown cargo ID");loads[id+1]=true end
    cfg.load=loads
   end
   if edit.max_load~=nil or edit.source_index==nil then
    local maximum={};for id in pairs(cargos) do maximum[id+1]=edit.max_load or 1 end;cfg.maxLoad=maximum
   end
   s.stopConfig=cfg;stops[#stops+1]=s
   local snap={stops={{stationGroup=s.stationGroup}}}
   terminals[#terminals+1]=terminalSelection(snap,{stop_index=0,station_index=s.station,terminal=s.terminal})
   for _,alt in ipairs(orderedVector(s.alternativeTerminals)) do
    terminals[#terminals+1]=terminalSelection(snap,{stop_index=0,station_index=alt.station,terminal=alt.terminal})
   end
  end
  c.stops=stops
  return c,signature,stableDataSignature(terminals)
 end
 local function makeConsist(args)
  local depot=requireEntity(args,"depot","VEHICLE_DEPOT")
  local player=api.engine.util.getPlayer()
  assert(ownerOf(depot)==player,"Depot is not owned by current player")
  -- Current native VEHICLE_DEPOT exposes transportModes, not carrier.
  local railMode=false
  for mode,enabled in pairs(getComponent(depot,"VEHICLE_DEPOT").transportModes) do
   local name=enumName("TransportMode",mode)
   if enabled and (name=="TRAIN" or name=="ELECTRIC_TRAIN") then railMode=true end
  end
  assert(railMode,"Consist requires a rail depot")
  local config=api.type.TransportVehicleConfig.new()
  local parts,groups,details,signature={},{},{},{tostring(player),tostring(depot)}
  local quote=0;local known={}
  api.res.modelRep.forEachModelWithMetadata("transportVehicle",function(name)
   local id=api.res.modelRep.find(name);if id and id>=0 then known[id]=true end
  end)
  local models=args.models;local muName;local orientations={}
  if args.resource then
   local muId
   for id,name in pairs(api.res.multipleUnitRep.getAll()) do if name==args.resource then muId=id end end
   assert(muId,"Unknown current multiple-unit resource")
   local mu=api.res.multipleUnitRep.get(muId);muName=api.res.multipleUnitRep.getName(muId)
   assert(muName==args.resource,"Multiple-unit resource identity mismatch")
   models={}
   for _,v in ipairs(orderedVector(mu.vehicles)) do
    assert(type(v.name)=="string" and type(v.forward)=="boolean","Invalid native MU part")
    local id=api.res.modelRep.find(v.name)
    assert(type(id)=="number" and known[id],"Unknown MU part model")
    assert(api.res.modelRep.getName(id)==v.name,"MU model resource mismatch")
    models[#models+1]=id;orientations[#orientations+1]=v.forward
   end
   assert(#models>=1 and #models<=16,"MU supports 1 to 16 native parts")
   signature[#signature+1]=muName
  end
  for index,id in ipairs(models) do
   assert(known[id],"Unknown current model ID")
   local modelId=resolveModel(id);local info=modelInfo(modelId)
   assert(muName or readField(api.res.modelRep.get(modelId).metadata.transportVehicle,"multipleUnitOnly")~=true,"Fixed multiple units require a separate adapter")
   assert(info and info.carrier=="RAIL","Consist contains a non-rail model")
   local one=makeVehicleConfig(modelId);local part=one.vehicles[1]
   part.maintenanceState=1
   if muName then part.part.reversed=not orientations[index] end
   local price=api.engine.util.vehicle.getPartPrice(part)
   assert(type(price)=="number" and price>=0 and price<1e15,"Part quote unavailable")
   parts[#parts+1]=part;groups[#groups+1]=1
   details[#details+1]={id=modelId,model=info.model,price=price,capacity=info.capacity,reversed=part.part.reversed}
   quote=quote+price;signature[#signature+1]=tostring(modelId)..":"..info.model..":"..tostring(price)..":"..tostring(part.part.reversed)
  end
  config.vehicles=parts;config.vehicleGroups=muName and {#parts} or groups;config.muFileNames=muName and {muName} or {}
  return config,{depot=depot,multipleUnit=muName,parts=details,partCount=#parts,quotedPartsCost=quote,
   quoteScope="sum of fresh native part quotes; final purchase is decided by the engine",nativeCompatibilityVerified=false},table.concat(signature,"|")
 end
 commands.list_multiple_units=function(args)
  local ids={};for id in pairs(api.res.multipleUnitRep.getAll()) do ids[#ids+1]=id end;table.sort(ids)
  local offset,limit=args.offset or 0,args.limit or 30;local out={}
  for i=offset+1,math.min(#ids,offset+limit) do
   local id=ids[i];local mu=api.res.multipleUnitRep.get(id);local parts={}
   for _,v in ipairs(orderedVector(mu.vehicles)) do parts[#parts+1]={model=v.name,forward=v.forward} end
   out[#out+1]={id=id,resource=api.res.multipleUnitRep.getName(id),name=mu.name,parts=parts}
  end
  return {items=out,total=#ids,offset=offset,hasMore=offset+#out<#ids}
 end
 -- These small readbacks use current native resource IDs, never Lua array positions.
 local function cargoReadId(args)
  local id=args.cargo
  assert(type(id)=="number" and id%1==0 and id>=0 and api.res.cargoTypeRep.getAll(true)[id]~=nil,"Unknown current cargo ID")
  return id
 end
 local function cargoQuality(q)
  local total,bad=q.countTotal,q.countBad
  assert(type(total)=="number" and total>=0 and total%1==0,"Invalid cargo count")
  assert(type(bad)=="number" and bad>=0 and bad%1==0,"Invalid bad cargo count")
  local average=q.averageQuality
  if average~=nil then assert(type(average)=="number" and average==average and math.abs(average)<math.huge,"Invalid cargo quality") end
  return {countTotal=total,countBad=bad,hasCargo=total>0,hasBadCargo=total>0 and bad>0,
   averageQuality=total>0 and average or nil,nativeIsVeryBad=q.isVeryBad}
 end
 local function cargoReadTime()
  return getComponent(api.engine.util.getWorld(),"GAME_TIME").gameTime
 end
 commands.get_vehicle_cargo=function(args)
  assert((args.offset==nil and args.limit==nil) or args.include_entities==true,"Entity pagination requires include_entities=true")
  local id=requireEntity(args,"vehicle","TRANSPORT_VEHICLE");local cargo=cargoReadId(args)
  local q=cargoQuality(api.engine.util.cargo.getCargoQualityDataForVehicle(id,cargo))
  local count=api.engine.system.simEntityAtVehicleSystem.getVehicleSimEntitiesCountForCargoType(id,cargo)
  local result={vehicle=id,cargo=cargo,gameTime=cargoReadTime(),count=count,quality=q,countAgreement=count==q.countTotal,
   scope="current onboard amount; a decrease alone does not prove delivery"}
  if args.include_entities then
   local offset=pageInteger(args.offset,0,0,1000000,"offset")
   local limit=pageInteger(args.limit,20,1,100,"limit")
   local ids,seen={},{}
   local function add(entity)
    assert(type(entity)=="number" and entity>=0 and entity%1==0,"Invalid onboard entity ID")
    assert(not seen[entity],"Duplicate onboard entity ID")
    seen[entity]=true;ids[#ids+1]=entity
    assert(#ids<=10000,"Onboard entity list exceeds read bound")
   end
   local source,scanned,visited="sim_cargo_vehicle_components",0,0
   if cargo==0 then
    -- The native aggregate map was empty for a live bus with ten passengers.
    -- Resolve actual membership from the two independently exposed components,
    -- not guessed cargo-map indexes, pickup times, or passenger seat positions.
    local ct=componentTypes()
    assert(ct.SIM_PERSON and ct.SIM_ENTITY_AT_VEHICLE and ct.SIM_PERSON_AT_VEHICLE,"Passenger component types unavailable")
    source="sim_person_vehicle_components"
    api.engine.forEachEntityWithComponent(function(entity)
     scanned=scanned+1;assert(scanned<=100000,"Passenger identity scan exceeds 100000 entities")
     local at=api.engine.getComponent(entity,ct.SIM_ENTITY_AT_VEHICLE)
     local seat=api.engine.getComponent(entity,ct.SIM_PERSON_AT_VEHICLE)
     if (at and at.vehicle==id) or (seat and seat.vehicle==id) then
      assert(at and seat and at.vehicle==seat.vehicle,"Passenger vehicle components disagree")
      add(entity)
     end
    end,ct.SIM_PERSON)
   else
    -- The aggregate map also omitted fifteen fish on a live ship. Match the
    -- actual cargo type and current vehicle component; pickup history alone
    -- cannot establish that a cargo item is still aboard.
    local ct=componentTypes()
    assert(ct.SIM_CARGO and ct.SIM_ENTITY_AT_VEHICLE,"Cargo component types unavailable")
    -- SIM_CARGO cannot be enumerated with forEachEntityWithComponent. Use
    -- the same complete entity index as list_map_entities, with a hard bound.
    api.engine.forEachEntity(function(entity)
     visited=visited+1;assert(visited<=1000000,"Cargo identity entity scan exceeds 1000000 entities")
     local item=api.engine.getComponent(entity,ct.SIM_CARGO)
     if item then
      scanned=scanned+1;assert(scanned<=100000,"Cargo identity scan exceeds 100000 entities")
      assert(type(item.cargoType)=="number" and item.cargoType>0 and item.cargoType%1==0,"Invalid scanned cargo type")
      if item.cargoType==cargo then
       local at=api.engine.getComponent(entity,ct.SIM_ENTITY_AT_VEHICLE)
       if at and at.vehicle==id then add(entity) end
      end
     end
    end)
   end
   table.sort(ids)
   local items={}
   for i=offset+1,math.min(#ids,offset+limit) do items[#items+1]=ids[i] end
   result.entities={ids=items,total=#ids,offset=offset,limit=limit,hasMore=offset+#items<#ids,
    countAgreement=#ids==count,source=source,scannedPersons=cargo==0 and scanned or 0,
    scannedCargo=cargo~=0 and scanned or 0,visitedEntities=visited,
    consistency="current live IDs only; recheck session and components before inferring alighting"}
  end
  return result
 end
 commands.get_sim_entity=function(args)
  local id=args.id
  assert(type(id)=="number" and id>=0 and id%1==0,"Invalid sim entity ID")
  local result={id=id,exists=api.engine.entityExists(id),gameTime=cargoReadTime(),
   scope="current native components; absence or deletion alone is not proof of completed travel"}
  if not result.exists then return result end
  local specs={
   {"SIM_PERSON","SimPerson",COMPONENT_FIELDS.SIM_PERSON},
   {"SIM_CARGO","SimCargo",{"cargoType","targetOrPickupEntity","sourceEntity","startTime","pickupTime","deliveryExtensionDuration"}},
   {"SIM_ENTITY_AT_VEHICLE","SimEntityAtVehicle",{"line","lineStop0","lineStop1","vehicle","roundTripCounter"}},
   {"SIM_PERSON_AT_VEHICLE","SimPersonAtVehicle",{"vehicle","part","place","expectedArrivalTime"}},
   {"SIM_ENTITY_AT_TERMINAL","SimEntityAtTerminal",{"line","lineStop0","lineStop1","arrivalTime","vehicle"}},
   {"SIM_ENTITY_MOVING","SimEntityMoving",{"line","lineStop0","lineStop1","partialPath","expectedArrivalTime"}},
   {"SIM_ENTITY_AT_BUILDING","SimEntityAtBuilding",{"waitingTime"}}
  }
  result.components=json.object()
  for _,spec in ipairs(specs) do
   local ct=componentTypes()[spec[1]]
   assert(ct~=nil,"Native component type unavailable: "..spec[1])
   local value=api.engine.getComponent(id,ct)
   if value~=nil then result.components[spec[1]]=toPlain(value,0,spec[3],"Engine.Component."..spec[2]) end
  end
  assert(result.components.SIM_PERSON~=nil or result.components.SIM_CARGO~=nil,"Entity is neither SIM_PERSON nor SIM_CARGO")
  return result
 end
 commands.get_stock_activity=function(args)
  local id=requireEntity(args,"stock_list","STOCK_LIST");local cargo=cargoReadId(args)
  return {stockList=id,cargo=cargo,gameTime=cargoReadTime(),
   annualConsumed=api.engine.util.stock.getCargoConsumedPerYear(id,cargo),
   annualMaxConsumption=api.engine.util.stock.getCargoMaxConsumptionPerYear(id,cargo),
   scope="native annual consumption and maximum; not instantaneous rate or interval delivery"}
 end
 commands.get_town_population=function(args)
  local town=requireEntity(args,"town","TOWN")
  local u=api.engine.util.town.getTownCapacityUsage(town)
  local r=assert(u[api.type.enum.LandUseType.RESIDENTIAL+1],"Residential capacity usage unavailable")
  assert(type(r.used)=="number" and type(r.capacity)=="number","Invalid native population")
  return {town=town,population=r.used,residentialCapacity=r.capacity,gameTime=cargoReadTime()}
 end
 ENGINE_COMMANDS.get_town_population=true
 commands.get_town_cargo_supply=function(args)
  local town=requireEntity(args,"town","TOWN")
  local system=assert(api.engine.system.townBuildingSystem,"Town building system unavailable")
  assert(system.getCargoSupplyAndLimit~=nil,"Native city supply API unavailable") -- native bindings may be callable tables
  local districts={};local totals={}
  local function finite(n)return type(n)=="number" and n==n and n~=math.huge and n~=-math.huge and n>=0 end
  for _,name in ipairs({"residential","commercial","industrial"}) do
   local landUse=assert(api.type.enum.LandUseType[string.upper(name)],"Land use enum unavailable")
   local values=assert(system.getCargoSupplyAndLimit(town,landUse),"Native supply data unavailable")
   local rows={}
   for cargo,v in pairs(values) do
    assert(finite(cargo) and cargo%1==0 and finite(v[1]) and finite(v[2]),"Invalid native supply or demand")
    local demand=math.floor(v[2]);local supply=math.min(math.ceil(v[1]),demand)
    rows[#rows+1]={cargo=cargo,rawSupply=v[1],rawDemand=v[2],supply=supply,demand=demand,
     rateKnown=demand>0,supplyRate=demand>0 and supply/demand or nil}
    local t=totals[cargo] or {cargo=cargo,supply=0,demand=0};totals[cargo]=t
    t.supply=t.supply+supply;t.demand=t.demand+demand
   end
   table.sort(rows,function(a,b)if a.demand~=b.demand then return a.demand>b.demand end;return a.cargo<b.cargo end)
   districts[name]=rows
  end
  local items={}
  for _,t in pairs(totals) do t.rateKnown=t.demand>0;t.supplyRate=t.demand>0 and t.supply/t.demand or nil;items[#items+1]=t end
  table.sort(items,function(a,b)return a.cargo<b.cargo end)
  local passengers=nil
  if args.include_passengers then
   assert(system.getLandUsePersonCapacities~=nil,"Native residential capacity API unavailable")
   local capacities=assert(system.getLandUsePersonCapacities(town),"Native residential capacities unavailable")
   local demand=capacities[api.type.enum.LandUseType.RESIDENTIAL+1]
   assert(finite(demand),"Invalid native passenger demand")
   passengers={demand=demand,panelRowPresent=demand>0,rateKnown=false,
    source="town_util.getCargoSupplyDemandsLandUseWithResidentialLineUsage",
    scope="Residential passenger panel; line-usage-derived supply, all public transport, not bus-only or a transported-person counter",
    periodKnown=false,lineUsageRatingMultiplier=2}
   if demand>0 then
    local townApi=assert(api.engine.util.town,"Native town utility unavailable")
    assert(townApi.getTownLineUsage~=nil,"Native town line usage API unavailable")
    local usage=townApi.getTownLineUsage(town)
    assert(finite(usage),"Invalid native town line usage")
    local rating=math.max(0,math.min(usage*2,1))
    local supply=math.floor(demand*rating+0.5)
    passengers.rawLineUsage=usage;passengers.supply=supply
    passengers.rateKnown=true;passengers.supplyRate=supply/demand
   end
  end
  return {town=town,gameTime=cargoReadTime(),passengers=passengers,townPassengerSupplyVersion=1,districts=districts,items=items,readOnly=true,townCargoSupplyVersion=2,
   source="api.engine.system.townBuildingSystem.getCargoSupplyAndLimit",
   scope="Native city-panel cargo supply/demand; district rounding matches town_util.getCargoSupplyDemandsLandUse; totals sum district display values",
   periodKnown=false,period="Native panel metric; temporal window not exposed by this API; not annual or half-year delivery counters"}
 end
 ENGINE_COMMANDS.get_town_cargo_supply=true
 commands.get_town_building_stats=function(args)
  local out={};local cargos=api.res.cargoTypeRep.getAll(true)
  for _,id in ipairs(args.ids) do
   local b=assert(getComponent(id,"TOWN_BUILDING"),"Town building removed or changed")
   local stock=b.stockList;local row={id=id,town=b.town,stock_list=stock,cargos={}}
   if type(stock)=="number" and stock>=0 and api.engine.entityExists(stock) and getComponent(stock,"STOCK_LIST") then
    row.available=true
    for cargo in pairs(cargos) do
     local demand=api.engine.util.stock.getCargoMaxConsumptionPerYear(stock,cargo)
     if demand>0 then row.cargos[#row.cargos+1]={cargo=cargo,demand=demand,
      consumed=api.engine.util.stock.getCargoConsumedPerYear(stock,cargo),delivered=api.engine.util.stock.getCargoTypeDeliveredPerYear(stock,cargo)} end
    end
   else row.available=false;row.reason="no_valid_stock_list" end
   out[#out+1]=row
  end
  return {items=out,gameTime=cargoReadTime(),scope="engine annual counters, not per-round flow; invalid stocks not queried"}
 end
 ENGINE_COMMANDS.get_town_building_stats=true
 commands.get_town_deliveries=function(args)
  local town=requireEntity(args,"town","TOWN")
  local interval=math.floor(api.util.getDefaultYearDuration()/2+.5)
  local data=api.engine.util.town.getTownDeliveriesStats(town,interval,true,true)
  local rows={}
  for line,byCargo in pairs(data) do for cargo,counts in pairs(byCargo) do
   assert(type(counts[1])=="number" and type(counts[2])=="number","Unknown native delivery tuple")
   rows[#rows+1]={line=line,cargo=cargo,late=counts[1],total=counts[2]}
  end end
  assert(#rows<=500,"Town delivery result exceeds bound")
  table.sort(rows,function(a,b)return a.line==b.line and a.cargo<b.cargo or a.line<b.line end)
  return {town=town,gameTime=cargoReadTime(),interval=interval,items=rows,
   scope="native rolling half-year delivery statistics, matching town UI; not 60-second throughput"}
 end
 commands.get_stop_cargo=function(args)
  local id=requireEntity(args,"line","LINE");local cargo=cargoReadId(args)
  local stops=listOf(getComponent(id,"LINE").stops)
  assert(type(args.stop_index)=="number" and args.stop_index%1==0 and args.stop_index>=0 and args.stop_index<#stops,"Invalid current line stop")
  local q=cargoQuality(api.engine.util.cargo.getCargoQualityDataAtStop(id,args.stop_index,cargo))
  return {line=id,stopIndex=args.stop_index,cargo=cargo,gameTime=cargoReadTime(),quality=q,scope="current waiting amount"}
 end
 commands.get_stock_cargo=function(args)
  local id=requireEntity(args,"stock_list","STOCK_LIST");local cargo=cargoReadId(args)
  local stocks=listOf(getComponent(id,"STOCK_LIST").stocks)
  assert(#stocks<=64,"Stock list exceeds bounded read; no inventory calls made")
  assert(args.stock_quality==nil or type(args.stock_quality)=="boolean","stock_quality must be boolean")
  local items,total={},0
  for i,stock in ipairs(stocks) do
   local count=api.engine.system.simEntityAtStockSystem.getStockCountForCargoType(id,i-1,cargo)
   local item={stockIndex=i-1,count=count,capacity=stock.capacity}
   if args.stock_quality then
    item.quality=cargoQuality(api.engine.util.cargo.getCargoQualityDataForStock(id,i-1,cargo))
    item.countAgreement=count==item.quality.countTotal
   end
   if args.diagnostic then
    local d={stockType=enumName("StockListType",stock.type),
     allCargoCount=api.engine.system.simEntityAtStockSystem.getStockCount(id,i-1),
     allCargoQuality=cargoQuality(api.engine.util.cargo.getCargoQualityDataForStock(id,i-1)),
     scope="all-cargo slot summary and at most one oldest entity; not a full inventory or age distribution"}
    if d.allCargoCount>0 then
     local oldest=api.engine.system.simEntityAtStockSystem.getStockSimEntity(id,i-1)
     assert(type(oldest)=="number" and oldest%1==0,"Invalid oldest stock entity")
     d.oldestEntity=oldest;d.oldestEntityExists=oldest>=0 and api.engine.entityExists(oldest)
     if d.oldestEntityExists then
      local c=getComponent(oldest,"SIM_CARGO")
      d.simCargoObserved=c~=nil
      if c then
       d.cargo={}
       for _,key in ipairs({"cargoType","sourceEntity","targetOrPickupEntity","startTime","pickupTime","deliveryExtensionDuration"}) do
        local value=readField(c,key);assert(type(value)=="number","Missing sampled cargo field: "..key);d.cargo[key]=value
       end
       d.requestedCargoMatches=c.cargoType==cargo
      end
     end
    end
    item.diagnostic=d
   end
   total=total+count;items[#items+1]=item
  end
  local q=cargoQuality(api.engine.util.cargo.getCargoQualityDataForStockList(id,cargo))
  return {stockList=id,cargo=cargo,gameTime=cargoReadTime(),stocks=items,count=total,quality=q,countAgreement=total==q.countTotal,
   annualDelivered=api.engine.util.stock.getCargoTypeDeliveredPerYear(id,cargo),
   annualShipped=api.engine.util.stock.getCargoTypeShippedPerYear(id,cargo),
   scope="one real stock list; capacities may be shared; annual statistics are not interval throughput"}
 end
 commands.list_cargo_types=function()
  local out={}
  for id,name in pairs(api.res.cargoTypeRep.getAll(true)) do out[#out+1]={id=id,name=name} end
  table.sort(out,function(a,b)return a.id<b.id end)
  return {items=out,count=#out}
 end
 local workflows={
  preview_subvention={commit="commit_subvention",read="get_subvention_operation"},
  preview_flatten_terrain={commit="commit_flatten_terrain",read="get_terrain_operation"},
  preview_industry={commit="commit_industry",read="get_industry_operation"},
  preview_town_cargo_needs={commit="commit_town_cargo_needs",read="get_town_cargo_operation"},
  preview_prospection={commit="commit_prospection",read="get_prospection_operation"},
  preview_loan={commit="commit_loan",read="get_loan_operation"},
 }
 local workflowCommits={};for _,v in pairs(workflows) do workflowCommits[v.commit]=v.read end
 local function edgeSignature(id)
  local e=assert(getComponent(id,"BASE_EDGE"),"Edge removed")
  assert(not constructionOfEdge(id),"Construction-owned edge edit refused")
  local endpoints={}
  for _,node in ipairs({e.node0,e.node1}) do
   local adjacent=listOf(api.engine.system.streetSystem.getNodeSegments(node));table.sort(adjacent)
   endpoints[#endpoints+1]={node=node,adjacent=adjacent,frozen=isFrozenStreetNode(node),position=nodePosition(node)}
  end
  local snapshot={edge=toPlain(e,0,nil,"Network.BaseEdge"),owner=ownerOf(id),
   endpoints=endpoints,a=networkNodeConfigSnapshot(getComponent(e.node0,"BASE_NODE_CONFIG")),b=networkNodeConfigSnapshot(getComponent(e.node1,"BASE_NODE_CONFIG"))}
  -- Native crosswalk edge references can enumerate in a different order on
  -- consecutive reads (Yulin 32932). Compare membership with multiplicity,
  -- not enumeration order. Sort only the detached snapshot, never native data.
  -- Keep lane/phase ordering and every other state field under the same guard.
  for _,cfg in pairs({a=snapshot.a,b=snapshot.b})do
   if type(cfg.crosswalks)=="table" then table.sort(cfg.crosswalks)end
  end
  return stableDataSignature(snapshot)
 end
 local function quotaState(ledger)
  if not ledger.quota then ledger.quota={round=0,used=math.min(ledger.count,QUOTA_LIMIT)} end
  ledger.retiredRequests=ledger.retiredRequests or {}
  ledger.retiredCount=ledger.retiredCount or 0
  return ledger.quota
 end
 local function reclaimReadBudget(ledger)
  local removed={}
  for id,row in pairs(ledger.requests)do
   if pureEngineReads[row.cmd] and (row.status=="returned" or row.status=="error") then removed[#removed+1]=id end
  end
  assert(ledger.count>=#removed,"Construction ledger count mismatch; reconcile")
  for _,id in ipairs(removed)do ledger.requests[id]=nil end
  ledger.count=ledger.count-#removed
  ledger.reclaimedReadRequests=(ledger.reclaimedReadRequests or 0)+#removed
  ledger.accountingVersion=2
 end
 -- General demolition is intentionally not exposed. This workflow handles one
 -- owned, empty road depot, with paused simulation and independently read state.
 function uiBuild.depotRemovalNodeConfig(cfg,removedEdges)
  if cfg==nil then return false end
  local c=networkNodeConfigSnapshot(cfg)
  stableDataSignature(c) -- reject unreadable records before deriving an expectation
  assert(type(c.laneConnections)=="table" and type(c.crosswalks)=="table"
   and type(c.trafficLightConfig)=="table" and type(c.trafficLightConfig.states)=="table","Incomplete node configuration")
  local turns,walks={},{};local changed=false
  for _,v in ipairs(c.laneConnections) do
   if removedEdges and (removedEdges[tostring(v.segment0)] or removedEdges[tostring(v.segment1)]) then changed=true
   else turns[#turns+1]=v end
  end
  for _,v in ipairs(c.crosswalks) do
   if removedEdges and removedEdges[tostring(v)] then changed=true else walks[#walks+1]=v end
  end
  -- Signal phase indices refer to lane/crosswalk order; do not guess remapping.
  assert(not changed or #c.trafficLightConfig.states==0,"Depot boundary has signal phases; guarded phase remapping is not supported")
  if #c.trafficLightConfig.states==0 then
   table.sort(turns,function(x,y)return stableDataSignature(x)<stableDataSignature(y) end)
   table.sort(walks)
  end
  c.laneConnections=turns;c.crosswalks=walks
  return c
 end
 function uiBuild.depotRemovalSnapshot(entity)
  assert(commands.get_game_state({}).speedup==0,"Pause before depot removal")
  local target=entity
  if getComponent(entity,"VEHICLE_DEPOT") then
   target=api.engine.system.streetConnectorSystem.getConstructionEntityForDepot(entity)
  end
  local c=assert(getComponent(target,"CONSTRUCTION"),"Depot construction missing")
  assert(c.fileName=="::/depots/road/road_depot/road_depot.con","Only road depots are supported")
  local ds=listOf(c.depots);assert(#ds==1,"Expected exactly one depot subentity")
  local depot=ds[1];assert(getComponent(depot,"VEHICLE_DEPOT"),"Depot subentity missing")
  local player=api.engine.util.getPlayer()
  assert(ownerOf(depot)==player,"Depot is not owned by current player")
  local co=ownerOf(target);assert(co==nil or co<0 or co==player,"Construction belongs to another player")
  for _,field in ipairs({"stations","industries","townBuildings"}) do
   assert(#listOf(c[field])==0,"Depot has attached facilities; removal refused")
  end
  -- Native road depots list their own VEHICLE_DEPOT in subconstructions.
  -- Permit only that already-verified subentity, never an additional facility.
  for _,id in ipairs(listOf(c.subconstructions)) do
   assert(id==depot,"Depot has additional subconstructions; removal refused")
  end
  local inside=assert(api.engine.system.transportVehicleSystem.getDepotVehicles(depot),"Depot inventory unavailable")
  assert(#listOf(inside)==0,"Depot contains vehicles")
  local s={entity=target,depot=depot,player=player,config=toPlain(c,0,nil,"Engine.Component.Construction"),
   ownedEdges={},ownedNodes={},roads={},nodes={},nodeConfigs={},expectedNodeConfigs={},boundaryNodes={},vehicles={},dependentVehicles={}}
  local endpoints={}
  for _,n in ipairs(listOf(c.frozenNodes)) do s.ownedNodes[tostring(n)]=true;endpoints[tostring(n)]=n end
  for _,e in ipairs(listOf(c.frozenEdges)) do
   local b=assert(getComponent(e,"BASE_EDGE"),"Depot internal edge missing")
   assert(#listOf(b.objects)==0,"Depot internal edge has objects")
   s.ownedEdges[tostring(e)]=true;endpoints[tostring(b.node0)]=b.node0;endpoints[tostring(b.node1)]=b.node1
  end
  for _,n in pairs(endpoints) do
   for _,e in ipairs(listOf(assert(api.engine.system.streetSystem.getNodeSegments(n),"Adjacent road inventory unavailable"))) do
    if not s.ownedEdges[tostring(e)] then
     local b=assert(getComponent(e,"BASE_EDGE"),"Adjacent road missing")
     s.roads[tostring(e)]=stableDataSignature(toPlain(b,0,nil,"Network.BaseEdge"))
     for _,nn in ipairs({b.node0,b.node1}) do
      s.nodes[tostring(nn)]=stableDataSignature(toPlain(assert(getComponent(nn,"BASE_NODE")),0,nil,"Engine.Component.BaseNode"))
      assert(not s.ownedNodes[tostring(nn)],"External road uses a depot-owned node; removal refused")
     end
    end
   end
  end
  for _,n in pairs(endpoints) do
   if not s.ownedNodes[tostring(n)] then
    s.boundaryNodes[tostring(n)]=true
    s.nodes[tostring(n)]=stableDataSignature(toPlain(assert(getComponent(n,"BASE_NODE")),0,nil,"Engine.Component.BaseNode"))
   end
  end
  for id in pairs(s.nodes) do
   local cfg=getComponent(tonumber(id),"BASE_NODE_CONFIG")
   s.nodeConfigs[id]=uiBuild.depotRemovalNodeConfig(cfg)
   s.expectedNodeConfigs[id]=uiBuild.depotRemovalNodeConfig(cfg,s.ownedEdges)
  end
  local vehicleCount=0
  api.engine.forEachEntityWithComponent(function(id)
   vehicleCount=vehicleCount+1;assert(vehicleCount<=2048,"Vehicle inventory exceeds guarded removal limit")
   local v=assert(getComponent(id,"TRANSPORT_VEHICLE"))
   if v.depot==depot then
    local state=enumName("TransportVehicleState",v.state)
    assert(state=="EN_ROUTE" or state=="AT_TERMINAL","Vehicle in/returning to depot or unknown state")
    assert(v.line and v.line>=0 and getComponent(v.line,"LINE"),"Dependent vehicle has no valid line")
    s.dependentVehicles[#s.dependentVehicles+1]=id
   end
   s.vehicles[tostring(id)]=uiBuild.depotRemovalVehicle(v)
  end,componentTypes().TRANSPORT_VEHICLE)
  table.sort(s.dependentVehicles)
  s.signature=stableDataSignature(s)
  return s
 end
 function uiBuild.depotRemovalVehicle(v)
  local parts={}
  for _,p in ipairs(listOf(v.transportVehicleConfig.vehicles)) do
   parts[#parts+1]={part=toPlain(p.part,0,nil,"VehiclePart"),purchaseTime=p.purchaseTime}
  end
  return {signature=stableDataSignature({line=v.line,userStopped=v.userStopped,parts=parts}),noPath=v.noPath==true}
 end
 function uiBuild.depotRemovalProposal(s)
  -- createProposalRemove returns Proposal, NOT SimpleProposal. See the shipped
  -- api/tealdef/api/type.d.tl: Proposal.toRemove/toAdd/proposal fields.
  local p=assert(api.engine.util.proposal.createProposalRemove(s.entity,api.type.Context.new()),"Native removal proposal unavailable")
  local function values(v,label,entityRecords)
   assert(v~=nil,"Native removal field unavailable: "..label)
   local out={}
   for _,x in pairs(v) do
    assert(#out<2048,"Native removal scope exceeds limit: "..label)
    if entityRecords then x=x.entity end
    assert(type(x)=="number" and x>=0,"Invalid native entity in "..label)
    out[#out+1]=x
   end
   table.sort(out);return out
  end
  local function size(v,label)
   assert(v~=nil,"Native removal field unavailable: "..label)
   local n=0;for _ in pairs(v) do n=n+1;assert(n<=2048,"Native removal scope exceeds limit") end
   return n
  end
  local street=assert(p.proposal,"Native Proposal.proposal unavailable")
  local scope={toRemove=values(p.toRemove,"toRemove"),toAdd=size(p.toAdd,"toAdd"),
   old2new=size(p.old2new,"old2new"),
   removedSegments=values(street.removedSegments,"removedSegments",true),
   removedNodes=values(street.removedNodes,"removedNodes",true),
   addedSegments=size(street.addedSegments,"addedSegments"),addedNodes=size(street.addedNodes,"addedNodes"),
   edgeObjectsToAdd=size(street.edgeObjectsToAdd,"edgeObjectsToAdd"),
   new2oldEdgeObjects=size(street.new2oldEdgeObjects,"new2oldEdgeObjects"),
   old2newEdgeObjects=size(street.old2newEdgeObjects,"old2newEdgeObjects"),
   nodeConfigsToAdd=values(street.nodeConfigsToAdd,"nodeConfigsToAdd",true),
   nodeConfigsToRemove=values(street.nodeConfigsToRemove,"nodeConfigsToRemove")}
  local function check(ok,reason)
   assert(ok,reason.."; nativeScope="..json.encode(scope))
  end
  check(#scope.toRemove==1 and scope.toRemove[1]==s.entity,"Removal proposal includes unexpected constructions")
  check(scope.toAdd==0 and scope.old2new==0,"Removal proposal adds/replaces constructions")
  check(scope.addedSegments==0 and scope.addedNodes==0 and scope.edgeObjectsToAdd==0
   and scope.new2oldEdgeObjects==0 and scope.old2newEdgeObjects==0,"Removal proposal modifies additional network objects")
  for _,id in ipairs(scope.removedSegments) do check(s.ownedEdges[tostring(id)],"Removal would remove external road") end
  for _,id in ipairs(scope.removedNodes) do check(s.ownedNodes[tostring(id)] and not s.nodes[tostring(id)],"Removal would remove external node") end
  local paired={};local expectedUpdates={}
  for id,c in pairs(s.nodeConfigs) do
   if stableDataSignature(c)~=stableDataSignature(s.expectedNodeConfigs[id]) then expectedUpdates[id]=true end
  end
  for _,id in ipairs(scope.nodeConfigsToRemove) do
   local k=tostring(id)
   check(s.boundaryNodes[k] and expectedUpdates[k] and not paired[k],"Unexpected or duplicate boundary configuration removal")
   paired[k]=true
  end
  scope.boundaryConfigs={}
  for _,row in pairs(street.nodeConfigsToAdd) do
   local k=tostring(row.entity)
   check(paired[k]==true,"Unpaired or duplicate boundary configuration replacement")
   local cfg=uiBuild.depotRemovalNodeConfig(row.comp)
   scope.boundaryConfigs[k]={before=s.nodeConfigs[k],expected=s.expectedNodeConfigs[k],proposed=cfg}
   check(stableDataSignature(cfg)==stableDataSignature(s.expectedNodeConfigs[k]),"Boundary configuration changes unrelated to removed depot")
   paired[k]="verified"
  end
  for id in pairs(expectedUpdates) do check(paired[id]=="verified","Missing boundary configuration cleanup") end
  for id in pairs(paired) do check(paired[id]=="verified","Boundary configuration replacement missing") end
  -- Keep the complete native Proposal unchanged. Never feed it to the
  -- SimpleProposal-only conversion path or bypass native errors.
  return p,scope
 end
 function uiBuild.depotRemovalReadback(op)
  local s=op.before;local issues={}
  for _,id in ipairs({s.entity,s.depot}) do if api.engine.entityExists(id) then issues[#issues+1]="target_present:"..id end end
  for id in pairs(s.ownedEdges) do if api.engine.entityExists(tonumber(id)) then issues[#issues+1]="internal_edge_present:"..id end end
  for id in pairs(s.ownedNodes) do if api.engine.entityExists(tonumber(id)) then issues[#issues+1]="internal_node_present:"..id end end
  for id,signature in pairs(s.roads) do
   local c=getComponent(tonumber(id),"BASE_EDGE")
   if not c or stableDataSignature(toPlain(c,0,nil,"Network.BaseEdge"))~=signature then issues[#issues+1]="external_road_changed:"..id end
  end
  for id,signature in pairs(s.nodes) do
   local c=getComponent(tonumber(id),"BASE_NODE")
   if not c or stableDataSignature(toPlain(c,0,nil,"Engine.Component.BaseNode"))~=signature then issues[#issues+1]="external_node_changed:"..id end
  end
  for id,expected in pairs(s.expectedNodeConfigs) do
   local c=uiBuild.depotRemovalNodeConfig(getComponent(tonumber(id),"BASE_NODE_CONFIG"))
   if stableDataSignature(c)~=stableDataSignature(expected) then issues[#issues+1]="external_node_config_changed:"..id end
  end
  for id,old in pairs(s.vehicles) do
   local v=getComponent(tonumber(id),"TRANSPORT_VEHICLE")
   if not v then issues[#issues+1]="vehicle_missing:"..id
   else
    local now=uiBuild.depotRemovalVehicle(v)
    if now.signature~=old.signature or (now.noPath and not old.noPath) then issues[#issues+1]="vehicle_changed:"..id end
   end
  end
  return #issues==0,issues
 end
 function uiBuild.depotRemoval(state,root,ledger,req)
  ledger.depotRemovalPreviews=ledger.depotRemovalPreviews or {}
  ledger.depotRemovalOperations=ledger.depotRemovalOperations or {}
  local function result(op)
   return {operation_id=op.token,request_id=op.request,entity=op.before.entity,depot=op.before.depot,
    session=op.epoch,phase=op.phase,removed=op.verified==true,verified=op.verified==true,
    nativeAccepted=op.nativeAccepted,issues=op.issues,backup_save=op.backup,do_not_resubmit=true}
  end
  local function reconcile(op)
   assert(op.epoch==req.facilityEpoch and op.before.player==api.engine.util.getPlayer(),"Removal operation session/player changed; no automatic reconciliation")
   if op.phase=="dispatch_started" then
    local verified,issues=uiBuild.depotRemovalReadback(op);op.issues=issues
    if verified then
     op.verified=true;op.phase="confirmed"
     if ledger.pending==op.request then ledger.pending=nil end
    end
   end
   state:set(root);return result(op)
  end
  if req.cmd=="get_depot_removal_operation" then
   local op=assert(ledger.depotRemovalOperations[req.args.operation_id],"Unknown depot removal operation")
   return reconcile(op)
  end
  assert(not ledger.pending and not ledger.pendingWorkflow,"Previous mutation unresolved")
  if req.cmd=="preview_depot_removal" then
   local s=uiBuild.depotRemovalSnapshot(req.args.entity)
   local _,scope=uiBuild.depotRemovalProposal(s)
   local token="ui-depot-remove:"..req.id
   ledger.depotRemovalPreviews[token]={before=s,epoch=req.facilityEpoch,clock=assert(wallClock()),round=quotaState(ledger).round}
   state:set(root)
   return {preview=true,preview_token=token,entity=s.entity,depot=s.depot,dependentVehicles=s.dependentVehicles,
    validation="structural_and_native_proposal_scope",nativePreview=false,nativeScope=scope,
    warning="Maintenance coverage changes. Existing operating vehicles are preserved; future routing needs live verification."}
  end
  local token=req.args.preview_token;local t=ledger.depotRemovalPreviews[token]
  ledger.depotRemovalPreviews[token]=nil;state:set(root)
  assert(t and t.epoch==req.facilityEpoch and t.round==quotaState(ledger).round,"Unknown, consumed or stale depot removal preview")
  local now=assert(wallClock());assert(now>=t.clock and now-t.clock<=60,"Depot removal preview expired")
  local fresh=uiBuild.depotRemovalSnapshot(t.before.entity)
  assert(fresh.signature==t.before.signature,"Depot/network/vehicle state changed since preview")
  local p=uiBuild.depotRemovalProposal(fresh)
  local op={token=token,request=req.id,epoch=req.facilityEpoch,before=fresh,backup=req.args.backup_save,phase="dispatch_started"}
  ledger.depotRemovalOperations[token]=op;ledger.pending=req.id;state:set(root)
  -- Persist before native dispatch. Callback mutates local state only; never
  -- writes stale root state from a later callback. Read-only reconciliation is
  -- authoritative when a callback is delayed/lost or dispatch raises.
  local accepted
  applyProposal(p,false,function(ok)accepted=ok==true end)
  op.nativeAccepted=accepted;state:set(root)
  return reconcile(op)
 end

 uiBuild.engine=function(state,param)
  -- Native get() may expose an event-start snapshot. Preserve all nested writes.
  local native,current=state,state:get() or {}
  state={get=function()return current end,set=function(_,v)current=v;native:set(v)end}
  local req=json.decode(param or "")
  assert(type(req)=="table" and type(req.id)=="string" and #req.id==32 and req.id:match("^[0-9a-f]+$"),"Invalid construction envelope")
  local valid,why=pcall(validate,req.cmd,req.args)
  if not valid then emit(req,false,why);return end
  assert(type(req.facilityEpoch)=="string","Missing construction session")
  local root=state:get() or {};local ledger=root.uiConstruction or {requests={},tokens={},count=0}
  reclaimReadBudget(ledger);root.uiConstruction=ledger;state:set(root)
  local quota=quotaState(ledger)
  if ledger.requests[req.id] or ledger.retiredRequests[req.id] then return end -- including all prior rounds
  local function rejectQuota(message)
   -- Retain rejected IDs as well: a later reset never turns a rejected envelope
   -- into an executable command. The finite history guard remains independent.
   if ledger.retiredCount+ledger.count<REPLAY_ID_LIMIT then
    ledger.retiredRequests[req.id]=true;ledger.retiredCount=ledger.retiredCount+1
   end
   state:set(root)
   emit(req,false,{message=message,code="operation_quota_rejected",rejectedBeforeDispatch=true})
  end
  if req.cmd=="reset_operation_quota" then
   local ok,value=pcall(function()
    assert(not ledger.pending and not ledger.pendingWorkflow,"Previous mutation unresolved; cannot reset quota")
    assert(req.args.expected_round==quota.round and req.args.expected_used==quota.used
     and req.args.expected_count==ledger.count,"Quota changed; read status before reset")
    assert(quota.used>0,"Quota is unused; nothing to reset")
    local count=0
    for _,row in pairs(ledger.requests) do
     count=count+1
     assert(row.status=="returned" or row.status=="error" or row.status=="rejected"
      or row.status=="reconciled_rejected","Unresolved request receipt; cannot reset quota")
    end
    assert(count==ledger.count,"Receipt accounting mismatch; cannot reset quota")
    assert(ledger.retiredCount+count+1<REPLAY_ID_LIMIT,"Replay history storage limit reached; cannot reset quota")
    local previous={round=quota.round,used=quota.used,activeRequestCount=ledger.count}
    for id in pairs(ledger.requests)do ledger.retiredRequests[id]=true end
    ledger.retiredRequests[req.id]=true -- reset itself is never replayable
    ledger.retiredCount=ledger.retiredCount+count+1
    ledger.requests={};ledger.count=0
    -- No preview from an earlier round may be committed after resetting.
    ledger.tokens={};ledger.linePreviews={};ledger.edgePreviews={};ledger.workflowTokens={}
    ledger.depotRemovalPreviews={};ledger.structurePreviews={};ledger.consistPreviews={};ledger.removalPreviews={};ledger.snapshotBuffer=nil
    quota.round=quota.round+1;quota.used=0
    return {reset=true,previous=previous,round=quota.round,used=0,limit=QUOTA_LIMIT,
     remaining=QUOTA_LIMIT,retiredRequestCount=ledger.retiredCount,session=req.facilityEpoch,
     historyPreserved=true,previewsInvalidated=true}
   end)
   if not ok and ledger.retiredCount+ledger.count<REPLAY_ID_LIMIT then
    ledger.retiredRequests[req.id]=true;ledger.retiredCount=ledger.retiredCount+1
   end
   state:set(root);emit(req,ok,value);return
  end
  if not pureEngineReads[req.cmd] then
   if quota.used>=QUOTA_LIMIT then rejectQuota("Operation quota exhausted; read status and explicitly reset after reconciliation");return end
   if ledger.count>=SAVED_MUTATION_LIMIT then rejectQuota("Saved construction request limit reached; explicit quota reset required");return end
   if ledger.retiredCount+ledger.count>=REPLAY_ID_LIMIT then rejectQuota("Replay history storage limit reached");return end
   quota.used=quota.used+1
  end
  ledger.requests[req.id]={status="started",cmd=req.cmd};ledger.count=ledger.count+1
  root.uiConstruction=ledger;state:set(root)
  if req.cmd=="begin_snapshot" or req.cmd=="read_snapshot_page" or req.cmd=="release_snapshot" then
   local ok,value=pcall(function()
    local a=req.args
    if req.cmd=="begin_snapshot" then
     local args={spacing=a.spacing,whole_map=a.whole_map,start_construction=a.start_construction,end_construction=a.end_construction}
     local command
     if a.snapshot_kind=="planning" then
      assert(a.start_construction==nil and a.end_construction==nil and a.whole_map==nil,"Planning snapshot accepts bounds/spacing only")
      args={bounds=a.bounds,spacing=a.spacing};command="get_planning_snapshot"
     else
      assert(a.bounds==nil and a.start_construction~=nil and a.end_construction~=nil and a.start_construction~=a.end_construction,"Route snapshot needs distinct station constructions")
      assert((a.spacing or 100)<=250,"Route spacing exceeds 250")
      command="get_route_snapshot"
     end
     local result=commands[command](args)
     local encoded=json.encode(result);assert(#encoded<=8388608,"Snapshot exceeds 8 MiB; reduce survey area")
     ledger.snapshotBuffer={token=req.id,epoch=req.facilityEpoch,data=encoded,clock=assert(wallClock())}
     return {snapshot=req.id,bytes=#encoded,session=req.facilityEpoch,state=result.state,encoding="hex_utf8_json",pageBytes=24000}
    end
    local t=assert(ledger.snapshotBuffer,"Snapshot missing or released")
    assert(t.epoch==req.facilityEpoch and t.token==a.snapshot,"Snapshot session/token mismatch")
    local now=assert(wallClock());assert(now>=t.clock and now-t.clock<=600,"Snapshot expired")
    if req.cmd=="release_snapshot" then ledger.snapshotBuffer=nil;return {released=true,snapshot=a.snapshot} end
    assert(a.offset<=#t.data,"Snapshot offset out of range")
    local last=math.min(#t.data,a.offset+24000)
    return {snapshot=a.snapshot,offset=a.offset,nextOffset=last,totalBytes=#t.data,hex=hexEncode(t.data:sub(a.offset+1,last)),hasMore=last<#t.data,session=req.facilityEpoch}
   end)
   ledger.requests[req.id]={status=ok and "returned" or "error",cmd=req.cmd,ok=ok}
   state:set(root);emit(req,ok,value);return
  end
  if req.cmd=="preview_road_upgrade" or req.cmd=="preview_street_stop" or req.cmd=="commit_edge_edit" then
   local ok,value=pcall(function()
    assert(not ledger.pending,"Previous mutation unresolved")
    ledger.edgePreviews=ledger.edgePreviews or {}
    if req.cmd~="commit_edge_edit" then
     local args={};for k,v in pairs(req.args) do args[k]=v end;args.preview=true
     local signature=edgeSignature(args.edge)
     local command=req.cmd=="preview_road_upgrade" and "upgrade_road" or "build_street_stop"
     local r=commands[command](args);r.preview=true
     local allowed=command=="upgrade_road" and (r.validation=="structural_only" or r.noChange==true)
      or command=="build_street_stop" and r.ok==true and not r.blocked and not r.critical and #r.collisions==0
     if allowed then
      local token="ui-edge:"..req.id
      ledger.edgePreviews[token]={args=args,command=command,signature=signature,clock=assert(wallClock()),epoch=req.facilityEpoch,player=api.engine.util.getPlayer()}
      r.preview_token=token
     end
     return r
    end
    local t=ledger.edgePreviews[req.args.preview_token];ledger.edgePreviews[req.args.preview_token]=nil;state:set(root)
    assert(t and t.epoch==req.facilityEpoch,"Unknown, consumed or stale edge preview")
    local now=assert(wallClock());assert(now>=t.clock and now-t.clock<=60,"Edge preview expired")
    assert(t.player==api.engine.util.getPlayer() and t.signature==edgeSignature(t.args.edge),"Edge/player changed")
    ledger.pending=req.id;state:set(root)
    t.args.preview=false;local r=commands[t.command](t.args)
    if r.verified==true or r.noChange==true then ledger.pending=nil end
    return r
   end)
   ledger.requests[req.id]={status=ok and "returned" or "error",cmd=req.cmd,ok=ok,result=value}
   state:set(root);emit(req,ok,value);return
  end
  local function rememberBuilt(value)
   if type(value)~="table" or value.built~=true or value.verified~=true then return end
   ledger.createdEntities=ledger.createdEntities or {}
   for _,id in ipairs(value.edges or {}) do ledger.createdEntities[tostring(id)]={epoch=req.facilityEpoch,request=req.id,kind="edge"} end
   local id=value.entity or value.construction
   if id then ledger.createdEntities[tostring(id)]={epoch=req.facilityEpoch,request=req.id,kind="construction"} end
  end
  local function removalState(id)
   local receipt=(ledger.createdEntities or {})[tostring(id)]
   assert(receipt and receipt.epoch==req.facilityEpoch,"Removal limited to independently verified objects built by this channel in the current session")
   assert(api.engine.entityExists(id),"Test object is already absent; do not resubmit")
   local e=getComponent(id,"BASE_EDGE")
   if e then
    assert(not constructionOfEdge(id) and #listOf(e.objects)==0,"Test edge acquired construction/station dependencies")
    for _,node in ipairs({e.node0,e.node1}) do for _,adj in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do
     assert((ledger.createdEntities or {})[tostring(adj)],"Test edge connects to pre-existing network; removal refused")
    end end
    return stableDataSignature({kind="edge",comp=toPlain(e,0,nil,"Network.BaseEdge")}),"edge"
   end
   local c=assert(getComponent(id,"CONSTRUCTION"),"Test construction missing")
   assert(c.fileName=="::/warehouses/warehouse.con" and ownerOf(id)==api.engine.util.getPlayer(),"Only owned empty test warehouses or test edges may be removed")
   local stocks={}
   api.engine.forEachEntityWithComponent(function(wid)
    local w=getComponent(wid,"WAREHOUSE")
    if w.construction==id then
     local st=assert(getComponent(w.stockList,"STOCK_LIST"),"Warehouse stock unavailable")
     assert(#listOf(st.stocks)<=4,"Test warehouse exceeds removal bound")
     for i in ipairs(listOf(st.stocks)) do for cargo in pairs(api.res.cargoTypeRep.getAll(true)) do
      assert(api.engine.system.simEntityAtStockSystem.getStockCountForCargoType(w.stockList,i-1,cargo)==0,"Test warehouse contains cargo; removal refused")
     end end
     stocks[#stocks+1]=w.stockList
    end
   end,componentTypes().WAREHOUSE)
   assert(#stocks>0,"Warehouse inventory identity unavailable")
   table.sort(stocks)
   return stableDataSignature({kind="warehouse",config=commands.get_facility_config({entity=id}),stocks=stocks}),"warehouse"
  end
  if req.cmd=="preview_depot_removal" or req.cmd=="commit_depot_removal" or req.cmd=="get_depot_removal_operation" then
   local ok,value=pcall(uiBuild.depotRemoval,state,root,ledger,req)
   ledger.requests[req.id]={status=ok and "returned" or "error",cmd=req.cmd,ok=ok,result=value}
   state:set(root);emit(req,ok,value);return
  end
  if req.cmd=="preview_test_removal" or req.cmd=="commit_test_removal" then
   local ok,value=pcall(function()
    assert(not ledger.pending,"Previous mutation unresolved")
    ledger.removalPreviews=ledger.removalPreviews or {}
    if req.cmd=="preview_test_removal" then
     local signature,kind=removalState(req.args.entity);local token="ui-remove:"..req.id
     ledger.removalPreviews[token]={entity=req.args.entity,signature=signature,kind=kind,epoch=req.facilityEpoch,clock=assert(wallClock())}
     return {preview=true,preview_token=token,entity=req.args.entity,kind=kind,validation="structural_only",nativePreview=false}
    end
    local t=ledger.removalPreviews[req.args.preview_token];ledger.removalPreviews[req.args.preview_token]=nil;state:set(root)
    assert(t and t.epoch==req.facilityEpoch,"Unknown, consumed or stale removal preview")
    local now=assert(wallClock());assert(now>=t.clock and now-t.clock<=60,"Removal preview expired")
    assert(removalState(t.entity)==t.signature,"Test object changed since preview")
    local p=t.kind=="edge" and api.engine.util.proposal.makeSegmentsRemoveProposal({t.entity})
     or api.engine.util.proposal.createProposalRemove(t.entity,api.type.Context.new())
    assert(p,"Native removal proposal unavailable")
    ledger.pending=req.id;state:set(root);local accepted=false
    applyProposal(p,false,function(ok)accepted=ok==true end)
    local verified=accepted and not api.engine.entityExists(t.entity)
    if verified then ledger.pending=nil;ledger.createdEntities[tostring(t.entity)]=nil end
    return {entity=t.entity,submitted=true,removed=verified,verified=verified,do_not_resubmit=true}
   end)
   ledger.requests[req.id]={status=ok and "returned" or "error",cmd=req.cmd,ok=ok,result=value}
   state:set(root);emit(req,ok,value);return
  end
  if req.cmd=="get_validation_state" then
   local names={};for cmd in pairs(schemas) do names[#names+1]=cmd end;table.sort(names)
   ledger.requests[req.id]={status="returned",cmd=req.cmd,ok=true};state:set(root)
   emit(req,true,{townPassengerSupplyVersion=1,townCargoSupplyVersion=2,notificationsVersion=1,capabilityRevision="consolidated-20261011-v40",subventionReconciliationVersion=1,assignmentReconciliationVersion=1,depotRemovalVersion=1,depotRemovalFingerprintVersion=5,edgeEditSignaturePolicy="crosswalk-membership-v1",frontageDiscoveryPolicy="displaced-discovery-node-v5",frontageHeightPolicy="native-foundation-alignment-v1",roadGradePolicy="native-preview-v1",commands=names,
    roadGraph={command="preview_road_graph",isolatedTestRequired=false,mapUsePolicy="current-map-authorized-v1",
     nodeLimit=32,edgeLimit=48,splitPreview="structural_only",pairedHighway="host_compiler",
     specialCases="v37_candidate_pending_native_acceptance",unsupported={"frozen_internal_nodes","construction_owned_splits","rail_signal_object_splits","custom_rail_switches"}},
    roadJunctionBranch={command="preview_network",flag="connect_road_junctions",existingDegree=2,isolatedTestRequired=false,mapUsePolicy="current-map-authorized-v1"},
    durableRequestCount=ledger.count,pending=ledger.pending,mutationLimit=SAVED_MUTATION_LIMIT,
    operationQuota={version=1,round=quota.round,used=quota.used,limit=QUOTA_LIMIT,
     remaining=math.max(0,QUOTA_LIMIT-quota.used),activeRequestCount=ledger.count-1,
     retiredRequestCount=ledger.retiredCount,replayIdLimit=REPLAY_ID_LIMIT,
     resetCommand="reset_operation_quota",requiresReconciliation=true},
    session=req.facilityEpoch,verification="capabilities only, not live feature acceptance"});return
  end
  local structureCommands={preview_depot="build_depot",preview_station="build_station",preview_rail_station="build_rail_station"}
  local function structureAllowed(v)
   return type(v)=="table" and v.ok==true and not v.critical and not v.blocked and not v.placementBlocked
    and type(v.collisions)=="table" and next(v.collisions)==nil
  end
  if structureCommands[req.cmd] or req.cmd=="commit_structure" then
   local ok,value=pcall(function()
    assert(not ledger.pending,"Previous construction outcome unresolved")
    ledger.structurePreviews=ledger.structurePreviews or {}
    if structureCommands[req.cmd] then
     local args={};for k,v in pairs(req.args) do args[k]=v end
     args.preview=true;args.connect=false;args.allow_collisions=false
     local result=commands[structureCommands[req.cmd]](args)
     result.preview=true;result.externalConnectionsBuilt=false
     if structureAllowed(result) then
      local now=wallClock();assert(now,"Preview requires clock")
      local token="ui-structure:"..req.id
      local signature
      if args.frontage_node then local _,s=frontageAdapter.inspect(args.frontage_node);signature=s end
      ledger.structurePreviews[token]={command=structureCommands[req.cmd],args=args,created=now,epoch=req.facilityEpoch,player=api.engine.util.getPlayer(),frontageSignature=signature}
      result.preview_token=token
     end
     return result
    end
    local token=req.args.preview_token;local p=ledger.structurePreviews[token]
    ledger.structurePreviews[token]=nil;state:set(root)
    assert(p and p.epoch==req.facilityEpoch,"Unknown, consumed or stale structure preview")
    local now=wallClock();assert(now and now>=p.created and now-p.created<=60,"Structure preview expired")
    assert(p.player==api.engine.util.getPlayer(),"Player changed")
    if p.args.frontage_node then
     local _,signature=frontageAdapter.inspect(p.args.frontage_node)
     assert(signature==p.frontageSignature,"Frontage changed since preview; investigate again")
    end
    local fresh=commands[p.command](p.args)
    assert(structureAllowed(fresh),"Structure preview no longer buildable")
    ledger.pending=req.id;state:set(root) -- reserve before native dispatch
    local args={};for k,v in pairs(p.args) do args[k]=v end;args.preview=false
    local result=commands[p.command](args)
    local id=result.construction
    assert(result.built==true and result.verified~=false and type(id)=="number" and getComponent(id,"CONSTRUCTION"),"Structure outcome incomplete; reconcile, never retry")
    assert(ownerOf(id)==p.player,"Constructed object ownership not confirmed")
    result.verified=true;result.verificationScope="construction entity and owner only; connections and operation require independent acceptance"
    result.externalConnectionsBuilt=false;ledger.pending=nil;rememberBuilt(result)
    return result
   end)
   ledger.requests[req.id]={status=ok and "returned" or "error",cmd=req.cmd,ok=ok,result=value}
   state:set(root);emit(req,ok,value);return
  end
  if req.cmd=="preview_consist" or req.cmd=="preview_multiple_unit" then
   local ok,value=pcall(function()
    assert(not ledger.pending,"Previous mutation unresolved")
    local _,result,signature=makeConsist(req.args)
    local now=wallClock();assert(now,"Preview requires clock")
    local token="ui-consist:"..req.id
    ledger.consistPreviews=ledger.consistPreviews or {}
    ledger.consistPreviews[token]={args=req.args,signature=signature,created=now,epoch=req.facilityEpoch}
    result.preview=true;result.preview_token=token;return result
   end)
   ledger.requests[req.id]={status=ok and "returned" or "rejected",cmd=req.cmd,ok=ok}
   state:set(root);emit(req,ok,value);return
  end
  if req.cmd=="preview_line_edit" then
   local ok,value=pcall(function()
    assert(not ledger.pending,"Previous mutation unresolved")
    local config,signature,terminalSignature=uiBuild.editLine(req.args)
    local token="ui-line:"..req.id;ledger.linePreviews=ledger.linePreviews or {}
    ledger.linePreviews[token]={edit=true,args=req.args,signature=signature,terminalSignature=terminalSignature,created=assert(wallClock()),epoch=req.facilityEpoch}
    return {preview=true,preview_token=token,line=req.args.line,stopCount=#req.args.stops,cost=0,configurationOnly=true,pathVerified=false,retainedComplexStops=true}
   end)
   ledger.requests[req.id]={status=ok and "returned" or "rejected",cmd=req.cmd,ok=ok}
   state:set(root);emit(req,ok,value);return
  end
  if req.cmd=="preview_line_stop" or req.cmd=="preview_line_terminal" then
   local ok,value=pcall(function()
    assert(not ledger.pending,"Previous mutation unresolved")
    local snap,signature=lineSnapshot(req.args.line)
    assert(req.args.stop_index<#snap.stops,"stop_index outside current line stops")
    local terminalSignature=terminalSelection(snap,req.args)
    lineWithConfig(snap,req.args) -- validate/copy only; never send during preview
    local now=wallClock();assert(now,"Preview requires clock")
    local token="ui-line:"..req.id
    ledger.linePreviews=ledger.linePreviews or {}
    ledger.linePreviews[token]={args=req.args,signature=signature,terminalSignature=terminalSignature,created=now,epoch=req.facilityEpoch}
    return {preview=true,preview_token=token,line=req.args.line,stop_index=req.args.stop_index,cost=0,configurationOnly=true}
   end)
   ledger.requests[req.id]={status=ok and "returned" or "rejected",cmd=req.cmd,ok=ok}
   state:set(root);emit(req,ok,value);return
  end
  if ({set_game_speed=true,commit_consist=true,create_line=true,buy_vehicles=true,assign_vehicles=true,set_vehicle_stopped=true,send_to_depot=true,delete_line=true,sell_vehicles=true,commit_line_stop=true})[req.cmd] then
   if ledger.pending then
    ledger.requests[req.id]={status="rejected",cmd=req.cmd,ok=false}
    state:set(root);emit(req,false,"Previous construction outcome unresolved; reconcile before further mutations");return
   end
   local overrideHandler,expectedLine
   if req.cmd=="set_game_speed" or req.cmd=="commit_consist" or req.cmd=="assign_vehicles" or req.cmd=="delete_line" or req.cmd=="sell_vehicles" or req.cmd=="commit_line_stop" then
    local validAssignment,assignmentError=pcall(function()
     if req.cmd=="set_game_speed" then
      local before=commands.get_game_state({})
      assert(before.speedup==req.args.expected_speed,"Game speed changed; read current state before a new request")
      overrideHandler=function(args,reply)
       return sendGameCommand(api.cmd.makeGameSetSpeedCmd(args.speed),reply,function()
        local after=commands.get_game_state({})
        assert(after.world==before.world and after.player==before.player and after.speedup==args.speed,
         "Game speed readback mismatch; reconcile, never retry")
        return {speedup=after.speedup,previousSpeed=before.speedup,verified=true}
       end)
      end
     elseif req.cmd=="commit_consist" then
      local token=req.args.preview_token;local p=(ledger.consistPreviews or {})[token]
      if ledger.consistPreviews then ledger.consistPreviews[token]=nil end
      state:set(root)
      assert(p and p.epoch==req.facilityEpoch,"Unknown, consumed or stale consist preview")
      local now=wallClock();assert(now and now>=p.created and now-p.created<=60,"Consist preview expired")
      local config,review,signature=makeConsist(p.args)
      assert(signature==p.signature,"Consist quote or resource identity changed")
      overrideHandler=function(_,reply)
       return sendGameCommand(api.cmd.makeVehicleBuyCmd(api.engine.util.getPlayer(),p.args.depot,config),reply,function(res)
        local id=res.resultVehicleEntity
        return {bought={id},partCount=review.partCount,depot=p.args.depot}
       end)
      end
     elseif req.cmd=="delete_line" then
      requireEntity(req.args,"line","LINE")
      assert(ownerOf(req.args.line)==api.engine.util.getPlayer(),"Line is not owned by current player")
      assert(#listOf(api.engine.system.transportVehicleSystem.getLineVehicles(req.args.line))==0,"Line still has assigned vehicles")
     elseif req.cmd=="sell_vehicles" then
      local id=requireEntity({vehicle=req.args.vehicles[1]},"vehicle","TRANSPORT_VEHICLE")
      assert(ownerOf(id)==api.engine.util.getPlayer(),"Vehicle is not owned by current player")
      local v=getComponent(id,"TRANSPORT_VEHICLE")
      assert(v.state==api.type.enum.TransportVehicleState.IN_DEPOT,"Sale requires vehicle in depot")
      local found=false
      for _,id2 in ipairs(listOf(api.engine.system.transportVehicleSystem.getDepotVehicles(v.depot))) do if id2==id then found=true end end
      assert(found,"Vehicle not independently listed in depot")
     elseif req.cmd=="commit_line_stop" then
      local token=req.args.preview_token;local p=(ledger.linePreviews or {})[token]
      if ledger.linePreviews then ledger.linePreviews[token]=nil end
      state:set(root)
      assert(p and p.epoch==req.facilityEpoch,"Unknown, consumed or stale line preview")
      local now=wallClock();assert(now and now>=p.created and now-p.created<=60,"Line preview expired")
      local config
      if p.edit then
       local signature,terminalSignature
       config,signature,terminalSignature=uiBuild.editLine(p.args)
       assert(signature==p.signature and terminalSignature==p.terminalSignature,"Line or terminal changed since preview")
      else
       local snap,signature=lineSnapshot(p.args.line)
       assert(signature==p.signature,"Line configuration changed since preview")
       assert(terminalSelection(snap,p.args)==p.terminalSignature,"Station/terminal identity changed since preview")
       config=lineWithConfig(snap,p.args)
      end
      expectedLine=p.args.line
      local expectedSignature=p.edit and uiBuild.lineSignature(config) or nil
      overrideHandler=function(_,reply)
       return sendGameCommand(api.cmd.makeLineUpdateCmd(expectedLine,config),reply,function()
        if expectedSignature then assert(uiBuild.lineSignature(getComponent(expectedLine,"LINE"))==expectedSignature,"Line readback mismatch; reconcile without retry") end
        return {updated=true,line=expectedLine,stop_index=p.args.stop_index,configurationVerified=expectedSignature~=nil,pathVerified=false}
       end)
      end
     else
     requireEntity({vehicle=req.args.vehicles[1]},"vehicle","TRANSPORT_VEHICLE")
     local line=requireEntity(req.args,"line","LINE")
     assert(req.args.stop_index<#listOf(getComponent(line,"LINE").stops),"stop_index outside current line stops")
     end
    end)
    if not validAssignment then
     ledger.requests[req.id]={status="rejected",cmd=req.cmd,ok=false};state:set(root)
     emit(req,false,assignmentError);return
    end
   end
   -- Reserve before native dispatch. A delayed or missing callback cannot authorize retry.
   ledger.pending=req.id;state:set(root)
   local dispatching=true
   runRequest(req,function(ok,value)
    -- The event-local state supports synchronous callbacks; later callbacks merge
    -- into fresh persisted state rather than overwriting subsequent read events.
    local latest=dispatching and state:get() or native:get()
    local journal=latest and latest.uiConstruction
    local record=journal and journal.requests[req.id]
    if not record or record.status~="started" or journal.pending~=req.id then return end
    local function entity(v)return type(v)=="number" and v%1==0 and v>=0 and v<2147483647 end
    local complete=false
    if ok and type(value)=="table" then
     if req.cmd=="set_game_speed" then complete=value.verified==true and value.speedup==req.args.speed and value.previousSpeed==req.args.expected_speed
     elseif req.cmd=="commit_consist" then complete=type(value.bought)=="table" and #value.bought==1 and entity(value.bought[1])
     elseif req.cmd=="create_line" then complete=entity(value.line)
     elseif req.cmd=="buy_vehicles" then
      complete=type(value.bought)=="table" and #value.bought==1 and entity(value.bought[1]) and type(value.failures)=="table" and next(value.failures)==nil
     elseif req.cmd=="assign_vehicles" then
      complete=value.line==req.args.line and type(value.assigned)=="table" and #value.assigned==1 and value.assigned[1]==req.args.vehicles[1] and type(value.failures)=="table" and next(value.failures)==nil
     elseif req.cmd=="set_vehicle_stopped" then complete=value.vehicle==req.args.vehicle and value.stopped==req.args.stopped
     elseif req.cmd=="send_to_depot" then complete=value.vehicle==req.args.vehicle and value.sellOnArrival==false
     elseif req.cmd=="delete_line" then complete=value.deleted==req.args.line
     elseif req.cmd=="sell_vehicles" then complete=type(value.sold)=="table" and #value.sold==1 and value.sold[1]==req.args.vehicles[1]
     elseif req.cmd=="commit_line_stop" then complete=value.updated==true and value.line==expectedLine end
    end
    local original=value
    if ok and not complete then ok=false;value="Incomplete mutation result; reconcile, never retry: "..json.encode(value) end
    journal.requests[req.id]={status=ok and "returned" or "error",cmd=req.cmd,ok=ok,result=original}
    if complete then journal.pending=nil end
    latest.uiConstruction=journal
    if dispatching then state:set(latest) else native:set(latest) end
    emit(req,ok,value)
   end,overrideHandler)
   dispatching=false
   return
  end
  local ok,value=pcall(function()
   if req.cmd=="reconcile_facility_rejection" then
    -- Exact durable error emitted only before proposal creation/applyProposal.
    -- No timeout, collision result, native failure, or arbitrary error qualifies.
    local id=req.args.request_id;local old=ledger.requests[id]
    local reason="facility changed since preview; inspect and preview again"
    assert(ledger.pending==id and old and old.cmd=="commit_facility" and old.status=="error" and old.ok==false
     and old.error==reason,"No matching pre-submit facility rejection; pending remains blocked")
    local found=false
    for _,row in ipairs((state:get() or {}).responses or {}) do if row.id==id then
     assert(not found,"Ambiguous facility rejection evidence");found=true
     local proof=json.decode(row.text)
     assert(proof.id==id and proof.ok==false and proof.error==reason,"Conflicting facility rejection evidence")
    end end
    old.status="reconciled_rejected";old.retryAllowed=false;old.nativeSubmissionAttempted=false
    ledger.pending=nil
    return {request_id=id,status="reconciled_rejected",nativeSubmissionAttempted=false,retryAllowed=false,
     verificationScope="persisted pre-submit fingerprint rejection; fresh survey and preview required"}
   end
   if req.cmd=="reconcile_assignment_rejection" then
    -- Close only one explicit native false callback, never a lost/partial result.
    -- The original durable result is retained and its request ID stays replay-blocked.
    local a=req.args;local id=a.request_id;local old=ledger.requests[id]
    assert(ledger.pending==id and not ledger.pendingWorkflow and old and old.cmd=="assign_vehicles"
     and old.status=="error" and old.ok==false,"No matching terminal assignment rejection")
    local proof=old.result
    assert(type(proof)=="table" and proof.line==a.line and type(proof.assigned)=="table"
     and next(proof.assigned)==nil and type(proof.failures)=="table"
     and proof.failures[1]=="vehicle "..tostring(a.vehicle).." rejected",
     "Assignment result is not an explicit single-vehicle rejection")
    local count=0;for key in pairs(proof.failures) do count=count+1;assert(key==1,"Ambiguous failure evidence") end
    assert(count==1,"Missing failure evidence")
    requireEntity(a,"vehicle","TRANSPORT_VEHICLE");requireEntity(a,"line","LINE")
    local player=api.engine.util.getPlayer();local v=getComponent(a.vehicle,"TRANSPORT_VEHICLE")
    assert(commands.get_game_state({}).speedup==0,"Pause required for rejection reconciliation")
    assert(ownerOf(a.vehicle)==player and ownerOf(a.line)==player,"Assignment ownership changed")
    assert(v.line==-1 and v.state==api.type.enum.TransportVehicleState.IN_DEPOT,
     "Vehicle state conflicts with assignment rejection")
    local found=false
    for _,vehicle in ipairs(listOf(api.engine.system.transportVehicleSystem.getDepotVehicles(v.depot))) do
     if vehicle==a.vehicle then found=true end
    end
    assert(found,"Vehicle not independently listed in depot")
    for _,vehicle in ipairs(listOf(api.engine.system.transportVehicleSystem.getLineVehicles(a.line))) do
     assert(vehicle~=a.vehicle,"Vehicle is listed on rejected line")
    end
    old.status="reconciled_rejected";old.retryAllowed=false;old.nativeAccepted=false
    old.reconciliation={vehicle=a.vehicle,line=a.line,depot=v.depot,player=player,
     evidenceSource="durable_native_false_callback_and_unassigned_depot_readback"}
    ledger.pending=nil
    return {request_id=id,status="reconciled_rejected",nativeAccepted=false,retryAllowed=false,
     vehicle=a.vehicle,line=a.line,depot=v.depot,gameMutation=false,
     verificationScope="rejected assignment only; no retry, route repair or operation acceptance"}
   end
   if req.cmd=="reconcile_depot_rejection" then
    -- A single depot command with an explicit native false callback only.
    -- Do not accept a timeout, partial response, thrown error or other mutation.
    -- This records rejection, never retries the command or claims physical return.
    local id=req.args.request_id;local old=ledger.requests[id]
    assert(ledger.pending==id and old and old.cmd=="send_to_depot" and old.status=="error" and old.ok==false
     and old.result=="game rejected the command","No matching explicitly rejected depot command")
    old.status="reconciled_rejected";old.retryAllowed=false
    ledger.pending=nil
    return {request_id=id,status="reconciled_rejected",nativeAccepted=false,retryAllowed=false,
     verificationScope="native rejection receipt only; vehicle state requires independent readback"}
   end
   if req.cmd=="reconcile_road_rejection" or req.cmd=="reconcile_network_rejection" then
    -- Explicit recovery only for an exact, persisted pre-dispatch rejection.
    -- Never clears a native failure, timeout, partial build, or unrelated pending ID.
    local id=req.args.request_id;local old=ledger.requests[id]
    local command=req.cmd=="reconcile_network_rejection" and "commit_network" or "commit_road"
    assert(ledger.pending==id and old and old.cmd==command and old.status=="error" and old.ok==false,"No matching rejected road request")
    local proof,cached,source
    for _,row in ipairs((state:get() or {}).responses or {}) do
     if row.id==id then
      assert(not cached,"Ambiguous road rejection evidence")
      cached=json.decode(row.text)
     end
    end
    if old.error then
     proof={id=id,cmd=command,ok=false,error=old.error};source="durable_engine_ledger"
     assert(not cached or cached.id==id and (cached.cmd==nil or cached.cmd==command) and cached.ok==false and cached.error==old.error,"Conflicting rejection evidence")
    elseif cached then proof=cached;source="engine_response_cache"
    end
    local suffix=command=="commit_network" and "Network endpoints or template changed" or "Unknown or consumed road preview; do not retry"
    local network=(state:get() or {}).uiNetworkAdapter or {}
    local op=(network.operations or {})[id]
    local noDispatch=command=="commit_network" and old.error and op and op.id==id and op.cmd==command
     and op.phase=="pre_dispatch" and not (network.previews or {})[op.token] and not ledger.tokens[op.token]
    if op then assert(noDispatch,"Network dispatch was reached or phase proof is incomplete; pending remains blocked") end
    local signatureProof=proof and type(proof.error)=="string" and proof.error:sub(-#suffix)==suffix
    local pinned=false;local identityDelta
    if not noDispatch and not signatureProof and command=="commit_network" and NETWORK_REJECTION_MIGRATION then
     -- Legacy builds retained no error in the durable ledger. This immutable
     -- installer payload comes from the host's archived original native receipt,
     -- Bound to the old engine epoch and consumed token. Default is exact map;
     -- an explicit installer opt-in permits only audited industry additions.
     local m=json.decode(NETWORK_REJECTION_MIGRATION)
     local network=(state:get() or {}).uiNetworkAdapter or {}
     assert(m.id==id and m.cmd==command and network.epoch==m.session,"Legacy rejection lineage mismatch")
     assert(not (network.previews or {})[m.token] and not ledger.tokens[m.token],"Legacy preview was not consumed")
     local map=commands.get_map_info({});local identity={width=map.width,height=map.height,towns={},industries={}}
     for _,kind in ipairs({"towns","industries"}) do
      for _,v in ipairs(map[kind]) do
       local key=tostring(v.id);local label=kind=="towns" and "name" or "fileName"
       assert(type(v.id)=="number" and v.id>=0 and v.id%1==0 and not identity[kind][key],"Invalid or duplicate recovery map entity")
       assert(type(v[label])=="string" and #v[label]>0 and type(v.position)=="table","Incomplete recovery map entity")
       for _,axis in ipairs({"x","y"}) do
        local n=v.position[axis];assert(type(n)=="number" and n==n and math.abs(n)<math.huge,"Invalid recovery map position")
       end
       identity[kind][key]={[label]=v[label],position=v.position}
      end
     end
     assert(api.engine.util.getPlayer()==m.player,"Legacy rejection player mismatch")
     if m.identityPolicy=="original_objects_plus_industry_additions" then
      assert(identity.width==m.map.width and identity.height==m.map.height
       and stableDataSignature(identity.towns)==stableDataSignature(m.map.towns),"Legacy rejection map/towns mismatch")
      assert(next(m.map.industries)~=nil,"Empty recovery industry baseline")
      for key,v in pairs(m.map.industries) do
       assert(identity.industries[key] and stableDataSignature(identity.industries[key])==stableDataSignature(v),"Original recovery industry removed or changed")
      end
      identityDelta={policy=m.identityPolicy,addedIndustries={},removed=0,changed=0,oldPreviewsReusable=false}
      for key,v in pairs(identity.industries) do
       if not m.map.industries[key] then identityDelta.addedIndustries[#identityDelta.addedIndustries+1]={id=tonumber(key),fileName=v.fileName,position=v.position} end
      end
      table.sort(identityDelta.addedIndustries,function(a,b)return a.id<b.id end)
     else
      assert(m.identityPolicy==nil or m.identityPolicy=="exact","Unknown recovery identity policy")
      assert(stableDataSignature(identity)==stableDataSignature(m.map),"Legacy rejection map/player mismatch")
     end
     assert(not proof or proof.error==m.error,"Conflicting installer and engine rejection proof")
     assert(m.error:sub(-#suffix)==suffix or m.rejectionKind=="network_edge_enumeration_before_dispatch","Unsupported pinned rejection kind")
     proof=m;source="installer_pinned_host_receipt";pinned=true
    end
    assert(proof and proof.id==id and (proof.cmd==nil or proof.cmd==command) and proof.ok==false and type(proof.error)=="string"
     and (noDispatch or signatureProof or pinned),"No verified pre-dispatch rejection; pending remains blocked")
    if noDispatch then source="durable_engine_pre_dispatch_phase" end
    old.status="reconciled_rejected";old.mutationAttempted=false;old.rejectionEvidenceSource=source;old.recoveryIdentityDelta=identityDelta
    ledger.pending=nil
    return {request_id=id,status="reconciled_rejected",mutationAttempted=false,retryAllowed=false,evidenceSource=source,identityDelta=identityDelta}
   end
   if req.cmd=="reconcile_subvention_rejection" then
    local id=req.args.request_id;local old=ledger.requests[id];local p=ledger.pendingWorkflow
    assert(ledger.pending==id and old and old.cmd=="commit_subvention" and old.status=="error" and old.ok==false
     and old.error=="previous subvention accept requires reconciliation; query state and never resend","No matching pre-dispatch subvention rejection")
    assert(p and p.id==id and p.read=="get_subvention_operation","Subvention workflow lineage missing")
    local adapter=(state:get() or {}).subventionAdapter or {};local token=p.token
    local op=(adapter.operations or {})[token]
    assert(type(adapter.epoch)=="string" and type(token)=="string" and token:sub(1,#adapter.epoch+12)=="subvention:"..adapter.epoch..":"
     and op and op.player==api.engine.util.getPlayer() and type(op.uid)=="number" and type(op.resource)=="string" and type(op.spawnTime)=="number"
     and not (adapter.previews or {})[token] and not (ledger.workflowTokens or {})[token]
     and not (adapter.submitted or {})[tostring(op.uid)] and not op.acceptanceEvidence
     and (op.phase==nil or op.phase=="prepared"),"Subvention may have dispatched or rejection proof is incomplete")
    local native=commands.get_subventions({assess=false})
    for _,row in ipairs(native.tasks) do
     assert(row.uid~=op.uid or (row.status=="Proposed" and row.acceptedTime==nil and row.resource==op.resource and row.spawnTime==op.spawnTime),"Native evidence conflicts with rejection")
    end
    assert(native.gameTime>=op.spawnTime,"Native time regressed")
    op.phase="rejected_before_dispatch";op.rejectionEvidenceSource="durable_exact_error_consumed_workflow_no_submission"
    old.status="reconciled_rejected";old.mutationAttempted=false;old.retryAllowed=false;old.rejectionEvidenceSource=op.rejectionEvidenceSource
    ledger.pending=nil;ledger.pendingWorkflow=nil
    local updated=state:get() or {};updated.subventionAdapter=adapter;updated.uiConstruction=ledger;state:set(updated)
    return {request_id=id,status="reconciled_rejected",mutationAttempted=false,retryAllowed=false,evidenceSource=op.rejectionEvidenceSource}
   end
   if req.cmd=="reconcile_town_cargo_rejection" then
    -- The town handler creates an operation and consumes its preview BEFORE any
    -- native dispatch. An intact matching preview plus no operation, an exact
    -- durable identity-rejection error and unchanged native demand prove this
    -- one request never dispatched. No generic workflow reset is exposed.
    local id=req.args.request_id;local old=ledger.requests[id];local pending=ledger.pendingWorkflow
    assert(ledger.pending==id and old and old.cmd=="commit_town_cargo_needs" and old.status=="error" and old.ok==false
     and type(old.error)=="string" and old.error:match('^%[string "[^\r\n]+bridge%.script%.lua"%]:%d+: town/session changed$'),"No matching pre-dispatch town identity rejection")
    assert(pending and pending.id==id and pending.read=="get_town_cargo_operation","Town workflow lineage missing")
    local adapter=(state:get() or {}).town_cargoAdapter or {};local token=pending.token
    local preview=(adapter.previews or {})[token]
    assert(type(adapter.epoch)=="string" and type(token)=="string" and token:sub(1,#adapter.epoch+12)=="town-cargo:"..adapter.epoch..":"
     and preview and not (adapter.operations or {})[token] and not (ledger.workflowTokens or {})[token],"Town request may have dispatched or preview proof is incomplete")
    local before=preview.before;local now=commands.get_town_cargo_needs({town=before.town})
    local a=before.reference;local b=now.reference
    assert(a and b and a.entity==b.entity and a.revision and b.revision and type(a.revision.num)=="table" and type(b.revision.num)=="table"
     and type(a.revision.num[1])=="number" and type(a.revision.num[2])=="number"
     and a.revision.num[1]==b.revision.num[1] and a.revision.num[2]==b.revision.num[2]
     and before.world==now.world and before.player==now.player and now.gameTime>=before.gameTime,"Town identity no longer matches rejection proof")
    assert(stableDataSignature(before.weighted_needs)==stableDataSignature(now.weighted_needs),"Town demand changed; cannot reconcile rejection")
    adapter.previews[token]=nil
    old.status="reconciled_rejected";old.mutationAttempted=false;old.retryAllowed=false
    old.rejectionEvidenceSource="durable_error_intact_preview_no_operation"
    ledger.pending=nil;ledger.pendingWorkflow=nil
    local updated=state:get() or {};updated.town_cargoAdapter=adapter;updated.uiConstruction=ledger;state:set(updated)
    return {request_id=id,status="reconciled_rejected",mutationAttempted=false,retryAllowed=false,evidenceSource=old.rejectionEvidenceSource}
   end
   if workflowCommits[req.cmd] then
    assert(not ledger.pending,"Previous mutation unresolved")
    local t=(ledger.workflowTokens or {})[req.args.preview_token]
    if ledger.workflowTokens then ledger.workflowTokens[req.args.preview_token]=nil end
    state:set(root)
    assert(t and t.epoch==req.facilityEpoch and t.commit==req.cmd,"Unknown, consumed or mismatched workflow preview")
    ledger.pending=req.id;ledger.pendingWorkflow={id=req.id,token=req.args.preview_token,read=t.read};state:set(root)
   elseif workflows[req.cmd] or req.cmd=="preview_facility_module" or req.cmd=="preview_facility_parameter" then
    assert(not ledger.pending,"Previous mutation unresolved")
   end
   if req.cmd=="commit_facility" or req.cmd=="commit_road" or req.cmd=="commit_network" or req.cmd=="commit_road_graph" then
    assert(not ledger.pending,"Previous construction outcome unresolved; reconcile before further commits")
    local token=req.args.preview_token;local epoch=ledger.tokens[token]
    ledger.tokens[token]=nil
    root=state:get() or {};root.uiConstruction=ledger;state:set(root)
    assert(epoch==req.facilityEpoch,"Commit requires an unused UI preview from this session")
    ledger.pending=req.id;root.uiConstruction=ledger;state:set(root)
   end
   if req.cmd=="list_map_entities" or req.cmd=="release_map_snapshot" then
    local saved=root.uiMapSnapshots
    if saved and saved.epoch==req.facilityEpoch then
     mapSnapshots=saved.entries;mapSnapshotSerial=saved.serial
    else mapSnapshots={};mapSnapshotSerial=0 end
    mapSnapshotSession=req.facilityEpoch
   end
   if ({get_facility_config=true,commit_facility=true,build_facility=true,build_headquarters=true,build_warehouse=true,build_heliport=true,build_airfield=true,build_water_facility=true,build_helipad=true,preview_facility_module=true,preview_facility_parameter=true})[req.cmd] then req.args.compact=true end
   handleEngineEvent(state,json.encode(req))
   if req.cmd=="list_map_entities" or req.cmd=="release_map_snapshot" then
    local updated=state:get() or {}
    updated.uiMapSnapshots={epoch=req.facilityEpoch,entries=mapSnapshots,serial=mapSnapshotSerial}
    state:set(updated)
   end
   local result
   for _,row in ipairs((state:get() or {}).responses or {}) do if row.id==req.id then result=json.decode(row.text) end end
   assert(result,"Engine result missing; do not retry")
   if not result.ok then error(result.error,0) end
   return result.result
  end)
  if ok and type(value)=="table" then
   if value.mode~="configure" then rememberBuilt(value) end
   if workflows[req.cmd] and value.preview_token and not value.blocked then
    ledger.workflowTokens=ledger.workflowTokens or {};local w=workflows[req.cmd]
    ledger.workflowTokens[value.preview_token]={epoch=req.facilityEpoch,commit=w.commit,read=w.read}
   end
   local p=ledger.pendingWorkflow
   if p and ledger.pending==p.id and value.verified==true and
    ((req.id==p.id and workflowCommits[req.cmd]) or (req.cmd==p.read and req.args.operation_id==p.token)) then
    ledger.pending=nil;ledger.pendingWorkflow=nil
   end
  end
  if ok and type(value)=="table" and value.preview_token and value.preview and not value.blocked then
   ledger.tokens[value.preview_token]=req.facilityEpoch
  end
  if ledger.pending==req.id and ok and type(value)=="table" and value.built==true and value.verified==true then ledger.pending=nil end
  if ledger.pending==req.id and req.cmd=="commit_road_graph" and ok and type(value)=="table"
   and value.id==req.id and value.built==false and value.phase=="rejected_unchanged" and value.rejectionVerified==true
   and value.nativeResult and value.nativeResult.explicitRejection==true and value.retryAllowed==false then ledger.pending=nil end
  -- Only this handler's durable pre-dispatch phase proves that an error is safe to close.
  local rejectedBeforeDispatch=false
  if not ok and req.cmd=="commit_subvention" and ledger.pending==req.id then
   local p=ledger.pendingWorkflow;local adapter=(state:get() or {}).subventionAdapter or {}
   local op=p and (adapter.operations or {})[p.token]
   if p and p.id==req.id and p.read=="get_subvention_operation" and op and op.phase=="prepared"
    and not (adapter.submitted or {})[tostring(op.uid)] then
    op.phase="rejected_before_dispatch";op.error=tostring(value):sub(1,2048)
    local updated=state:get() or {};updated.subventionAdapter=adapter;state:set(updated)
    ledger.pending=nil;ledger.pendingWorkflow=nil;rejectedBeforeDispatch=true
   end
  end
  ledger.requests[req.id]={status=ok and "returned" or "error",cmd=req.cmd,ok=ok,error=not ok and tostring(value):sub(1,2048) or nil}
  if rejectedBeforeDispatch then
   local record=ledger.requests[req.id];record.status="reconciled_rejected";record.mutationAttempted=false;record.retryAllowed=false
   record.rejectionEvidenceSource="durable_engine_pre_dispatch_phase"
  end
  root=state:get() or {};root.uiConstruction=ledger;state:set(root)
  emit(req,ok,value)
 end
end

-- Bounded, read-only ingress experiment. This does not dispatch commands. The
-- installed native base/init.lua calls resolveutil.loadfile(resolved) and then
-- chunk(); its require cache is separate. Whether loadfile sees changed disk
-- bytes must be verified live before using this as a request transport.
-- Disabled after build 40420 returned the initial marker for all 120 reads,
-- despite an atomic on-disk replacement. This is not a usable live inbox.
local ENABLE_RESOURCE_INGRESS_PROBE = false
local ingressProbe = {last=nil, started=nil, value=nil, stopped=false, reads=0}
local function probeResourceIngress()
	if ingressProbe.stopped or type(resolveutil) ~= "table" or type(resolveutil.loadfile) ~= "function" then return end
	local now = wallClock()
	if not now then ingressProbe.stopped=true;return end
	if ingressProbe.last and now-ingressProbe.last < 1 then return end
	ingressProbe.started=ingressProbe.started or now
	ingressProbe.last=now
	if now-ingressProbe.started > 120 then
		ingressProbe.stopped=true
		log("[TNJ_INGRESS_PROBE_V1]", json.encode({status="ended",reads=ingressProbe.reads,session=terrainEpoch}))
		return
	end
	local ok,value=pcall(function()
		local chunk,why=resolveutil.loadfile("tnj_tf3_ai_bridge::/tf3_mcp_bridge/ingress_probe.lua")
		assert(type(chunk)=="function",tostring(why))
		local v=chunk()
		assert(type(v)=="string" and #v<=64 and v:match("^[a-z0-9_-]+$"),"Invalid ingress probe value")
		return v
	end)
	if not ok then
		ingressProbe.stopped=true
		log("[TNJ_INGRESS_PROBE_V1]",json.encode({status="error",error=tostring(value),session=terrainEpoch}))
		return
	end
	ingressProbe.reads=ingressProbe.reads+1
	if value~=ingressProbe.value then
		ingressProbe.value=value
		log("[TNJ_INGRESS_PROBE_V1]",json.encode({status="observed",value=value,reads=ingressProbe.reads,session=terrainEpoch}))
	end
end

-- Separate first-read experiment: each path is read exactly once. Kept off in
-- release builds. A host watcher replaces a marker AFTER the ready log and
-- BEFORE its first read; this distinguishes native bytecode cache from VFS data.
local ENABLE_FIRST_READ_PROBE = false
local firstReadProbe = {slot=1, due=nil, stopped=false}
local function probeFirstReadIngress()
	if firstReadProbe.stopped then return end
	local now=wallClock()
	if not now or type(resolveutil)~="table" or type(resolveutil.loadfile)~="function" then
		firstReadProbe.stopped=true
		log("[TNJ_FIRST_READ_V1]",json.encode({status="error",error="loader or clock unavailable",session=terrainEpoch}))
		return
	end
	local slot=firstReadProbe.slot
	if not firstReadProbe.due then
		firstReadProbe.due=now+30
		log("[TNJ_FIRST_READ_V1]",json.encode({status="ready",slot=slot,session=terrainEpoch}))
		return
	end
	if now<firstReadProbe.due then return end
	-- A delayed tick must not consume a marker long after the observer timed out.
	if now>firstReadProbe.due+30 then
		firstReadProbe.stopped=true
		log("[TNJ_FIRST_READ_V1]",json.encode({status="error",error="read window expired",slot=slot,session=terrainEpoch}))
		return
	end
	local ok,value=pcall(function()
		local path="tnj_tf3_ai_bridge::/tf3_mcp_bridge/ingress_first_read_v1_"..slot..".lua"
		local chunk,why=resolveutil.loadfile(path)
		assert(type(chunk)=="function",tostring(why))
		local v=chunk()
		assert(type(v)=="string" and #v<=64 and v:match("^[a-z0-9_-]+$"),"Invalid marker")
		return v
	end)
	log("[TNJ_FIRST_READ_V1]",json.encode({status=ok and "observed" or "error",slot=slot,value=tostring(value),session=terrainEpoch}))
	if not ok or slot==2 then firstReadProbe.stopped=true;return end
	firstReadProbe.slot=slot+1
	firstReadProbe.due=nil
end

-- Opt-in bounded transport: installer provides a unique generation of indexed
-- resource slots. Every slot is read once, including empty ones. Never recycle
-- cached filenames or automatically dispatch after a session reload.
local HEADLESS_GENERATION = "disabled"
local HEADLESS_ON_DEMAND = false
local HEADLESS_USERDATA = false
-- Same command-specific limit in the ingress and the construction dispatcher.
function uiBuild.inputLimit(text)
	return type(text)=="string" and (text:match("^[0-9a-f]+ preview_line_edit ") or text:match("^[0-9a-f]+ preview_road_graph ")) and 8192 or 512
end
local headless = {slot=1,due=nil,stopped=false,seen={},order={},saveIds={},saveCount=0}
function headless.canSave()
	-- Native bindings can be callable tables with a hidden metatable.
	return type(app)=="table" and (type(app.saveGame)=="function" or type(app.saveGame)=="table")
end
function headless.canLoad()
	return type(app)=="table" and isCallable(app.loadGame) and isCallable(app.findAllSavegames)
		and isCallable(app.setWaitForStartReadyGame) and type(app.SaveGameNamespace)=="table"
		and isCallable(app.SaveGameNamespace.getSavegame) and api.type.SavegameId~=nil
end
-- Same native entry and identifier construction as gui/menu/savegame_react_util.tl.
-- Acknowledgement precedes the destructive state transition and is NOT completion.
function headless.load(input)
	local id,cmd,raw=input:match("^([0-9a-f]+) ([a-z_]+) (.+)$")
	assert(id and #id==32 and cmd=="load_game" and raw:match("^%s*{"),"Invalid load request")
	local args=json.decode(raw)
	assert(type(args)=="table","Invalid load arguments")
	for k in pairs(args)do assert(k=="slot" or k=="backup_save","Unknown load argument")end
	for _,key in ipairs({"slot","backup_save"})do
		local slot=args[key]
		assert(type(slot)=="string" and #slot>=1 and #slot<=80 and slot:match("^[A-Za-z0-9][A-Za-z0-9_%-]*$"),"Invalid load slot")
		local lower=slot:lower()
		assert(not ({con=true,prn=true,aux=true,nul=true})[lower] and not lower:match("^com%d$") and not lower:match("^lpt%d$"),"Reserved load slot")
	end
	assert(args.slot~=args.backup_save,"Load target must differ from backup")
	assert(headless.canLoad(),"Native load API unavailable")
	local current=commands.get_game_state({});assert(current.speedup==0,"Pause before loading")
	local namespace=app.SaveGameNamespace.getSavegame()
	local selected,count=nil,0
	for _,info in pairs(app.findAllSavegames(namespace))do
		if info.saveName==args.slot then selected=info;count=count+1 end
	end
	assert(count==1 and selected.size>0,"Load target missing, empty or ambiguous")
	local saveId=api.type.SavegameId.new()
	saveId.path=selected.path;saveId.saveGameName=selected.saveName;saveId.saveGameNamespace=namespace
	headless.stopped=true -- Never process another command in the departing session, even on error.
	local encoded=json.encode({id=id,cmd=cmd,ok=true,result={requested=true,verified=false,
		slot=args.slot,session=terrainEpoch,verification="new_session_and_readback_required"}})
	local payload=hexEncode(encoded);local total=math.max(1,math.ceil(#payload/1500))
	for part=1,total do print("[TNJ_UI_READ_V1] id="..id.." part="..part.." total="..total.." hex="..payload:sub((part-1)*1500+1,part*1500))end
	app.setWaitForStartReadyGame()
	app.loadGame(saveId,false,nil)
	return "Result logged"
end
-- Saving runs in the application/GUI state without a visible panel or engine event.
-- Keep the callback empty; the host verifies that the .sav was actually written.
function headless.save(input)
	local id,cmd,raw=input:match("^([0-9a-f]+) ([a-z_]+) (.+)$")
	assert(id and #id==32 and cmd=="save_game","Invalid save request")
	assert(raw:match("^%s*{"),"Save arguments must be an object")
	local args=json.decode(raw)
	assert(type(args)=="table","Invalid save arguments")
	for k,v in pairs(args) do
		assert(k=="slot" or (k=="overwrite" and type(v)=="boolean"),"Unknown save argument")
	end
	local slot=args.slot
	assert(type(slot)=="string" and #slot>=1 and #slot<=80 and slot:match("^[A-Za-z0-9][A-Za-z0-9_%-]*$"),"Invalid save slot")
	local lower=slot:lower()
	assert(not ({con=true,prn=true,aux=true,nul=true})[lower] and not lower:match("^com%d$") and not lower:match("^lpt%d$"),"Reserved save slot")
	assert(not headless.saveIds[id] and headless.saveCount<256,"Save request duplicate or limit reached")
	assert(headless.canSave(),"Native save API unavailable")
	local current=commands.get_game_state({})
	assert(current.speedup==0,"Pause the game before saving")
	headless.saveIds[id]=true;headless.saveCount=headless.saveCount+1
	app.saveGame(slot,function() end,false,true)
	local encoded=json.encode({id=id,cmd=cmd,ok=true,result={requested=true,verified=false,
		slot=slot,session=terrainEpoch,gameTime=current.gameTime,player=current.player,world=current.world,verification="host_file_check_required"}})
	local payload=hexEncode(encoded)
	local total=math.max(1,math.ceil(#payload/1500))
	for part=1,total do
		print("[TNJ_UI_READ_V1] id="..id.." part="..part.." total="..total.." hex="..payload:sub((part-1)*1500+1,part*1500))
	end
	return "Result logged"
end
local function headlessTick()
	if HEADLESS_GENERATION=="disabled" or headless.stopped then return end
	local function emit(status,extra)
		local row=extra or {};row.status=status;row.session=terrainEpoch
		row.generation=HEADLESS_GENERATION;row.slot=headless.slot
		row.mode=HEADLESS_USERDATA and "userdata" or (HEADLESS_ON_DEMAND and "demand" or "bounded")
		if HEADLESS_USERDATA then
			row.userdataVersion=1;row.userdataDirectory="mod_presets"
			row.filename="tnj_mcp_"..HEADLESS_GENERATION.."_request.preset.lua"
		end
		row.saveGameAvailable=headless.canSave()
		row.loadGameVersion=1;row.loadGameAvailable=headless.canLoad()
		row.saveApiType=type(app)=="table" and type(app.saveGame) or "nil"
		row.saveRequestCount=headless.saveCount;row.saveRequestLimit=256
		row.operationQuotaVersion=1
		row.depotRemovalVersion=1
		row.waterFacilityVersion=1
		row.waterHarborLayoutVersion=1
		row.industryBonusesVersion=1
		row.townCargoSupplyVersion=2
		row.townPassengerSupplyVersion=1
		row.assignmentReconciliationVersion=1
		row.notificationsVersion=1
		row.waterFacilityFingerprintVersion=2
		row.inputLimits={default=512,preview_line_edit=8192,preview_road_graph=8192};row.roadGraphVersion=40
		if HEADLESS_ON_DEMAND and not HEADLESS_USERDATA then row.filename="s"..terrainEpoch:gsub("[^a-zA-Z0-9]","_").."_"..headless.slot..".lua" end
		row.utc=os.time();row.clock=wallClock()
		log("[TNJ_HEADLESS_V1]",json.encode(row))
	end
	local now=wallClock()
	if not now or (not HEADLESS_USERDATA and (type(resolveutil)~="table" or type(resolveutil.loadfile)~="function")) then
		headless.stopped=true;emit("stopped",{error="loader or clock unavailable"});return
	end
	if not headless.due then headless.due=now+2;emit("ready",{due=headless.due});return end
	if now<headless.due then return end
	if not HEADLESS_ON_DEMAND and now>headless.due+5 then headless.stopped=true;emit("stopped",{error="late update; no replay"});return end
	local consumed=false
	local ok,err=pcall(function()
		local value
		local mailbox="tnj_mcp_"..HEADLESS_GENERATION.."_request.preset"
		if HEADLESS_USERDATA then
			local found=false
			local names=app.getAllUserdata("mod_presets")
			assert(type(names)=="table","Userdata directory enumeration failed")
			for _,name in pairs(names) do if name==mailbox or name==mailbox..".lua" then found=true end end
			if not found then return end
			local data=app.loadUserdata("mod_presets",mailbox)
			assert(type(data)=="table" and type(data.hex)=="string" and #data.hex<=32768,"Invalid userdata envelope")
			value=hexDecode(data.hex)
		else
		local filename=HEADLESS_ON_DEMAND and ("s"..terrainEpoch:gsub("[^a-zA-Z0-9]","_").."_"..headless.slot..".lua") or (headless.slot..".lua")
		local chunk,why=resolveutil.loadfile("tnj_tf3_ai_bridge::/tf3_mcp_bridge/headless/"..HEADLESS_GENERATION.."/"..filename)
		if HEADLESS_ON_DEMAND and chunk==nil and type(why)=="string" and why:find("Could not find file",1,true) then return end
		assert(type(chunk)=="function",tostring(why))
		value=chunk()
		end
		if not HEADLESS_ON_DEMAND and value=="" then return end
		assert(type(value)=="string" and #value<=16384,"Invalid headless payload")
		local req=json.decode(value)
		-- Stale persisted mail must never execute in a new session or twice.
		-- The host keeps the original durable intent; no automatic replay occurs.
		if HEADLESS_USERDATA and type(req)=="table" and req.generation==HEADLESS_GENERATION
			and (req.session~=terrainEpoch or (type(req.slot)=="number" and req.slot<headless.slot)) then return end
		assert(type(req)=="table" and req.session==terrainEpoch and req.generation==HEADLESS_GENERATION and req.slot==headless.slot,"Headless session/slot mismatch")
		assert(type(req.expires)=="number" and now<=req.expires and req.expires<=headless.due+(HEADLESS_ON_DEMAND and 60 or 5),"Expired headless request")
		assert(type(req.input)=="string","Invalid request input")
		local id,cmd=req.input:match("^([0-9a-f]+) ([a-z_]+)")
		assert(id and #id==32 and not headless.seen[id],"Duplicate or invalid request ID")
		headless.seen[id]=true -- reserve before invoking either existing dispatcher
		headless.order[#headless.order+1]=id
		if #headless.order>256 then headless.seen[table.remove(headless.order,1)]=nil end
		consumed=true
		if #req.input>uiBuild.inputLimit(req.input) then
			-- Identity/envelope validated, but no dispatcher has been called.
			-- Consume this slot and return a real rejection; never replay it.
			emit("rejected",{id=id,command=cmd,reason="input_too_large",inputBytes=#req.input,inputLimit=uiBuild.inputLimit(req.input),dispatchAttempted=false})
			return
		end
		emit("consumed",{id=id})
		if HEADLESS_USERDATA then app.removeUserdata("mod_presets",mailbox) end
		local status
		if req.kind=="build" then
			assert(uiBuild.recognizes(req.input),"Unsupported construction command")
			status=uiBuild.forward(req.input,HEADLESS_ON_DEMAND)
		elseif req.kind=="read" then status=handleUiRead(req.input,HEADLESS_ON_DEMAND)
		elseif req.kind=="save" then status=headless.save(req.input)
		elseif req.kind=="load" then status=headless.load(req.input)
		else error("Unsupported request kind") end
		emit("dispatched",{id=id,detail=status})
		assert(status=="Submitted; inspect log" or status=="Result logged","Dispatch failed or unknown: "..tostring(status))
	end)
	if not ok then headless.stopped=true;emit("stopped",{error=tostring(err)});return end
	if headless.stopped then return end
	if not HEADLESS_ON_DEMAND and headless.slot>=1024 then headless.stopped=true;emit("exhausted");return end
	-- Never catch up missed frames or perform multiple reads on one update.
	if not HEADLESS_ON_DEMAND or consumed then headless.slot=headless.slot+1 end
	headless.due=now+(HEADLESS_ON_DEMAND and 1 or 2);emit("ready",{due=headless.due})
end

local bridgeScript = {
	update = function(_userParams, state, dt)
		if state ~= nil then
			local saved = state:get() or {}
			-- GUI events share the game-script subscription filter. Migrate saves
			-- that already subscribed only to the original file-channel event.
			if not state:hasEventSubscriptions() or saved.bridgeSubscriptionsVersion ~= 2 then
				state:subscribeToEvent(ENGINE_EVENT)
				state:subscribeToEvent("tnj_bridge_readonly.request")
				state:subscribeToEvent("tnj_bridge_build.request")
				saved.bridgeSubscriptionsVersion = 2
				state:set(saved)
			end
		end
		bridgeTick(dt, "engine", state)
	end,

	handleEvent = function(_userParams, state, _src, id, name, param)
		if id == "tnj_bridge_build" and name == "tnj_bridge_build.request" then
			uiBuild.engine(state,param);return
		end
		if id == ENGINE_EVENT_ID and name == ENGINE_EVENT then
			local ok, err = pcall(handleEngineEvent, state, param)
			if not ok then log("engine request failed:", err) end
		end
	end,

	guiUpdate = function(_userParams, state, _guiState)
		if not HEADLESS_USERDATA then bridgeTick(nil, "gui", state) end
		if ENABLE_RESOURCE_INGRESS_PROBE then probeResourceIngress() end
		if ENABLE_FIRST_READ_PROBE then probeFirstReadIngress() end
		headlessTick()
	end,

	guiHandleEvent = function(_userParams, _state, _guiState, _src, _id, _name, _param)
		if _id == "tnj_bridge_readonly" and _name == "tnj_bridge_readonly.request" then
			if uiBuild.recognizes(_param) then return uiBuild.forward(_param) end
			return handleUiRead(_param)
		end
	end,
}

-- One engine read collects the whole planning corridor, including model-only depots.
commands.get_route_snapshot = function(args)
 local CT=api.type.ComponentType
 local spacing=roadNumber(args.spacing or 100,'spacing',25,args.survey_bounds and 2000 or 250)
 local function revision(id) local r=api.engine.getRevision(id);return table.concat({r.num[1],r.num[2],r.num[3]},':') end
 local margin=roadNumber(args.margin or 1500,'margin',250,4000)
 local stations,ignore={},{}
 if args.survey_bounds then
  local b=args.survey_bounds
  stations={{position={x=b.min.x,y=b.min.y},ports={}},{position={x=b.max.x,y=b.max.y},ports={}}}
 elseif args.start_node and args.end_node then
  for _,n in ipairs({args.start_node,args.end_node}) do
   local links=api.engine.system.streetSystem.getNodeSegments(n)
   if #links<1 then error('road endpoint has no segments',0) end
   local e=api.engine.getComponent(links[1],CT.BASE_EDGE)
   if e.roadType~=api.type.enum.RoadType.STREET then error('endpoint must be a street',0) end
   local p=api.engine.getComponent(n,CT.BASE_NODE).position
   local t=e.node1==n and e.tangent1 or e.tangent0;local sign=e.node1==n and 1 or -1
   local d=math.sqrt(t.x*t.x+t.y*t.y);ignore[links[1]]=true
   stations[#stations+1]={position={x=p.x,y=p.y,z=p.z},ports=#links==1 and {{node=n,position={x=p.x,y=p.y,z=p.z},direction={x=t.x/d*sign,y=t.y/d*sign}}} or {}}
  end
 else
 for _,id in ipairs({args.start_construction,args.end_construction}) do
  local c=api.engine.getComponent(id,CT.CONSTRUCTION)
  if not c then error('station construction does not exist: '..tostring(id),0) end
  local frozen,ports={},{}
  ignore[id]=true
  for _,n in ipairs(c.frozenNodes) do frozen[n]=true end
  for _,s in ipairs(c.stations) do ignore[s]=true end
  for _,eid in ipairs(c.frozenEdges) do
   ignore[eid]=true
   local e=api.engine.getComponent(eid,CT.BASE_EDGE)
   if e.roadType==api.type.enum.RoadType.TRACK then
    for _,n in ipairs({e.node0,e.node1}) do
     if not frozen[n] and #api.engine.system.streetSystem.getNodeSegments(n)==1 then
      local p=api.engine.getComponent(n,CT.BASE_NODE).position
      local t=e.node1==n and e.tangent1 or e.tangent0
      local sign=e.node1==n and 1 or -1
      local d=math.sqrt(t.x*t.x+t.y*t.y)
      ports[#ports+1]={node=n,edge=eid,position={x=p.x,y=p.y,z=p.z},direction={x=sign*t.x/d,y=sign*t.y/d}}
     end
    end
   end
  end
  stations[#stations+1]={construction=id,position=constructionPosition(id),ports=ports}
 end
 end
 local a,b=stations[1].position,stations[2].position
 local bounds=api.engine.terrain.getBoundingBox()
 local x0=math.max(bounds.min.x,math.floor((math.min(a.x,b.x)-margin)/spacing)*spacing)
 local y0=math.max(bounds.min.y,math.floor((math.min(a.y,b.y)-margin)/spacing)*spacing)
 if args.whole_map then x0=bounds.min.x;y0=bounds.min.y;margin=math.max(bounds.max.x-bounds.min.x,bounds.max.y-bounds.min.y)*2 end
 if args.survey_bounds then x0=a.x;y0=a.y;margin=0 end
 local nx=math.floor((math.min(bounds.max.x,math.max(a.x,b.x)+margin)-x0)/spacing)+1
 local ny=math.floor((math.min(bounds.max.y,math.max(a.y,b.y)+margin)-y0)/spacing)+1
 if nx*ny>100000 then error('corridor exceeds 100000 terrain samples; increase spacing or reduce margin',0) end
 local grid={x=x0,y=y0,nx=nx,ny=ny,spacing=spacing,heights={},water={}}
 local terrainRevisions={}
 for id,r in pairs(api.engine.terrain.getTerrainEntityRevisions()) do terrainRevisions[tostring(id)]=table.concat({r.num[1],r.num[2],r.num[3]},':') end
 local domain=table.concat({x0,y0,nx,ny,spacing},':')
 local same=args.domain==domain and args.terrain_revisions~=nil
 if same then
  for id,r in pairs(terrainRevisions) do if args.terrain_revisions[id]~=r then same=false;break end end
  for id in pairs(args.terrain_revisions) do if not terrainRevisions[id] then same=false;break end end
 end
 if not same then
 for j=0,ny-1 do for i=0,nx-1 do
  local p=api.type.Vec2f.new(x0+i*spacing,y0+j*spacing)
  grid.heights[#grid.heights+1]=api.engine.terrain.getHeightAt(p)
  grid.water[#grid.water+1]=api.engine.terrain.isOnWater(p)
 end end
 else grid=nil end
 local cx,cy=x0+(nx-1)*spacing/2,y0+(ny-1)*spacing/2
 local radius=math.sqrt(((nx-1)*spacing)^2+((ny-1)*spacing)^2)/2+spacing
 local obstacles,seen,revisions={},{},{}
 for _,kind in ipairs({'BASE_EDGE','TOWN_BUILDING','STATION','VEHICLE_DEPOT','CONSTRUCTION','MODEL_INSTANCE_LIST'}) do
  for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(cx,cy),radius,CT[kind])) do
   if not seen[id] and not ignore[id] then
    seen[id]=true
    local rev=revision(id);revisions[tostring(id)]=rev
    if not args.revisions or args.domain~=domain or args.revisions[tostring(id)]~=rev then
    local bv=api.engine.getComponent(id,CT.BOUNDING_VOLUME)
    if bv then
     local lo,hi=bv.bbox.min,bv.bbox.max
     local vegetation=false
     local ml=api.engine.getComponent(id,CT.MODEL_INSTANCE_LIST)
     if kind=='MODEL_INSTANCE_LIST' and ml then
      vegetation=true
      for _,list in ipairs({ml.fatInstances,ml.thinInstances}) do for _,m in ipairs(list) do
       local name=api.res.modelRep.getName(m.modelId)
       if not name:find('/tree') and not name:find('/rock') and not name:find('/bush') then vegetation=false end
      end end
     end
     if not vegetation and hi.x>=x0 and hi.y>=y0 and lo.x<=x0+(nx-1)*spacing and lo.y<=y0+(ny-1)*spacing then
      local tb=api.engine.getComponent(id,CT.TOWN_BUILDING)
      local row={entity=id,kind=kind,town=tb and tb.town or nil,min={x=lo.x,y=lo.y,z=lo.z},max={x=hi.x,y=hi.y,z=hi.z}}
      if kind=='BASE_EDGE' then
       local e=api.engine.getComponent(id,CT.BASE_EDGE)
       row.node0=e.node0;row.node1=e.node1;row.roadType=e.roadType;row.roadTemplate=e.roadTemplate
       row.position0={x=e.position0.x,y=e.position0.y,z=e.position0.z};row.position1={x=e.position1.x,y=e.position1.y,z=e.position1.z}
       row.tangent0={x=e.tangent0.x,y=e.tangent0.y,z=e.tangent0.z};row.tangent1={x=e.tangent1.x,y=e.tangent1.y,z=e.tangent1.z}
      end
      obstacles[#obstacles+1]=row
     end
    end
    end
   end
  end
 end
 return {schema=2,domain=domain,revisions=revisions,terrainRevisions=terrainRevisions,delta=args.domain==domain and args.revisions~=nil,state=commands.get_game_state({}),stations=stations,grid=grid,obstacles=obstacles,
  consistency='single engine read; revalidate before construction',coverage='bounding boxes and sampled terrain; native preview required'}
end
ENGINE_COMMANDS.get_route_snapshot=true

-- Read-only survey independent of existing stations; no entity exclusions or delta reuse.
commands.get_planning_snapshot = function(args)
 local map=commands.get_map_info()
 local bounds=args.bounds or map.bounds
 for _,axis in ipairs({'x','y'}) do
  local lo=roadNumber(bounds.min[axis],'bounds.min.'..axis,map.bounds.min[axis],map.bounds.max[axis])
  local hi=roadNumber(bounds.max[axis],'bounds.max.'..axis,map.bounds.min[axis],map.bounds.max[axis])
  if hi<=lo then error('survey bounds must have positive area',0) end
 end
 local spacing=roadNumber(args.spacing or 250,'spacing',25,2000)
 if bounds.max.x-bounds.min.x<spacing or bounds.max.y-bounds.min.y<spacing then error('bounds must span at least one grid cell',0) end
 local result=commands.get_route_snapshot({survey_bounds=bounds,spacing=spacing})
 result.bridgeVersion=BRIDGE_VERSION
 result.map=map;result.bounds=bounds;result.scope=args.bounds and 'local' or 'global'
 result.stations=nil
 result.coverage='sampled terrain and available bounding volumes; missing bounds and unreadable geometry remain unknown'
 return result
end
ENGINE_COMMANDS.get_planning_snapshot=true

-- BEGIN TERRAIN FLATTEN ADAPTER
-- Kept as a source fragment for atomic installation into bridge.script.lua.
do
 local tickets,operations={},{}
 local serial=0
 local pending=nil
 local checkpoint=function()end
 -- Engine script modules may be reconstructed between events. Persist only plain
 -- data in the game-owned script state, never globals; GUI epoch invalidates tokens
 -- after reload. Keep unresolved operations across epochs for reconciliation.
 terrainStateBind=function(state,epoch)
  assert(type(epoch)=='string','terrain GUI session epoch required')
  local root=state:get() or {}
  local saved=root.terrainAdapter or {}
  tickets=saved.epoch==epoch and (saved.tickets or {}) or {}
  operations=saved.operations or {};serial=saved.serial or 0;pending=saved.pending
  checkpoint=function()
   local current=state:get() or {}
   current.terrainAdapter={epoch=epoch,tickets=tickets,operations=operations,serial=serial,pending=pending}
   state:set(current)
  end
  checkpoint()
 end
 local function signature(v)
  if type(v)~='table' then return tostring(v) end
  local keys={};for k in pairs(v)do keys[#keys+1]=k end
  table.sort(keys,function(a,b)return tostring(a)<tostring(b)end)
  local out={};for _,k in ipairs(keys)do out[#out+1]=tostring(k)..'='..signature(v[k])end
  return '{'..table.concat(out,',')..'}'
 end
 local function identity()
  local s=commands.get_game_state({})
  return {world=s.world,player=s.player,gameTime=s.gameTime,tickCount=s.tickCount}
 end
 local function sameSession(a,b)
  return a.world==b.world and a.player==b.player and b.gameTime>=a.gameTime and b.tickCount>=a.tickCount
 end
 local function capabilities()
  return {operation='flatten_rectangle',native_calibrated=true,
   native_preview_supported=false,commit_available=true,transition_supported=true,max_native_steps=256,
   reason='Rectangle and bounded smooth transition; native Proposal preview binding unavailable',
   native_api='Proposal.terrain.baseHeightMod',max_vertices=20000,
   verification='survey only; no native proposal sent'}
 end
 local function survey(args)
  assert(type(args.bounds)=='table' and type(args.bounds.min)=='table' and type(args.bounds.max)=='table','bounds.min/max required')
  local b={min={},max={}}
  for _,a in ipairs({'x','y'})do
   b.min[a]=roadNumber(args.bounds.min[a],'bounds.min.'..a)
   b.max[a]=roadNumber(args.bounds.max[a],'bounds.max.'..a)
   assert(b.max[a]>b.min[a] and b.max[a]-b.min[a]<=600,'flatten extent must be positive and <=600m per axis')
  end
  local z=roadNumber(args.target_height,'target_height')
  local width=roadNumber(args.transition_width or 0,'transition_width',0,128)
  local margin=16
  local grade=roadNumber(args.max_edge_grade or 0.10,'max_edge_grade',0.01,0.20)
  local limit=roadNumber(args.max_height_change or 10,'max_height_change',0.05,50)
  local res=api.engine.terrain.getBaseResolution()
  local sx,sy=roadNumber(res.x,'resolution.x',0.1,25),roadNumber(res.y,'resolution.y',0.1,25)
  local quantum=roadNumber(res.z,'resolution.z',0.001,1)
  local t=assert(getComponent(api.engine.util.getWorld(),'TERRAIN'),'terrain unavailable')
  assert(z>roadNumber(t.waterLevel,'water level')+1,'target must remain above water level + 1m')
  local flattened={min={x=math.floor(b.min.x/sx)*sx,y=math.floor(b.min.y/sy)*sy},
                   max={x=math.ceil(b.max.x/sx)*sx,y=math.ceil(b.max.y/sy)*sy}}
  assert(width==0 or width>=2*math.max(sx,sy),'transition width must span at least two base-grid cells')
  local modified={min={x=flattened.min.x-math.ceil(width/sx)*sx,y=flattened.min.y-math.ceil(width/sy)*sy},
                  max={x=flattened.max.x+math.ceil(width/sx)*sx,y=flattened.max.y+math.ceil(width/sy)*sy}}
  local area={min={x=modified.min.x-math.ceil(margin/sx)*sx,y=modified.min.y-math.ceil(margin/sy)*sy},
              max={x=modified.max.x+math.ceil(margin/sx)*sx,y=modified.max.y+math.ceil(margin/sy)*sy}}
  local map=api.engine.terrain.getBoundingBox()
  for _,a in ipairs({'x','y'})do assert(area.min[a]>=map.min[a] and area.max[a]<=map.max[a],'guard area outside map')end
  local nx=math.floor((area.max.x-area.min.x)/sx+.5)+1
  local ny=math.floor((area.max.y-area.min.y)/sy+.5)+1
  assert(nx*ny<=20000,'terrain vertex budget exceeded; reduce area')
  local cx,cy=(area.min.x+area.max.x)/2,(area.min.y+area.max.y)/2
  local radius=math.sqrt((area.max.x-area.min.x)^2+(area.max.y-area.min.y)^2)/2
  local obstacles,seen={},{}
  for _,kind in ipairs({'BASE_EDGE','BASE_NODE','TOWN_BUILDING','CONSTRUCTION','MODEL_INSTANCE_LIST'})do
   local ct=assert(api.type.ComponentType[kind],'missing component type: '..kind)
   for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(V2(cx,cy),radius,ct))do
    if not seen[id]then
     seen[id]=true
     local bv=getComponent(id,'BOUNDING_VOLUME')
     if not bv then obstacles[#obstacles+1]={entity=id,kind=kind,reason='unknown_bounds'}
     elseif bv.bbox.max.x>=area.min.x and bv.bbox.min.x<=area.max.x and bv.bbox.max.y>=area.min.y and bv.bbox.min.y<=area.max.y then
      obstacles[#obstacles+1]={entity=id,kind=kind,reason='inside_affected_area'}
     end
    end
   end
  end
  local points,blocked={},{}
  if #obstacles>0 then blocked[#blocked+1]='existing_entities_in_affected_area'end
  local cut,fill,maxChange,changed=0,0,0,0
  for j=0,ny-1 do for i=0,nx-1 do
   local x,y=area.min.x+i*sx,area.min.y+j*sy
   local v=V2(x,y);local h=roadNumber(api.engine.terrain.getBaseHeightAt(v),'base height')
   local surface=roadNumber(api.engine.terrain.getHeightAt(v),'surface height')
   local inside=x>=flattened.min.x and x<=flattened.max.x and y>=flattened.min.y and y<=flattened.max.y
   local dx=math.max(flattened.min.x-x,0,x-flattened.max.x)
   local dy=math.max(flattened.min.y-y,0,y-flattened.max.y)
   local distance=math.sqrt(dx*dx+dy*dy)
   local transition=not inside and width>0 and distance<width
   local expected=inside and z or h
   if transition then
    local t=distance/width;local weight=1-t*t*(3-2*t)
    expected=h+(z-h)*weight
    expected=math.floor(expected/quantum+.5)*quantum
   end
   local delta=expected-h
   if api.engine.terrain.isOnWater(v)~=false then blocked[#blocked+1]='water_or_unknown';break end
   if math.abs(surface-h)>0.25 then blocked[#blocked+1]='surface_base_difference_requires_review';break end
   if math.abs(delta)>limit then blocked[#blocked+1]='height_change_limit';break end
   if expected<=t.waterLevel+1 then blocked[#blocked+1]='water_clearance';break end
   points[#points+1]={x=x,y=y,before=h,surface_before=surface,expected=expected,inside=inside,transition=transition}
   if math.abs(delta)>quantum/2 then changed=changed+1 end
   maxChange=math.max(maxChange,math.abs(delta))
   cut=cut+math.max(0,-delta)*sx*sy;fill=fill+math.max(0,delta)*sx*sy
  end;if #blocked>0 and #points<nx*(j+1) then break end end
  local edgeGrade=0
  if #points==nx*ny then
   for j=0,ny-1 do for i=0,nx-1 do
    local a=points[j*nx+i+1]
    for _,step in ipairs({{1,sx,i+1<nx},{nx,sy,j+1<ny}})do
     if step[3]then local q=points[j*nx+i+1+step[1]]
      if a.inside~=q.inside or a.transition or q.transition then edgeGrade=math.max(edgeGrade,math.abs(a.expected-q.expected)/step[2])end
     end
    end
   end end
   if width>0 then
    for j=0,ny-2 do for i=0,nx-2 do
     local a,b,c,d=points[j*nx+i+1],points[j*nx+i+2],points[(j+1)*nx+i+1],points[(j+1)*nx+i+2]
     if a.transition or b.transition or c.transition or d.transition then
      local gx=math.max(math.abs(b.expected-a.expected),math.abs(d.expected-c.expected))/sx
      local gy=math.max(math.abs(c.expected-a.expected),math.abs(d.expected-b.expected))/sy
      edgeGrade=math.max(edgeGrade,math.sqrt(gx*gx+gy*gy))
     end
    end end
   end
   if edgeGrade>grade then blocked[#blocked+1]='edge_grade_requires_separate_transition_design'end
  end
  local patches={{bounds=flattened,height=z}}
  -- No mutable native grid accessor: a disjoint constant-height run per row.
  local last=nil
  for _,p in ipairs(points)do
   if p.transition and math.abs(p.expected-p.before)>quantum/2 then
    if last and last.height==p.expected and last.bounds.max.y==p.y and last.bounds.max.x+sx==p.x then
     last.bounds.max.x=p.x
    else
     last={bounds={min={x=p.x,y=p.y},max={x=p.x,y=p.y}},height=p.expected}
     patches[#patches+1]=last
    end
   else last=nil end
  end
  if #patches>256 then blocked[#blocked+1]='native_step_budget_exceeded_reduce_area_or_transition'end
  local revisions={}
  for id,r in pairs(api.engine.terrain.getTerrainEntityRevisions())do revisions[tostring(id)]={r.num[1],r.num[2],r.num[3]}end
  return {args={bounds=b,target_height=z,max_edge_grade=grade,max_height_change=limit,transition_width=width},area=area,flattened=flattened,modified=modified,patches=patches,
   resolution={x=sx,y=sy,z=quantum},nx=nx,ny=ny,points=points,blocked=blocked,obstacles=obstacles,
   revisions=signature(revisions),session=identity(),changed=changed,
   summary={native_steps=#patches,max_edge_grade=edgeGrade,vertices=nx*ny,changed_vertices=changed,max_height_change=maxChange,
    estimated_cut_m3=cut,estimated_fill_m3=fill,volume_basis='base-grid vertex estimate; not native cost'}}
 end
 commands.get_terrain_operation_capabilities=function()return capabilities()end
 commands.preview_flatten_terrain=function(args)
  local s=survey(args);local c=capabilities()
  local result={preview=true,bounds=s.args.bounds,affected_bounds=s.area,target_height=s.args.target_height,
   flattened_bounds=s.flattened,modified_bounds=s.modified,transition_width=s.args.transition_width,summary=s.summary,obstacles=s.obstacles,blockers=s.blocked,
   blocked=#s.blocked>0,validation='structural_only',native_preview=false,
   transition_supported=true,warning='Smoothstep transition uses bounded sequential native steps; partial failure stops without retry',
   commit_available=c.commit_available,capability=c,requires_post_operation_survey=true}
  if #s.blocked>0 or not c.commit_available or s.changed==0 then return result end
  for k,t in pairs(tickets)do if wallClock()-t.created>60 then tickets[k]=nil end end
  serial=serial+1;local token='terrain:'..tostring(wallClock())..':'..serial
  tickets[token]={survey=s,created=wallClock()};checkpoint();result.preview_token=token;result.expires_in_seconds=60
  return result
 end
 local function readback(op)
  local current=identity()
  if not sameSession(op.session,current)then
   return {operation_id=op.id,status='needs_reconciliation',verified=false,reason='session changed; inspect saved receipt',receipt=op.receipt}
  end
  local mismatches,maxError=0,0
  for _,p in ipairs(op.points)do
   local h=api.engine.terrain.getBaseHeightAt(V2(p.x,p.y))
   local err=math.abs(h-p.expected);maxError=math.max(maxError,err)
   if err>op.tolerance then mismatches=mismatches+1 end
  end
  local verified=op.callback==true and op.success==true and not op.error and mismatches==0 and (not op.total_steps or op.completed_steps==op.total_steps)
  if verified and pending==op.id then pending=nil;checkpoint() end
  return {operation_id=op.id,status=verified and 'verified' or 'needs_reconciliation',verified=verified,
   submitted=true,completed_steps=op.completed_steps,total_steps=op.total_steps,callback_received=op.callback,native_success=op.success,error=op.error,
   mismatched_vertices=mismatches,max_error_m=maxError,receipt=op.receipt,
   requires_fresh_snapshot=true,requires_fresh_facility_and_road_preview=true}
 end
 commands.commit_flatten_terrain=function(args)
  local token=args.preview_token;local ticket=tickets[token];tickets[token]=nil;checkpoint()
  assert(ticket,'unknown, consumed or reloaded terrain preview token')
  assert(not pending,'previous terrain operation needs reconciliation; do not resubmit')
  assert(wallClock()-ticket.created<=60,'terrain preview expired')
  assert(type(args.backup_save)=='string' and args.backup_save:match('^[%w_-]+$'),'backup_save slot required')
  local s=ticket.survey;assert(sameSession(s.session,identity()),'session changed')
  local fresh=survey(s.args)
  assert(#fresh.blocked==0,'terrain/obstacles changed or blocked; preview again')
  assert(s.revisions==fresh.revisions and signature(s.points)==signature(fresh.points),'terrain changed; preview again')
  local rx,ry=s.resolution.x,s.resolution.y
  local op={id=token,session=identity(),points=s.points,tolerance=s.resolution.z+0.025,
   callback=false,completed_steps=0,total_steps=#s.patches}
  op.receipt={operation_id=token,session=op.session,args=s.args,flattened_bounds=s.flattened,
   modified_bounds=s.modified,guard_bounds=s.area,patches=s.patches,
   backup_save=args.backup_save,expected_points=s.points,tolerance_m=op.tolerance}
  operations[token]=op;pending=token;checkpoint()
  for index,patch in ipairs(s.patches)do
   local f=patch.bounds
   local proposal=api.type.Proposal.new()
   proposal.terrain.baseHeightMod=api.type.GridVec2f.new(math.floor(f.min.x/rx+.5),math.floor(f.min.y/ry+.5),
    math.floor((f.max.x-f.min.x)/rx+.5)+1,math.floor((f.max.y-f.min.y)/ry+.5)+1,V2(patch.height,patch.height))
   op.callback=false;op.success=false;op.attempted_step=index;checkpoint()
   local ok,err=pcall(function()
    api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal,nil,false,true),function(_,success)
     op.callback=true;op.success=success==true
    end)
   end)
   if not ok then op.error=tostring(err)end
   if not op.callback or not op.success then op.error=op.error or 'native step not confirmed'end
   if not op.error then
    for y=f.min.y,f.max.y,ry do for x=f.min.x,f.max.x,rx do
     local h=api.engine.terrain.getBaseHeightAt(V2(x,y))
     if type(h)~='number' or h~=h or math.abs(h-patch.height)>op.tolerance then op.error='native step readback mismatch'end
    end end
   end
   if op.error then checkpoint();break end
   op.completed_steps=index;checkpoint()
  end
  return readback(op)
 end
 commands.get_terrain_operation=function(args)
  local op=operations[args.operation_id]
  assert(op,'unknown operation; reconcile from saved receipt and terrain survey, never resubmit')
  return readback(op)
 end
 for _,name in ipairs({'get_terrain_operation_capabilities','preview_flatten_terrain','commit_flatten_terrain','get_terrain_operation'})do ENGINE_COMMANDS[name]=true end
end
-- END TERRAIN FLATTEN ADAPTER

-- exposed for offline tests
bridgeScript._internal = { prepareHeadquarters = prepareHeadquarters, previewReputation = previewReputation, json = json, commands = commands, toPlain = toPlain, finishRoadConnections = finishRoadConnections }

-- The game loads ".script.lua" files by calling the global data() and resolving
-- "@update" / "@handleEvent" inside the returned table. Returning the same table
-- every time keeps the module-level state above alive across calls.
function data()
	return bridgeScript
end

return bridgeScript
