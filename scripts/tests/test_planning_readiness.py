import copy,json
import pytest
from planning_pipeline_core import TEMPLATE_DIR,load_templates,prepare_template
from planning_readiness import check
def test_missing_templates_fail_before_children(tmp_path,monkeypatch):
    import plan_pipeline
    monkeypatch.setattr(plan_pipeline.subprocess,'run',lambda *a,**k:pytest.fail('Should fail before child stages'))
    out=tmp_path/'out'
    with pytest.raises(ValueError,match='Cannot read city'):
        plan_pipeline.run(tmp_path/'snapshot',tmp_path/'details',tmp_path/'capacity',out,city_template=tmp_path/'missing',production_template=TEMPLATE_DIR/'production.json')
    assert json.loads((out/'failure.json').read_text('utf8'))['stages']==[]
def test_unknown_port_and_inconsistent_geometry_rejected():
    t=load_templates(TEMPLATE_DIR/'city.json',TEMPLATE_DIR/'production.json')['city']
    bad=copy.deepcopy(t);bad['rolePortNodes']['truck']=['missing']
    with pytest.raises(ValueError,match='Unbound'):prepare_template(bad,'city')
    bad=copy.deepcopy(t);bad['roads'][1]['position0']['x']+=1
    with pytest.raises(ValueError,match='inconsistent'):prepare_template(bad,'city')
def test_missing_execution_dependency_is_readiness_failure(tmp_path,monkeypatch):
    import planning_readiness
    monkeypatch.setattr(planning_readiness,'ROOT',tmp_path)
    with pytest.raises(FileNotFoundError):check()
