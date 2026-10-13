"""Runs the real bridge.script.lua inside lupa against a mocked game API, and talks to it
through the real file transport. Verifies JSON, the request/response protocol and commands
without starting the game."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

try:
    import lupa.lua52 as lupa_mod  # match the older Lua used by the game where possible
except ImportError:  # pragma: no cover
    import lupa as lupa_mod

from tf3_mcp.bridge import Bridge, BridgeError

MOCK_CONSTRUCTION = Path(__file__).resolve().parent / "mock_construction.lua"
SCRIPT = Path(__file__).resolve().parents[2] / "mod" / "tf3_mcp_bridge" / "content" / "tf3_mcp_bridge" / "bridge.script.lua"

MOCK_API = r"""
local CT = { NAME = 1, TOWN = 2, LINE = 3, GAME_TIME = 4, GAME_SPEED = 5, ACCOUNT = 6,
  STATION_GROUP = 7, VEHICLE_DEPOT = 8, TRANSPORT_VEHICLE = 9, PLAYER_OWNED = 10, CONSTRUCTION = 11 }
local Carrier = { ROAD = 0, RAIL = 1, TRAM = 2 }
local VState = { IN_DEPOT = 0, EN_ROUTE = 1, AT_TERMINAL = 2, GOING_TO_DEPOT = 3 }
local WORLD, PLAYER, AI = 1, 2, 3
local mine = { player = PLAYER }
local function transl(x, y, z) return { getTransl = function(self) return { x = x, y = y, z = z } end } end
components = {
  [WORLD] = { [CT.GAME_TIME] = { gameTime = 123000, timeOfDaySec = 3600, tickCount = 42 },
              [CT.GAME_SPEED] = { speedup = 1, millisPerDay = 2000 } },
  [PLAYER] = { [CT.ACCOUNT] = { balance = 5000000, loan = 0 } },
  [100] = { [CT.TOWN] = {}, [CT.NAME] = { name = "Zürich" } },
  [101] = { [CT.TOWN] = {}, [CT.NAME] = { name = "Bern \"quoted\"" } },
  -- two bus stations (group -> station -> construction) and a road depot
  [200] = { [CT.STATION_GROUP] = { stations = { 210 } }, [CT.NAME] = { name = "Zürich HB" }, [CT.PLAYER_OWNED] = mine },
  [201] = { [CT.STATION_GROUP] = { stations = { 211 } }, [CT.NAME] = { name = "Bern Bf" }, [CT.PLAYER_OWNED] = mine },
  [210] = {}, [211] = {},
  [220] = { [CT.CONSTRUCTION] = { transf = transl(10, 20, 5) } },
  [221] = { [CT.CONSTRUCTION] = { transf = transl(900, 40, 7) } },
  -- like the real game: depots have no carrier field, only the transport modes they serve
  [300] = { [CT.VEHICLE_DEPOT] = { transportModes = { [0] = false, [3] = true, [4] = true } }, [CT.PLAYER_OWNED] = mine },
  [320] = { [CT.CONSTRUCTION] = { transf = transl(15, 25, 5) } },
  -- a line owned by an AI player must be hidden by default
  [400] = { [CT.LINE] = { stops = {} }, [CT.NAME] = { name = "AI line" }, [CT.PLAYER_OWNED] = { player = AI } },
}
local nextEntity = 1000
local stationToCon = { [210] = 220, [211] = 221 }
local models = {
  ["vehicle/bus/old_bus.mdl"] = { id = 50, metadata = {
    description = { name = "Old Bus" }, availability = { yearFrom = 1830, yearTo = 1900 }, cost = { price = 40000 },
    landVehicle = { topSpeed = 12 },
    transportVehicle = { carrier = Carrier.ROAD, compartments = { { loadConfigs = { { cargoEntry = { capacity = 20 } } } } } } } },
  ["vehicle/bus/future_bus.mdl"] = { id = 51, metadata = {
    description = { name = "Future Bus" }, availability = { yearFrom = 2000, yearTo = 0 }, cost = { price = 90000 },
    transportVehicle = { carrier = Carrier.ROAD, compartments = {} } } },
  ["vehicle/train/steam.mdl"] = { id = 52, metadata = {
    description = { name = "Steam" }, availability = { yearFrom = 1840, yearTo = 0 }, cost = { price = 200000 },
    transportVehicle = { carrier = Carrier.RAIL, compartments = {} } } },
}
local modelsById = {}
for name, m in pairs(models) do m.name = name; modelsById[m.id] = m end
local function new(t) return function() return t and t() or {} end end
sentCommands = {}
api = {
  type = {
    ComponentType = CT,
    enum = { Carrier = Carrier, TransportVehicleState = VState,
             TransportMode = { PERSON = 0, CARGO = 1, CAR = 2, BUS = 3, TRUCK = 4, TRAM = 5, TRAIN = 7 } },
    Vec3f = { new = function(x, y, z) return { x = x, y = y, z = z } end },
    Line = { new = new(), Stop = { new = new() } },
    TransportVehiclePart = { new = function() return { part = {} } end },
    LoadConfig = { new = new() },
    TransportVehicleConfig = { new = new() },
  },
  res = { modelRep = {
    find = function(n) return models[n] and models[n].id or -1 end,
    get = function(id) return modelsById[id] end,
    getName = function(id) return modelsById[id].name end,
    forEachModelWithMetadata = function(key, fn)
      local names = {}
      for n, m in pairs(models) do if m.metadata[key] then names[#names+1] = n end end
      table.sort(names)
      for _, n in ipairs(names) do fn(n) end
    end,
  } },
  engine = {
    system = {
      lineSystem = {
        getLines = function()
          local out = {}
          for e, c in pairs(components) do if c[CT.LINE] then out[#out+1] = e end end
          table.sort(out)
          return out
        end,
        getLinesForPlayer = function(p)
          local out = {}
          for e, c in pairs(components) do
            if c[CT.LINE] and c[CT.PLAYER_OWNED] and c[CT.PLAYER_OWNED].player == p then out[#out+1] = e end
          end
          table.sort(out)
          return out
        end,
      },
      streetConnectorSystem = {
        getConstructionEntityForStation = function(s) return stationToCon[s] or -1 end,
        getConstructionEntityForDepot = function(d) return d == 300 and 320 or -1 end,
      },
      transportVehicleSystem = {
        getLineVehicles = function(line)
          local out = {}
          for e, c in pairs(components) do
            if c[CT.TRANSPORT_VEHICLE] and c[CT.TRANSPORT_VEHICLE].line == line then out[#out+1] = e end
          end
          table.sort(out)
          return out
        end,
        getDepotVehicles = function(depot)
          local out = {}
          for e, c in pairs(components) do
            local tv = c[CT.TRANSPORT_VEHICLE]
            if tv and tv.depot == depot and tv.state == VState.IN_DEPOT then out[#out+1] = e end
          end
          table.sort(out)
          return out
        end,
      },
    },
    getComponent = function(e, ct) return components[e] and components[e][ct] end,
    entityExists = function(e) return components[e] ~= nil end,
    forEachEntityWithComponent = function(fn, ct)
      for _,name in ipairs({'BASE_NODE','BASE_EDGE','MODEL_INSTANCE_LIST','ASSET_GROUP','SIM_CARGO','STOCK_LIST','TERRAIN_TILE_BRUSH','WATER_MESH'}) do
        local unsupported=api.type.ComponentType[name]
        if unsupported~=nil and ct==unsupported then error('Cannot loop over this component type') end
      end
      if ct == CT.LINE then error("Cannot loop over this component type") end
      local ids = {}
      for e, comps in pairs(components) do if comps[ct] then ids[#ids+1] = e end end
      table.sort(ids)
      for _, e in ipairs(ids) do fn(e) end
    end,
    util = {
      getWorld = function() return WORLD end,
      getPlayer = function() return PLAYER end,
      getCalendarDate = function(t) return { year = 1850, month = 1, day = 1 + math.floor(t / 100000) } end,
      finance = { getPlayersBalance = function(p) return components[p][CT.ACCOUNT].balance end },
    },
  },
  cmd = {
    makeGameSetSpeedCmd = function(s) return { kind = "speed", speed = s } end,
    makeLineCreateCmd = function(name, color, player, line)
      return { kind = "lineCreate", name = name, color = color, player = player, line = line }
    end,
    makeLineDestroyCmd = function(line) return { kind = "lineDestroy", line = line } end,
    makeVehicleBuyCmd = function(player, depot, config)
      return { kind = "buy", player = player, depot = depot, config = config }
    end,
    makeVehicleSetLineCmd = function(v, line, stop) return { kind = "setLine", vehicle = v, line = line, stop = stop } end,
    makeVehicleSellCmd = function(ids) return { kind = "sell", ids = ids } end,
    makeVehicleSendToDepotCmd = function(v, sell) return { kind = "toDepot", vehicle = v, sell = sell } end,
    makeVehicleSetStoppedByUserCmd = function(v, stopped) return { kind = "stop", vehicle = v, stopped = stopped } end,
    -- mimics the engine state: callbacks run synchronously; (cmdData, success, results)
    sendCommand = function(cmd, cb)
      sentCommands[#sentCommands+1] = cmd
      local ok, results = true, {}
      if cmd.kind == "speed" then
        ok = cmd.speed ~= 99
        if ok then components[WORLD][CT.GAME_SPEED].speedup = cmd.speed end
      elseif cmd.kind == "lineCreate" then
        nextEntity = nextEntity + 1
        components[nextEntity] = { [CT.LINE] = cmd.line, [CT.NAME] = { name = cmd.name }, [CT.PLAYER_OWNED] = mine }
        results = { { nextEntity, 1 } }
      elseif cmd.kind == "lineDestroy" then
        ok = #api.engine.system.transportVehicleSystem.getLineVehicles(cmd.line) == 0
        if ok then components[cmd.line] = nil end
      elseif cmd.kind == "buy" then
        local price = modelsById[cmd.config.vehicles[1].part.modelId].metadata.cost.price
        local acc = components[PLAYER][CT.ACCOUNT]
        ok = acc.balance >= price
        if ok then
          acc.balance = acc.balance - price
          nextEntity = nextEntity + 1
          components[nextEntity] = { [CT.TRANSPORT_VEHICLE] = { carrier = Carrier.ROAD, state = VState.IN_DEPOT,
            depot = cmd.depot, line = -1, userStopped = false }, [CT.PLAYER_OWNED] = mine }
          cmd.resultVehicleEntity = nextEntity
        end
      elseif cmd.kind == "setLine" then
        local tv = components[cmd.vehicle] and components[cmd.vehicle][CT.TRANSPORT_VEHICLE]
        ok = tv ~= nil and components[cmd.line] ~= nil
        if ok then tv.line = cmd.line; tv.stopIndex = cmd.stop; tv.state = VState.EN_ROUTE end
      elseif cmd.kind == "sell" then
        for _, v in ipairs(cmd.ids) do components[v] = nil end
      elseif cmd.kind == "stop" then
        components[cmd.vehicle][CT.TRANSPORT_VEHICLE].userStopped = cmd.stopped
      end
      if cb then cb(cmd, ok, results) end
    end,
  },
}
debugPrint = function(...) end
"""


# Mimics the game's app.saveUserdata/loadUserdata: tables are stored as
# <userdata>/local/<dir>/<name>.lua containing "function data() return {...} end",
# and loading runs that file's data() in its own environment.
MOCK_USERDATA = r"""
local function serialize(t)
  local keys = {}
  for k in pairs(t) do keys[#keys+1] = k end
  table.sort(keys)
  local out = {"function data()\nreturn {"}
  for _, k in ipairs(keys) do
    local v = t[k]
    out[#out+1] = "\t" .. k .. " = " .. (type(v) == "string" and string.format("%q", v) or tostring(v)) .. ","
  end
  out[#out+1] = "}\nend\n"
  return table.concat(out, "\n")
end
app = {
  saveUserdata = function(dir, name, t) py_write(name, serialize(t)) end,
  loadUserdata = function(dir, name)
    local src = py_read(name)
    if src == nil then error("no such userdata: " .. name) end
    local env = {}
    local chunk = assert(load(src, name, "t", env))
    chunk()
    return env.data()
  end,
  removeUserdata = function(dir, name) py_remove(name) end,
  getAllUserdata = function(dir) return py_list() end,
  getUserDataFolder = function() return "C:/fake/userdata/" end,
}
-- the game binds these as callable tables, not plain functions
local function callable(f) return setmetatable({}, { __call = function(_, ...) return f(...) end }) end
for k, f in pairs(app) do app[k] = callable(f) end
io = nil  -- the game exposes no io library to scripts
"""


class FakeGame:
    """Loads the bridge script and drives it like the game: engine update() calls from a
    worker thread and guiUpdate() calls, with the userdata API backed by `bridge_dir`."""

    def __init__(self, bridge_dir: Path):
        self.dir = bridge_dir
        self.lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK_API)
        g = self.lua.globals()
        g.py_write = self._write
        g.py_read = self._read
        g.py_remove = self._remove
        g.py_list = self._list
        self.lua.execute(MOCK_USERDATA)
        self.lua.execute(MOCK_CONSTRUCTION.read_text(encoding="utf-8"))
        self.script = self.lua.execute(SCRIPT.read_text(encoding="utf-8"))
        g.bridge_script = self.script
        self.state = g.engineState
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.errors: list[BaseException] = []

    def _path(self, name) -> Path:
        return self.dir / f"{name}.lua"

    def _write(self, name, text):
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(name).write_text(text, encoding="utf-8")

    def _read(self, name):
        try:
            return self._path(name).read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError):
            return None

    def _list(self):
        names = sorted(f.stem for f in self.dir.glob("*.lua")) if self.dir.exists() else []
        return self.lua.table_from(names)

    def _remove(self, name):
        self._path(name).unlink(missing_ok=True)

    def _run(self):
        update = self.script["update"]
        gui_update = self.script["guiUpdate"]
        try:
            while not self._stop.is_set():
                update(None, self.state, 0.2)
                gui_update(None, self.state, None)
                time.sleep(0.02)
        except BaseException as e:  # surface Lua errors in the test
            self.errors.append(e)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)
        assert not self.errors, self.errors


@pytest.fixture
def bridge_dir(tmp_path: Path) -> Path:
    return tmp_path / "tf3_mcp"


def run(coro):
    return asyncio.run(coro)


def test_ping_and_heartbeat(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir):
        res = run(b.call("ping", {"echo": "héllo"}))
        assert res["pong"] is True
        assert res["echo"] == "héllo"
        assert res["probe"]["io"] == "nil"
        assert res["probe"]["state"] == "gui"
        assert res["userdataFolder"] == "C:/fake/userdata/"
        deadline = time.time() + 3
        while not b.heartbeat_path.exists() and time.time() < deadline:
            time.sleep(0.05)
        hb = b.heartbeat()
        assert hb["connected"], hb
        assert hb["heartbeat"]["gameTime"] == 123000


def test_game_state_and_towns(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir):
        state = run(b.call("get_game_state"))
        assert state["balance"] == 5000000
        assert state["speedup"] == 1
        assert state["date"] == {"year": 1850, "month": 1, "day": 2}

        towns = run(b.call("list_towns"))
        assert towns["count"] == 2
        assert [t["name"] for t in towns["towns"]] == ["Zürich", 'Bern "quoted"']

        ent = run(b.call("get_entity", {"id": 100}))
        assert ent["name"] == "Zürich"
        assert "TOWN" in ent["components"]


def test_commands_and_errors(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        assert run(b.call("set_game_speed", {"speed": 4})) == {"speedup": 4}
        assert run(b.call("get_game_state"))["speedup"] == 4
        assert len(game.lua.globals().sentCommands) == 1

        with pytest.raises(BridgeError, match="rejected"):
            run(b.call("set_game_speed", {"speed": 99}))
        with pytest.raises(BridgeError, match="unknown command"):
            run(b.call("nope"))
        with pytest.raises(BridgeError, match="does not exist"):
            run(b.call("get_entity", {"id": 999}))


def test_eval(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir):
        assert run(b.call("eval", {"code": "1 + 2"})) == 3
        assert run(b.call("eval", {"code": "local t = {a = 1, b = {2, 3}} return t"})) == {"a": 1, "b": [2, 3]}
        assert run(b.call("eval", {"code": "return 1, 'x'"})) == [1, "x"]
        with pytest.raises(BridgeError, match="runtime error"):
            run(b.call("eval", {"code": "error('boom')"}))
        with pytest.raises(BridgeError, match="compile error"):
            run(b.call("eval", {"code": "this is not lua"}))


def test_timeout_without_game(bridge_dir):
    b = Bridge(bridge_dir, timeout=0.3)
    with pytest.raises(BridgeError, match="no heartbeat"):
        run(b.call("ping"))


def test_json_roundtrip_in_lua():
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    j = script["_internal"]["json"]
    sample = {"s": "a\"b\\c\né中", "n": [1, -2.5, 1e20, 0], "t": True, "f": False, "o": {"k": []}}
    encoded = j["encode"](lua.table_from(json.loads(json.dumps(sample)), recursive=True))
    back = json.loads(encoded)
    assert back["s"] == sample["s"]
    assert back["n"] == [1, -2.5, 1e20, 0]
    assert back["t"] is True and back["f"] is False
    decoded = j["decode"](json.dumps(sample, ensure_ascii=True))
    assert decoded["s"] == sample["s"]
    assert decoded["n"][2] == -2.5  # Lua tables are 1-indexed


class OpaqueGameValue:
    """Attribute-only userdata: like game components, pairs() is unsupported."""

    def __init__(self, **fields):
        self.fields = fields

    def __getitem__(self, key):
        return self.fields[key]


def test_realistic_userdata_serialization():
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    internal = script["_internal"]
    plain = internal["toPlain"]
    encode = internal["json"]["encode"]
    vec2 = OpaqueGameValue(x=12, y=-7)  # accessing z raises, as in the game
    assert json.loads(encode(plain(vec2))) == {"x": 12, "y": -7}
    bounds = OpaqueGameValue(min=vec2, max=OpaqueGameValue(x=20, y=30))
    assert json.loads(encode(plain(bounds)))["max"] == {"x": 20, "y": 30}
    lua.globals().components[100][2] = OpaqueGameValue(developmentActive=False, noise=0)
    result = internal["commands"]["get_entity"](lua.table_from({"id": 100}))
    town = json.loads(encode(result))["components"]["TOWN"]
    assert town["developmentActive"] is False and town["noise"] == 0
    assert "cargoNeeds" in town["_unavailableFields"]
    assert json.loads(encode(plain(OpaqueGameValue(secret=1))))["_unavailable"] == "opaque_userdata"


def test_map_pagination_exceeds_old_cap_and_validates_limits():
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    lua.execute("for id=10000,12004 do components[id] = {[2]={}} end")
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    commands = script["_internal"]["commands"]
    encode = script["_internal"]["json"]["encode"]
    def page(**kwargs):
        return json.loads(encode(commands["list_map_entities"](lua.table_from(kwargs))))
    ids = []
    offset = 0
    while True:
        result = page(kind="TOWN", offset=offset, limit=500)
        assert result["total"] == 2007
        ids.extend(item["id"] for item in result["items"])
        if not result["hasMore"]:
            break
        offset = result["nextOffset"]
    assert len(ids) == len(set(ids)) == 2007
    assert ids == sorted(ids)
    assert page(kind="TOWN", offset=9999)["items"] == []
    for kwargs in ({"limit": 0}, {"limit": 501}, {"offset": -1}, {"offset": 1.5}, {"kind": "INVALID"}):
        with pytest.raises(lupa_mod.LuaError):
            page(**kwargs)


def test_map_roads_use_system_index_and_deduplicate():
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    lua.execute(MOCK_CONSTRUCTION.read_text(encoding="utf-8"))
    lua.execute("""
      api.engine.system.streetSystem.getNode2SegmentMap = function()
        return {[STREET_A]={EDGE_AB}, [STREET_B]={EDGE_AB,EDGE_BC}, [STREET_C]={EDGE_BC}}
      end
      api.engine.forEachEntityWithComponent = function() error('Cannot loop over this component type') end
    """)
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    cmd = script["_internal"]["commands"]["list_map_entities"]
    assert cmd(lua.table_from({"kind": "BASE_NODE"}))["total"] == 3
    assert cmd(lua.table_from({"kind": "BASE_EDGE"}))["total"] == 2
    assert cmd(lua.table_from({"kind": "LINE"}))["total"] == 1


def test_map_info_with_opaque_bounds_and_coordinates():
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    g = lua.globals()
    g.test_bounds = OpaqueGameValue(min=OpaqueGameValue(x=-100, y=-200), max=OpaqueGameValue(x=100, y=200))
    g.test_position = OpaqueGameValue(x=12, y=34)
    lua.execute("""
      api.engine.terrain = {
        getBoundingBox = function() return test_bounds end,
        getBaseResolution = function() return {x=4,y=4,z=0.05} end,
        getHighResolution = function() return {x=1,y=1,z=0.05} end,
        makeMapFromGame = function(heightmap,towns,industries,assets)
          assert(not heightmap and towns and industries and not assets)
          return {numTilesX=0,numTilesY=0,climateId='temperate',
            towns={{existing=100,name='Town',pos=test_position}},
            industries={{existing=200,fileName='farm.con',pos=test_position}}}
        end
      }
    """)
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    result = json.loads(script["_internal"]["json"]["encode"](script["_internal"]["commands"]["get_map_info"]()))
    assert (result["width"], result["height"]) == (200, 400)
    assert result["towns"][0]["position"] == {"x": 12, "y": 34}
    assert result["industries"][0]["fileName"] == "farm.con"


def test_network_queries(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir):
        st = run(b.call("list_stations"))
        assert [s["name"] for s in st["stationGroups"]] == ["Zürich HB", "Bern Bf"]
        assert st["stationGroups"][1]["position"] == {"x": 900, "y": 40, "z": 7}

        depots = run(b.call("list_depots"))["depots"]
        assert depots == [{"id": 300, "construction": 320, "carrier": "ROAD", "transportModes": ["BUS", "TRUCK"],
                           "position": {"x": 15, "y": 25, "z": 5}, "vehiclesInDepot": []}]

        assert run(b.call("list_lines"))["count"] == 0  # the AI line is hidden
        assert run(b.call("list_lines", {"mine_only": False}))["count"] == 1

        models = run(b.call("list_vehicle_models", {"carrier": "road"}))
        assert models["year"] == 1850
        assert [m["model"] for m in models["models"]] == ["vehicle/bus/old_bus.mdl"]
        assert models["models"][0] | {} == {
            "id": 50, "model": "vehicle/bus/old_bus.mdl", "name": "Old Bus", "carrier": "ROAD",
            "yearFrom": 1830, "yearTo": 1900, "price": 40000, "topSpeed": 12, "capacity": 20,
        }
        everything = run(b.call("list_vehicle_models", {"include_unavailable": True}))
        assert everything["count"] == 3


def test_line_and_vehicle_workflow(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("""
            api.type.Line.StopConfig = {new=function()return {} end}
            api.res.cargoTypeRep = {getAll=function()return {[0]="PASSENGERS",[1]="LOGS"}end}
            components[210][api.type.ComponentType.STATION] = {terminals={{passengersLoad=true,cargoLoad=false}}}
            components[211][api.type.ComponentType.STATION] = {terminals={{passengersLoad=true,cargoLoad=false}}}
        """)
        created = run(b.call("create_line", {"station_groups": [200, 201], "name": "Bus 1", "color": [1, 0, 0]}))
        line = created["line"]
        for stop in game.lua.globals().components[created["line"]][3].stops.values():
            assert stop.stopConfig.load[1] is True
            assert stop.stopConfig.load[2] is False
            assert stop.stopConfig.maxLoad[1] == 1
        assert created == {"line": line, "name": "Bus 1", "stops": 2}
        lines = run(b.call("list_lines"))["lines"]
        assert lines[0]["stops"][1]["name"] == "Bern Bf"

        with pytest.raises(BridgeError, match="at least 2"):
            run(b.call("create_line", {"station_groups": [200]}))
        with pytest.raises(BridgeError, match="not a station group"):
            run(b.call("create_line", {"station_groups": [200, 300]}))

        bought = run(b.call("buy_vehicles", {"depot": 300, "model": "vehicle/bus/old_bus.mdl", "count": 3, "line": line}))
        assert len(bought["bought"]) == 3 and bought["failures"] == []
        vehicles = run(b.call("list_vehicles", {"line": line}))["vehicles"]
        assert [v["state"] for v in vehicles] == ["EN_ROUTE"] * 3
        assert run(b.call("get_finances"))["balance"] == 5000000 - 3 * 40000

        # the vehicle config is built like the game's own vehicle store does it
        buy_cmd = next(c for c in game.lua.globals().sentCommands.values() if c.kind == "buy")
        assert buy_cmd.config.vehicles[1].part.modelId == 50
        assert len(buy_cmd.config.vehicles[1].part.compartment2loadConfig) == 1

        with pytest.raises(BridgeError, match="rejected"):
            run(b.call("delete_line", {"line": line}))  # vehicles still assigned

        v0 = bought["bought"][0]
        assert run(b.call("set_vehicle_stopped", {"vehicle": v0}))["stopped"] is True
        assert run(b.call("list_vehicles", {"line": line}))["vehicles"][0]["userStopped"] is True

        assert run(b.call("sell_vehicles", {"vehicles": bought["bought"]}))["sold"] == bought["bought"]
        assert run(b.call("delete_line", {"line": line})) == {"deleted": line}

        with pytest.raises(BridgeError, match="unknown vehicle model"):
            run(b.call("buy_vehicles", {"depot": 300, "model": "nope.mdl"}))
        with pytest.raises(BridgeError, match="is not a VEHICLE_DEPOT"):
            run(b.call("buy_vehicles", {"depot": 200, "model": 50}))


def test_buy_reports_partial_failures(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("components[2][6].balance = 100000")  # enough for 2 old buses
        res = run(b.call("buy_vehicles", {"depot": 300, "model": 50, "count": 3}))
        assert len(res["bought"]) == 2
        assert len(res["failures"]) == 1 and "rejected" in res["failures"][0]


def test_script_defines_global_data_like_the_game_expects():
    # the game calls the global data() of a .script.lua file and resolves "@update" in its result
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    lua.execute(SCRIPT.read_text(encoding="utf-8"))
    script = lua.globals().data()
    assert lua.eval("type")(script["update"]) == "function"
    assert lua.eval("type")(script["handleEvent"]) == "function"


def test_engine_state_never_serves_requests(bridge_dir):
    # engine update() runs in many worker Lua states at once; only guiUpdate may answer
    b = Bridge(bridge_dir, timeout=0.5)
    game = FakeGame(bridge_dir)
    update = game.script["update"]
    from tf3_mcp.bridge import encode_message
    (bridge_dir).mkdir(parents=True, exist_ok=True)
    b.request_path.write_text(encode_message({"id": "x", "cmd": "ping", "args": {}}), encoding="utf-8")
    for _ in range(20):
        update(None, None, 0.2)
    assert not b.response_path.exists()
    assert not b.heartbeat_path.exists()


def test_message_encoding_roundtrip():
    from tf3_mcp.bridge import decode_message, encode_message
    data = {"id": "1", "s": 'quote " backslash \\ newline \n 中文', "n": [1, 2.5]}
    assert decode_message(encode_message(data)) == data
    # tolerate whatever layout the game's serializer uses around the hex field
    hexed = encode_message(data).split('"')[1]
    assert decode_message('function data()\nreturn { hex = "' + hexed + '", }\nend') == data
    assert decode_message("garbage") is None


# --- construction (runs in the engine via the script-event route) ---------------------


def test_engine_routed_eval(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        assert run(b.call("eval", {"code": "1 + 1"}, engine=True)) == 2
        responses = game.state.data["responses"]
        assert len(responses) == 1 and '"result":2' in responses[1]["text"]


def test_build_road_preview_then_build(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        street_c = game.lua.globals().STREET_C
        args = {"start": {"node": street_c}, "end": {"x": 320, "y": 0}}
        preview = run(b.call("build_road", {**args, "preview": True}))
        assert preview["ok"] is True and preview["segments"] == 3 and preview["cost"] == 3000
        assert game.lua.globals().builds == 0  # a preview never builds

        built = run(b.call("build_road", args))
        assert built["built"] is True and len(built["edges"]) == 3 and len(built["nodes"]) == 3
        # edges are looked up from the nodes, and include the one joining the existing start node
        starts = [e for e in built["edges"]
                  if street_c in (game.lua.globals().components[e][102].node0, game.lua.globals().components[e][102].node1)]
        assert len(starts) == 1
        near = run(b.call("find_nearby", {"x": 320, "y": 0, "radius": 5}))
        assert near["nodes"][0]["connections"][0]["direction"] == 180


def test_build_road_reports_collisions(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        r = run(b.call("build_road", {"start": {"x": 50, "y": -40}, "end": {"x": 50, "y": -6}}))
        house = game.lua.globals().HOUSE
        assert r["built"] is False and r["reason"]["blocking"]["townBuildings"] == [house]
        assert game.lua.globals().builds == 0  # refused before sending anything
        r = run(b.call("build_road", {"start": {"x": 50, "y": -40}, "end": {"x": 50, "y": -6},
                                      "allow_collisions": True}))
        assert r["built"] is True


def test_build_depot_faces_and_connects_to_street(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        street_a = game.lua.globals().STREET_A
        r = run(b.call("build_depot", {"x": 0, "y": -60}))
        assert r["built"] is True
        # the entrance is on the depot's local -y side, so facing the street to the north takes 180 degrees
        assert r["rotation"] == 180
        assert r["expectedEntrance"] == {"x": 0, "y": -39.7}
        assert r["connection"]["toNode"] == street_a
        depots = run(b.call("list_depots"))["depots"]
        assert r["depot"] in [d["id"] for d in depots]


@pytest.mark.parametrize("carrier,catenary", [("TRAM", 2), ("ROAD", None)])
def test_depot_catenary_parameters_reach_native_proposal(bridge_dir, carrier, catenary):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        r = run(b.call("build_depot", {"x": 0, "y": -60, "carrier": carrier, "connect": False}))
        assert r["built"] is True
        con = game.lua.globals().components[r["construction"]][game.lua.globals().api.type.ComponentType.CONSTRUCTION]
        assert con.params.tramCatenary == catenary


def test_street_stop_apply_cannot_be_enabled_by_experimental_flag(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        for args in ({"experimental": True},
                     {"experimental": True, "preview": True, "allow_collisions": True}):
            r = run(b.call("build_street_stop", args))
            assert r["code"] == "street_stop_apply_unavailable"
            assert r["built"] is False and r["mutationAttempted"] is False
        assert game.lua.globals().builds == 0


@pytest.mark.parametrize("has_nodes,apply", [(True, False), (False, False), (False, True), (True, True)])
def test_street_stop_preview_remaps_crosswalks_and_lanes(bridge_dir, has_nodes, apply):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.globals().STOP_HAS_NODES = has_nodes
        game.lua.execute("""
            local CT = api.type.ComponentType
            STOP_BUILD_CALLS = 0
            local send = api.cmd.sendCommand
            api.cmd.sendCommand = function(cmd, cb)
                if cmd.kind == "build" then
                    STOP_BUILD_CALLS = STOP_BUILD_CALLS + 1
                    error("native build failed after submission")
                end
                return send(cmd, cb)
            end
            CT.BASE_NODE_CONFIG = 180
            api.type.enum.TransportMode = {BUS=3}
            api.type.enum.EdgeObjectType = {STOP_LEFT=0,STOP_RIGHT=1}
            api.type.LaneConnection = { new = function() return {} end }
            api.type.BaseNodeLaneConnectionAndEntity = { new = function() return {} end }
            for _, n in ipairs({STREET_A, STREET_B}) do
                components[n][180] = {crosswalks={EDGE_AB,EDGE_BC}, laneConnections={
                    {segment0=EDGE_AB, segment1=EDGE_BC,lane0=0,lane1=1,withRoad=true,withTram=false}}}
            end
            api.engine.util.proposal.makeProposalData = function(p)
                local sp = p.streetProposal
                assert(#sp.edgeObjectsToAdd == 2)
                assert(sp.edgeObjectsToAdd[1].left == false and sp.edgeObjectsToAdd[2].left == true)
                assert(sp.edgeObjectsToAdd[1].params.year == 1850)
                assert(sp.edgesToAdd[1].comp.objects[1][1] == -400000000)
                assert(sp.edgesToAdd[1].comp.objects[2][1] == -400000001)
                assert(#p.streetProposal.nodeConfigsToAdd == 2)
                assert(#p.streetProposal.nodeConfigsToRemove == 2)
                for _, c in ipairs(p.streetProposal.nodeConfigsToAdd) do
                    assert(c.comp.crosswalks[1] == -1)
                    assert(c.comp.crosswalks[2] == EDGE_BC)
                    assert(c.comp.laneConnections[1].segment0 == -1)
                    assert(c.comp.laneConnections[1].segment1 == EDGE_BC)
                end
                return {errorState={critical=false,messages={},warnings={}},costs=123,
                        collisionInfo={collisionEntities={}},entity2tn={[-1]={
                            nodes=STOP_HAS_NODES and {{},{},{},{}} or {},
                            edges=STOP_HAS_NODES and {
                                {conns={{entity=-1,index=0},{entity=-1,index=2}},transportModes={[0]=true}},
                                {conns={{entity=-1,index=1},{entity=-1,index=3}},transportModes={[3]=true}}} or {}}}}
            end
        """)
        r = run(b.call("build_street_stop", {"edge": game.lua.globals().EDGE_AB,
                                            "two_sided": True, "preview": not apply}))
        assert r["preview"] is (not apply)
        if apply and has_nodes:
            assert r["code"] == "street_stop_needs_reconciliation"
            assert r["mutationAttempted"] is True and r["built"] is False
            assert game.lua.globals().STOP_BUILD_CALLS == 1
            return
        assert r["ok"] is has_nodes
        assert game.lua.globals().STOP_BUILD_CALLS == 0
        assert r["topology"]["valid"] is has_nodes
        if not has_nodes:
            assert r["code"] == "street_stop_terminal_nodes_missing"
        assert r["cost"] == 123 and r["applySupported"] is True
        assert r["built"] is False and r["mutationAttempted"] is False
        assert r["model"].endswith("small_old_twosided.con")
        assert game.lua.globals().builds == 0



def test_bulldoze_depot(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir):
        depot = run(b.call("build_depot", {"x": 100, "y": -60, "connect": False}))["depot"]
        r = run(b.call("bulldoze", {"entity": depot}))
        assert r["done"] is True and r["removed"].startswith("construction")
        assert run(b.call("list_depots"))["count"] == 1  # only the pre-existing depot remains



def test_build_station_connects_and_bulldoze(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        street_a = game.lua.globals().STREET_A
        preview = run(b.call("build_station", {"x": 0, "y": 40, "preview": True}))
        assert preview["ok"] is True and preview["expectedEntrance"] == {"x": 0, "y": 25}
        assert game.lua.globals().builds == 0

        r = run(b.call("build_station", {"x": 0, "y": 40, "name": "Central", "size": 2}))
        assert r["built"] is True and r["name"] == "Central" and r["kind"] == "passenger"
        assert r["connection"]["toNode"] == street_a
        con = game.lua.globals().components[r["construction"]][11]
        assert len(list(con.params.modules.keys())) == 5  # 2 columns x 2 platforms + entrance/exit

        groups = {s["name"]: s["id"] for s in run(b.call("list_stations"))["stationGroups"]}
        assert groups["Central"] == r["stationGroup"]
        gone = run(b.call("bulldoze", {"entity": r["stationGroup"]}))
        assert gone["done"] is True and gone["removed"].startswith("construction")
        assert "Central" not in [s["name"] for s in run(b.call("list_stations"))["stationGroups"]]


def test_bulldoze_street_segment_uses_official_removal(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        edge = game.lua.globals().EDGE_BC
        r = run(b.call("bulldoze", {"entity": edge}))
        assert r["done"] is True and r["removed"] == f"street segment {edge}"



def test_build_road_between_existing_nodes_reports_edge(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        g = game.lua.globals()
        r = run(b.call("build_road", {"start": {"node": g.STREET_A}, "end": {"x": 100, "y": 80}}))
        top = r["nodes"][-1]
        joined = run(b.call("build_road", {"start": {"node": top}, "end": {"node": g.STREET_C}, "max_segment_length": 200}))
        assert joined["built"] is True and joined["nodes"] == [] and len(joined["edges"]) == 1


@pytest.mark.parametrize("extra, message", [
    ({"snap_radius": -1}, "snap_radius must be between"),
    ({"max_segment_length": 0}, "max_segment_length must be between"),
    ({"via": "bad"}, "via must be an array"),
    ({"preview": "false"}, "preview must be boolean"),
    ({"start": {"x": "nan", "y": 0}}, "start.x must be finite"),
    ({"end": {"x": 100000, "y": 50}}, "exceeds 512 segments"),
])
def test_road_invalid_requests_never_build(bridge_dir, extra, message):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        with pytest.raises(BridgeError, match=message):
            run(b.call("build_road", {"start": {"x": 0, "y": 50}, "end": {"x": 100, "y": 50}, **extra}))
        assert game.lua.globals().builds == 0


def test_road_snap_excludes_tracks_and_respects_height(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("components[EDGE_AB][102].roadType = 0")
        args = {"start": {"x": 1, "y": 0}, "end": {"x": 1, "y": 50}, "preview": True}
        r = run(b.call("build_road", args))
        assert r["points"][0]["snapped"] is False
        with pytest.raises(BridgeError, match="is not a street node"):
            run(b.call("build_road", {**args, "start": {"node": game.lua.globals().STREET_A}}))
        r = run(b.call("build_road", {**args, "start": {"x": 201, "y": 0}}))
        assert r["points"][0]["snapped"] is True
        assert r["points"][0]["snapDistance"] == 1
        r = run(b.call("build_road", {**args, "start": {"x": 201, "y": 0, "z": 20}}))
        assert r["points"][0]["snapped"] is False
        assert game.lua.globals().builds == 0


def test_road_preview_elevations_match_built_nodes(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        args = {"start": {"x": 0, "y": 80, "z": 10}, "end": {"x": 100, "y": 80, "z": 20},
                "max_segment_length": 25}
        preview = run(b.call("build_road", {**args, "preview": True}))
        assert preview["buildable"] is True
        assert [p["z"] for p in preview["path"]] == [10, 12.5, 15, 17.5, 20]
        assert game.lua.globals().builds == 0
        built = run(b.call("build_road", args))
        positions = [game.lua.globals().components[n][101].position.z for n in built["nodes"]]
        assert sorted(positions) == [10, 12.5, 15, 17.5, 20]


def test_road_reports_all_via_connections_without_old_edges(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        g = game.lua.globals()
        r = run(b.call("build_road", {"start": {"node": g.STREET_A}, "end": {"node": g.STREET_C},
            "via": [{"x": 50, "y": 80}, {"x": 100, "y": 100}, {"x": 150, "y": 80}],
            "max_segment_length": 200}))
        assert r["built"] is True and len(r["edges"]) == 4
        assert g.EDGE_AB not in r["edges"] and g.EDGE_BC not in r["edges"]


def test_road_build_rejection_has_failure_reason(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("""
            local send = api.cmd.sendCommand
            api.cmd.sendCommand = function(cmd, callback)
                if cmd.kind == 'build' then callback({}, false, {}) else send(cmd, callback) end
            end
        """)
        r = run(b.call("build_road", {"start": {"x": 0, "y": 80}, "end": {"x": 100, "y": 80}}))
        assert r["built"] is False and r["reason"]["ok"] is False
        assert "rejected" in r["reason"]["messages"][0]



def test_road_outside_map_is_rejected_before_build(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("api.engine.terrain.isValidCoordinate = function(p) return p.x < 1000 end")
        with pytest.raises(BridgeError, match="outside the map"):
            run(b.call("build_road", {"start": {"x": 0, "y": 80}, "end": {"x": 1001, "y": 80}}))
        assert game.lua.globals().builds == 0


def test_road_collision_override_cannot_bypass_critical_error(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("""
            local evaluate = api.engine.util.proposal.makeProposalData
            api.engine.util.proposal.makeProposalData = function(p, ctx)
                local data = evaluate(p, ctx)
                data.errorState.critical = true
                data.errorState.messages = {'junction angle too sharp'}
                return data
            end
        """)
        args = {"start": {"x": 0, "y": 80}, "end": {"x": 100, "y": 80}, "allow_collisions": True}
        preview = run(b.call("build_road", {**args, "preview": True}))
        assert preview["buildable"] is False
        result = run(b.call("build_road", args))
        assert result["built"] is False and result["reason"]["critical"] is True
        assert game.lua.globals().builds == 0



def test_upgrade_road_preview_and_apply_preserves_geometry(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        g = game.lua.globals()
        # Use a curved segment so flattening tangents cannot pass unnoticed.
        game.lua.execute("components[EDGE_AB][102].tangent0.y = 17")
        args = {"edge": g.EDGE_AB, "street_type": "town/town_old_medium"}
        preview = run(b.call("upgrade_road", args))
        assert preview["preview"] and preview["validation"] == "structural_only"
        assert preview["costAvailable"] is False and "buildable" not in preview
        assert preview["nodes"] == [g.STREET_A, g.STREET_B]
        assert g.builds == 0
        result = run(b.call("upgrade_road", {**args, "preview": False, "expected_street_type": preview["fromType"]}))
        assert result["applied"] and result["changed"] and result["verified"]
        assert g.components[g.EDGE_AB] is None
        upgraded = g.components[result["edges"][0]][102]
        assert upgraded.node0 == g.STREET_A and upgraded.node1 == g.STREET_B
        assert upgraded.tangent0.y == 17 and upgraded.position0.z == 2
        assert upgraded.roadTemplate.endswith("town_old_medium.street_template")
        assert g.components[g.EDGE_BC] is not None
        again = run(b.call("upgrade_road", {**args, "edge": result["edges"][0], "preview": False}))
        assert again["noChange"] and not again["changed"] and g.builds == 1


@pytest.mark.parametrize("setup, message", [
    ("components[EDGE_AB][102].roadType = 0", "not a street"),
    ("components[EDGE_AB][102].type = 1", "bridge and tunnel"),
    ("components[EDGE_AB][102].objects = {{123, 0}}", "stops or other"),
    ("frozen[EDGE_AB] = 123", "construction-owned"),
])
def test_upgrade_road_unsupported_cases(bridge_dir, setup, message):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute(setup)
        with pytest.raises(BridgeError, match=message):
            run(b.call("upgrade_road", {"edge": game.lua.globals().EDGE_AB,
                "street_type": "town/town_old_medium", "preview": False}))
        assert game.lua.globals().builds == 0


def test_upgrade_road_stale_preview_and_game_rejection(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        g = game.lua.globals()
        args = {"edge": g.EDGE_AB, "street_type": "town/town_old_medium", "preview": False}
        with pytest.raises(BridgeError, match="changed since preview"):
            run(b.call("upgrade_road", {**args, "expected_street_type": "town/town_old_medium"}))
        game.lua.execute("""
            local send = api.cmd.sendCommand
            api.cmd.sendCommand = function(cmd, callback)
                if cmd.kind == 'build' then
                    assert(cmd.ignoreErrors == false)
                    callback({}, false, {})
                else send(cmd, callback) end
            end
        """)
        result = run(b.call("upgrade_road", args))
        assert not result["applied"] and not result["changed"]
        assert g.components[g.EDGE_AB][102].roadTemplate.endswith('town_old_small.street_template')


def test_upgrade_road_refuses_expanded_proposal(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("""
            local replace = api.engine.util.proposal.replaceSegment
            api.engine.util.proposal.replaceSegment = function(e, t)
                local p = replace(e, t)
                p.toRemove = {HOUSE}
                return p
            end
        """)
        with pytest.raises(BridgeError, match="more than the requested road"):
            run(b.call("upgrade_road", {"edge": game.lua.globals().EDGE_AB,
                "street_type": "town/town_old_medium", "preview": False}))
        assert game.lua.globals().builds == 0


def test_cargo_rail_station_preview_build_and_ports(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        args = {"x": 400, "y": 400, "tracks": 2, "length": 160, "rotation": 90, "specialization": "bulk"}
        preview = run(b.call("build_rail_station", args))
        assert preview["preview"] and preview["ok"] and game.lua.globals().builds == 0
        built = run(b.call("build_rail_station", {**args, "preview": False, "name": "Freight"}))
        assert built["built"] and built["verified"] and built["stationGroups"]
        assert built["externalConnectionsBuilt"] is False
        assert len(built["railPorts"]) == 1 and len(built["roadPorts"]) == 1
        assert built["railPorts"][0]["node"] != built["roadPorts"][0]["node"]
        modules = game.lua.globals().components[built["construction"]][11].params.modules
        # Four 40 m modules per column: two platform columns, two track columns, one station building.
        assert len(list(modules.keys())) == 17
        assert modules[6400000].name.endswith('platform_cargo_era_a_bulk.module')
        assert modules[8402000].name.endswith('simple/simple.street_template')
        assert game.lua.globals().builds == 1  # no accidental road connection to a rail port


@pytest.mark.parametrize("extra, message", [
    ({"tracks": 1.5}, "integer"), ({"tracks": 5}, "between"),
    ({"length": 100}, "length must"), ({"specialization": "invalid"}, "specialization"),
    ({"rotation": "nan"}, "finite"), ({"preview": "false"}, "boolean"),
])
def test_cargo_rail_station_invalid_parameters(bridge_dir, extra, message):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        with pytest.raises(BridgeError, match=message):
            run(b.call("build_rail_station", {"x": 400, "y": 400, **extra}))
        assert game.lua.globals().builds == 0


def test_cargo_rail_station_blocks_building_collision(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        r = run(b.call("build_rail_station", {"x": 50, "y": -6, "preview": False}))
        assert not r["built"] and r["reason"]["blocked"]
        assert game.lua.globals().builds == 0


@pytest.mark.parametrize("owner,has_station,preview", [(-1, False, True), (-1, False, False), (5004, False, False), (-1, True, False)])
def test_orphan_stop_cleanup_is_restricted(bridge_dir, owner, has_station, preview):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.globals().ORPHAN_OWNER = owner
        game.lua.globals().ORPHAN_STATION = has_station
        game.lua.execute("""
            local CT=api.type.ComponentType
            components[9001] = {[CT.EDGE_OBJECT]={edgeObjectConstruction="::/stations/street/small_stops/small_mid.con"}}
            if ORPHAN_STATION then components[9001][CT.STATION]={} end
            api.engine.system.streetSystem.getEdgeForEdgeObject = function() return ORPHAN_OWNER end
            api.engine.util.proposal.makeProposalData = function(p)
                assert(p.streetProposal.edgesToRemove == nil)
                assert(#p.streetProposal.edgeObjectsToRemove == 1)
                assert(p.streetProposal.edgeObjectsToRemove[1] == 9001)
                return {errorState={critical=false,messages={},warnings={}},collisionInfo={collisionEntities={}},costs=0}
            end
            local send=api.cmd.sendCommand
            api.cmd.sendCommand=function(cmd, cb)
                if cmd.kind=="build" then
                    builds=builds+1;components[9001]=nil;cb({},true,{})
                else send(cmd,cb) end
            end
        """)
        if owner >= 0 or has_station:
            with pytest.raises(BridgeError, match="cleanup refused"):
                run(b.call("repair_orphan_street_stop", {"entity": 9001,"preview":preview}))
            assert game.lua.globals().builds == 0
        else:
            r = run(b.call("repair_orphan_street_stop", {"entity":9001,"preview":preview}))
            assert r["removed"] is (not preview)
            assert r["mutationAttempted"] is (not preview)
            assert game.lua.globals().builds == int(not preview)


@pytest.mark.parametrize("junction_position", ["start", "via", "end"])
def test_road_junction_guard_rejects_without_submission(bridge_dir, junction_position):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        args = {"start": {"x": 0, "y": 80}, "end": {"x": 200, "y": 80}}
        junction = {"node": game.lua.globals().STREET_B}
        args[junction_position] = [junction] if junction_position == "via" else junction
        preview = run(b.call("build_road", {**args, "preview": True}))
        assert preview["geometryBuildable"] is True
        assert preview["buildable"] is False and preview["commitSupported"] is False
        assert preview["commitBlockedReason"] == "junction_commit_suspended"
        result = run(b.call("build_road", args))
        assert result["built"] is False
        assert result["reason"]["code"] == "junction_commit_suspended"
        assert game.lua.globals().builds == 0
