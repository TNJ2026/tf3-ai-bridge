"""Reject the frozen depot endpoint that bypassed native preview diagnostics."""
from pathlib import Path

import pytest
from test_e2e import lupa_mod

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/rail_connection.lua"


@pytest.mark.parametrize("endpoint", ["startNode", "endNode"])
def test_internal_endpoint_rejected_before_native_proposal(endpoint):
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
    PROPOSALS=0;COMMITS=0
    api={type={ComponentType={CONSTRUCTION=1}},engine={}}
    api.engine.forEachEntityWithComponent=function(fn,ct)assert(ct==1);fn(900)end
    api.engine.getComponent=function(id,ct)
      assert(id==900 and ct==1,'must reject before reading endpoint geometry')
      return {frozenNodes={10,11}}
    end
    api.engine.util={proposal={makeProposalData=function()PROPOSALS=PROPOSALS+1 end}}
    api.cmd={sendCommand=function()COMMITS=COMMITS+1 end}
    ''')
    run = lua.execute(SCRIPT.read_text(encoding="utf8"))
    args = {"startNode": 20, "endNode": 21, "apply": True}
    args[endpoint] = 10
    with pytest.raises(Exception, match="construction-internal frozen node"):
        run(lua.table_from(args), lua.table())
    assert lua.globals().PROPOSALS == 0
    assert lua.globals().COMMITS == 0
