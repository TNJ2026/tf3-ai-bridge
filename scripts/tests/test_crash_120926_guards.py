"""Containment guards verified offline; no live reproduction of the crash."""
import asyncio,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import plan_hq_access
from plan_native_preview import NATIVE

def test_hq_probe_is_disabled_before_any_bridge_access(monkeypatch,tmp_path):
    monkeypatch.setattr(sys,'argv',['probe','--plan',str(tmp_path/'absent.json'),'--output',str(tmp_path/'out.json')])
    monkeypatch.setattr(plan_hq_access,'Bridge',lambda:pytest.fail('Must not instantiate or contact bridge'))
    with pytest.raises(RuntimeError,match='Disabled after native access violation'):
        asyncio.run(plan_hq_access.main())

def test_module_preview_does_not_regenerate_template_for_reputation():
    assert 'B.previewReputation(' not in NATIVE
    assert 'getConstructionResult(' not in NATIVE
    assert "reputation={available=false" in NATIVE

def test_fine_survey_decodes_args_and_checks_returned_spacing():
    src=(Path(__file__).resolve().parents[1]/'plan_fresh_survey.py').read_text('utf8')
    assert src.count('get_planning_snapshot(B.json.decode(')==2
    assert "s['grid']['spacing']==25" in src
    assert "s['grid']['spacing']==5" in src
