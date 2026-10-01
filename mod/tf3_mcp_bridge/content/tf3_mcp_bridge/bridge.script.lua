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

local BRIDGE_VERSION = "0.10.0"
local USERDATA_DIR = "tf3_mcp"
local POLL_INTERVAL = 0.1       -- seconds (wall clock) between request polls
local HEARTBEAT_INTERVAL = 1.0  -- seconds (wall clock) between heartbeats
local MAX_LIST = 2000

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

------------------------------------------------------------------------------
-- environment probe
------------------------------------------------------------------------------

local function probeEnv()
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
			"CONSTRUCTION", "PLAYER_OWNED", "ACCOUNT", "VEHICLE_DEPOT", "BASE_NODE", "BASE_EDGE" }
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
local function runRequest(req, respond)
	local handler = commands[req.cmd or ""]
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
local ENGINE_COMMANDS = {}   -- filled by the construction commands below
local pendingEngine = {}     -- request id -> wall clock when forwarded
local ENGINE_TIMEOUT = 25.0

local function forwardToEngine(req)
	local cmd = api.cmd.makeScriptingSendEventCmd("tf3_mcp_bridge", ENGINE_EVENT_ID, ENGINE_EVENT, json.encode(req))
	api.cmd.sendCommand(cmd)
	pendingEngine[req.id] = wallClock() or 0
end

local function handleEngineEvent(state, param)
	local req = json.decode(param or "")
	if type(req) ~= "table" or req.id == nil then return end
	local text = nil
	local replied = runRequest(req, function(ok, payload) text = encodeResponse(req.id, ok, payload) end)
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
local function previewProposal(proposal, ignore)
	local ok, pd = pcall(api.engine.util.proposal.makeProposalData, proposal, nil)
	if not ok then
		return { ok = false, critical = true, messages = { "preview failed: " .. (tostring(pd):match("^[^\n]*") or "") } }
	end
	if pd == nil then
		return { ok = false, critical = true, messages = { "the game could not evaluate this proposal" } }
	end
	local r = {
		critical = tryField(function() return pd.errorState.critical end) or false,
		messages = tryField(function() return toPlain(pd.errorState.messages) end) or {},
		warnings = tryField(function() return toPlain(pd.errorState.warnings) end) or {},
		cost = tryField(function() return pd.costs end),
		collisions = {},
	}
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
	r.ok = not r.critical and not r.blocked
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

local function resolveEndpoint(spec, snapRadius, label)
	if type(spec) ~= "table" then error("'" .. label .. "' must be {node=id} or {x=..., y=...}", 0) end
	if spec.node ~= nil then
		local node = roadNumber(spec.node, label .. ".node", 0, 2147483647)
		if node % 1 ~= 0 or not isStreetNode(node) then error(label .. ": " .. tostring(spec.node) .. " is not a street node", 0) end
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
			if isStreetNode(n) then
				local p = nodePosition(n)
				local d = dist2d(p, { x = x, y = y })
				if z then d = math.sqrt(d * d + (p.z - z) ^ 2) end
				if d <= radius and (bestD == nil or d < bestD or (d == bestD and n < best)) then best, bestD = n, d end
			end
		end
		if best then return { node = best, pos = nodePosition(best), snapped = true, snapDistance = round1(bestD), explicitHeight = z ~= nil } end
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
			for _, e in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(pt.node))) do oldEdges[e] = true end
		end
	end
	local check = previewProposal((makeRoadProposal(points, tplName, tpl, maxLen)), roadIgnoreSet(points))
	outcome.cost = check.cost
	if check.critical or (check.blocked and not allowCollisions) then
		outcome.reason = check
		return outcome
	end
	applyProposal(proposal, true, function(success, res)
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
	local name = resolveStreetTemplate(args.street_type)
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
local function placeConstruction(args, fileName, params, extra)
	local x, y = tonumber(args.x), tonumber(args.y)
	if x == nil or y == nil then error("'x' and 'y' are required", 0) end
	local z = terrainHeight(x, y)
	local angle = resolveFacing(args, x, y)
	local offset = ENTRANCE_OFFSET[fileName]
	local function makeProposal()
		local proposal = api.type.SimpleProposal.new()
		local ce = api.type.SimpleProposal.ConstructionEntity.new()
		ce.fileName = fileName
		ce.transf = transfAt(x, y, z, angle)
		ce.params = params()
		if type(args.name) == "string" then ce.name = args.name end
		ce.playerEntity = api.engine.util.getPlayer()
		proposal.constructionsToAdd = { ce }
		return proposal
	end

	local out = { position = roundPos({ x = x, y = y, z = z }), rotation = round1(math.deg(angle) % 360) }
	if offset then
		out.expectedEntrance = roundPos({ x = x + offset * math.sin(angle), y = y - offset * math.cos(angle) })
	end
	for k, v in pairs(extra or {}) do out[k] = v end

	local check = previewProposal(makeProposal())
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
	applyProposal(makeProposal(), true, function(success) out.built = success end)
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
do
 local tickets, serial = {}, 0
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
     construction_support=kind=="construction" and supported and "clone_existing_layout" or "dedicated_or_unsupported",
     template_script=field(field(d,"createTemplateScript"),"fileName")}
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
 commands.get_facility_config=function(args)
  local out=inspect(args.entity);local types={};for _,s in ipairs(out.slots) do types[s.type]=true end
  out.compatible_modules={}
  for id,name in pairs(api.res.moduleRep.getAll(true)) do
   local d=api.res.moduleRep.get(id)
   if types[d.type] then out.compatible_modules[#out.compatible_modules+1]={resource=name,type=d.type,available=available(d)} end
  end
  table.sort(out.compatible_modules,function(a,b)return a.resource<b.resource end)
  return out
 end
 commands.list_facilities=function(args)
  local rows={};api.engine.forEachEntityWithComponent(function(id)
   local c=getComponent(id,"CONSTRUCTION");local cat,supported=category(c.fileName,lookup("construction",c.fileName))
   if supported and (args.mine_only==false or ownerOf(id)==api.engine.util.getPlayer()) then
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
  return {preview=true,preview_token=token,expires_in_seconds=60,mode=mode,entity=before.entity,
   parameters=toPlain(params),check=check,verification="configuration_only; simulation safety unverified"}
 end
 commands.configure_facility=function(args)
  local before=inspect(args.entity)
  if not before.configurable then error("construction is not an owned configurable facility",0) end
  local p=patch(before,args)
  if canonical(p)==canonical(before.params) then return {preview=true,changed=false} end
  -- Native replacement can remove frozen street edges. Do NOT call makeProposalData on it.
  return issue("configure",before,p,args,{structural_only=true,collision_checked=false,
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
   for _,key in ipairs({"buildingEntities","removableModules","autoRemovalEntity2models"}) do
    for _ in pairs(ci[key] or {}) do check.ok=false;check.blocked=true;check.unexpected_removals=true end
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
 commands.commit_facility=function(args)
  local t=tickets[args.preview_token];tickets[args.preview_token]=nil
  if not t then error("preview expired, already consumed, or bridge reloaded; preview again",0) end
  if wallClock()-t.created>60 or wallClock()<t.created then error("preview expired",0) end
  local gameTime=commands.get_game_state().gameTime
  if currentYear()~=t.year or (t.game_time and gameTime and gameTime<t.game_time) then error("game date/session changed; preview again",0) end
  local before=inspect(t.entity)
  if canonical(before)~=t.snapshot then error("facility changed since preview; inspect and preview again",0) end
  local proposal;local existing={}
  api.engine.forEachEntityWithComponent(function(id)existing[id]=true end,componentTypes().CONSTRUCTION)
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
  if id and (not existing[id] or (t.mode=="configure" and id==t.entity)) then
   local after=inspect(id);out.entity=id;out.config=after
   local matches=true
   for slot,m in pairs(t.params.modules or {}) do
    local got=(after.params.modules or {})[slot]
    if not got or got.name~=m.name or got.variant~=m.variant then matches=false end
   end
   for k,v in pairs(t.params) do if k~="modules" and canonical(after.params[k])~=canonical(v) then matches=false end end
   for slot in pairs(after.params.modules or {}) do if not (t.params.modules or {})[slot] then matches=false end end
   out.verified=matches and math.abs(after.position.x-pos.x)<0.1 and math.abs(after.position.y-pos.y)<0.1 and math.abs(after.position.z-pos.z)<0.1
  end
  out.verification="configuration_only; connectivity and long-term simulation must be checked separately"
  return out
 end
 for _,name in ipairs({"list_facility_resources","list_facilities","get_facility_config","configure_facility","build_facility","commit_facility"}) do ENGINE_COMMANDS[name]=true end
end

-- Native loan workflow: previews are local; only commit_loan dispatches an event.
do
	local previews, operations = {}, {}
	local serial, session = 0, tostring({})
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
		operations[token]=op
		local ok, err = pcall(function()
			api.cmd.sendCommand(cmd,function(_,success) op.callbackAccepted=success end)
		end)
		if not ok then op.dispatchError=tostring(err) end
		return reconcile(op)
	end
	for _, name in ipairs({"get_loans","preview_loan","commit_loan","get_loan_operation"}) do ENGINE_COMMANDS[name]=true end
end

commands.build_depot = function(args)
	local carrier = string.upper(args.carrier or "ROAD")
	local fileName = DEPOT_FILES[carrier]
	if fileName == nil then error("carrier must be one of ROAD, TRAM, RAIL, WATER", 0) end
	local out = placeConstruction(args, fileName, function()
		return { seed = math.random(1, 100000), year = currentYear() or 1900, modules = {} }
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

commands.build_rail_station = function(args)
	local x, y = roadNumber(args.x, "x"), roadNumber(args.y, "y")
	if not api.engine.terrain.isValidCoordinate(V2(x,y)) then error("station is outside the map", 0) end
	local tracks = roadNumber(args.tracks == nil and 2 or args.tracks, "tracks", 1, 4)
	if tracks % 1 ~= 0 then error("tracks must be an integer", 0) end
	local length = roadNumber(args.length == nil and 160 or args.length, "length")
	if not ({[80]=true,[120]=true,[160]=true,[240]=true,[320]=true})[length] then error("length must be 80, 120, 160, 240 or 320 metres", 0) end
	local rotation = roadNumber(args.rotation == nil and 0 or args.rotation, "rotation") % 360
	local specialization = args.specialization or "universal"
	if not ({universal=true,liquid=true,bulk=true,flatbed=true,goods=true})[specialization] then error("invalid cargo specialization", 0) end
	for _,key in ipairs({"preview", "allow_collisions"}) do
		if args[key] ~= nil and type(args[key]) ~= "boolean" then error(key .. " must be boolean", 0) end
	end
	local year = currentYear() or 1900
	-- Do not use connectEntrance: a mixed rail/road construction has multiple entrances.
	local placement = {x=x,y=y,rotation=rotation,connect=false,preview=args.preview ~= false,
		allow_collisions=args.allow_collisions == true,name=args.name}
	local out = placeConstruction(placement, RAIL_STATION, function()
		return {seed=1,year=year,modules=cargoRailModules(tracks,length,specialization,year)}
	end, {carrier="RAIL",kind="cargo",tracks=tracks,length=length,specialization=specialization,
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


------------------------------------------------------------------------------
-- street stops (edge-object constructions placed on a street segment)

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

local bridgeScript = {
	update = function(_userParams, state, dt)
		if state ~= nil and not state:hasEventSubscriptions() then
			state:subscribeToEvent(ENGINE_EVENT)
		end
		bridgeTick(dt, "engine", state)
	end,

	handleEvent = function(_userParams, state, _src, id, name, param)
		if id == ENGINE_EVENT_ID and name == ENGINE_EVENT then
			local ok, err = pcall(handleEngineEvent, state, param)
			if not ok then log("engine request failed:", err) end
		end
	end,

	guiUpdate = function(_userParams, state, _guiState)
		bridgeTick(nil, "gui", state)
	end,

	guiHandleEvent = function(_userParams, _state, _guiState, _src, _id, _name, _param)
	end,
}

-- One engine read collects the whole planning corridor, including model-only depots.
commands.get_route_snapshot = function(args)
 local CT=api.type.ComponentType
 local spacing=roadNumber(args.spacing or 100,'spacing',25,250)
 local function revision(id) local r=api.engine.getRevision(id);return table.concat({r.num[1],r.num[2],r.num[3]},':') end
 local margin=roadNumber(args.margin or 1500,'margin',250,4000)
 local stations,ignore={},{}
 if args.start_node and args.end_node then
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

-- exposed for offline tests
bridgeScript._internal = { json = json, commands = commands, toPlain = toPlain, finishRoadConnections = finishRoadConnections }

-- The game loads ".script.lua" files by calling the global data() and resolving
-- "@update" / "@handleEvent" inside the returned table. Returning the same table
-- every time keeps the module-level state above alive across calls.
function data()
	return bridgeScript
end

return bridgeScript
