import json
from pathlib import Path

import pytest

from tf3_mcp import localization, bridge
from tf3_mcp.development_planner import plan_local, plan_global
from tf3_mcp.planning_report import export_report
from test_development_planner import snapshot


@pytest.fixture(autouse=True)
def clean_language(monkeypatch):
    for key in ('TF3_UI_LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(localization.locale, 'getlocale', lambda: ('en_US', 'UTF-8'))


def test_language_precedence(monkeypatch):
    assert localization.language() == 'en'
    monkeypatch.setenv('TF3_UI_LANGUAGE', 'zh-CN')
    assert localization.language() == 'zh-CN'
    assert localization.language('en-GB') == 'en'
    monkeypatch.setenv('TF3_UI_LANGUAGE', 'auto')
    monkeypatch.setenv('LC_ALL', 'C.UTF-8')
    assert localization.language() == 'en'
    monkeypatch.setenv('LC_ALL', 'zh_CN.UTF-8')
    assert localization.language() == 'zh-CN'


def test_windows_chinese_locale_and_unavailable_locale(monkeypatch):
    monkeypatch.setattr(localization.locale, 'getlocale', lambda: ('Chinese (Simplified)_China', '936'))
    assert localization.language() == 'zh-CN'
    def unavailable():
        raise ValueError('unknown locale')
    monkeypatch.setattr(localization.locale, 'getlocale', unavailable)
    assert localization.language() == 'en'


@pytest.mark.parametrize('lang,heading,title', [
    ('en', 'Phases and acceptance gates', 'Local layout plan'),
    ('zh-CN', '分期行动与验收条件', '局部布局规划'),
])
def test_report_language_persists_and_preserves_native_names(tmp_path, monkeypatch, lang, heading, title):
    monkeypatch.setenv('TF3_UI_LANGUAGE', lang)
    s = snapshot()
    s['map']['towns'][0]['name'] = 'München 中文 <Town>'
    plan = plan_local(s)
    assert plan['language'] == lang and plan['title'] == title
    global_plan = plan_global(s, 1)
    assert global_plan['title'].startswith('München 中文 <Town>')
    monkeypatch.setenv('TF3_UI_LANGUAGE', 'zh-CN' if lang == 'en' else 'en')
    result = export_report(plan, tmp_path/'Reports with spaces 中文', width=800, height=600)
    text = Path(result['files']['html']).read_text('utf-8')
    assert f'lang="{lang}"' in text and heading in text
    assert 'München 中文 &lt;Town&gt;' in text
    assert result['language'] == lang
    assert json.loads(Path(result['files']['json']).read_text('utf-8')) == plan


def test_invalid_font_falls_back_without_aborting_report(tmp_path, monkeypatch):
    broken = tmp_path/'bad.ttf'
    broken.write_bytes(b'not a font')
    monkeypatch.setenv('TF3_PLANNING_FONT', str(broken))
    result = export_report(plan_local(snapshot()), tmp_path)
    assert any('Could not load font' in w for w in result['warnings'])
    assert Path(result['files']['png']).is_file()


def test_bridge_path_expansion_and_unicode_transport(tmp_path, monkeypatch):
    monkeypatch.setenv('TF3_TEST_ROOT', str(tmp_path))
    monkeypatch.setenv('TF3_MCP_DIR', '$TF3_TEST_ROOT/Steam Library/账户/tf3_mcp')
    assert bridge.default_bridge_dir() == tmp_path/'Steam Library/账户/tf3_mcp'
    payload = {'name': 'München 中文', 'path': 'C:/Steam Library/用户'}
    assert bridge.decode_message(bridge.encode_message(payload)) == payload

@pytest.mark.parametrize('lang,label', [('en', 'Candidate'), ('zh-CN', '候选')])
def test_siting_labels_preserve_requested_name(monkeypatch, lang, label):
    from tf3_mcp.site_planner import search_sites
    from test_site_planner import request
    monkeypatch.setenv('TF3_UI_LANGUAGE', lang)
    plan = search_sites(snapshot(), [request(name='München Depot')])
    assert plan['language'] == lang
    assert plan['sites'][0]['name'] == f'München Depot · {label} 1'
    if lang == 'en':
        assert not any('\u3400' <= c <= '\u9fff' for c in plan['title'] + ''.join(plan['warnings']))


@pytest.mark.parametrize('lang,label', [('en', 'Candidate'), ('zh-CN', '候选')])
def test_rail_plan_localization_with_offline_snapshot(tmp_path, monkeypatch, lang, label):
    import asyncio
    from tf3_mcp import server
    from test_route_planner import snapshot as rail_snapshot
    class Cache:
        async def refresh(self, *args, **kwargs):
            return rail_snapshot(), {'hit': True}
    monkeypatch.setenv('TF3_UI_LANGUAGE', lang)
    monkeypatch.setenv('TF3_MCP_TRANSPORT', 'file')
    monkeypatch.setattr(server, '_map_cache', Cache())
    result = asyncio.run(server.plan_rail_connection(1, 2, output_dir=str(tmp_path)))
    plan = json.loads(Path(result.structured_content['plan_path']).read_text('utf-8'))
    assert plan['language'] == lang
    assert plan['routes'][0]['name'] == f'{label} 1'
    if lang == 'en':
        assert not any('\u3400' <= c <= '\u9fff' for c in json.dumps(plan['phases'], ensure_ascii=False) + plan['title'])


def test_windows_bom_json_inputs(tmp_path, monkeypatch):
    import asyncio
    from tf3_mcp import server
    from tf3_mcp.development_planner import read_snapshot
    path = tmp_path/'München snapshot.json'
    path.write_text(json.dumps(snapshot(), ensure_ascii=False), encoding='utf-8-sig')
    assert read_snapshot(path) == snapshot()
    plan = plan_local(snapshot())
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8-sig')
    async def card(value, *args):
        assert value == plan
        return 'report reached'
    monkeypatch.setattr(server, '_planning_card', card)
    assert asyncio.run(server.export_planning_report(str(path), str(tmp_path))) == 'report reached'
    config = tmp_path/'Recovery config 中文.json'
    config.write_text(json.dumps({'stateDirectory': str(tmp_path/'state')}), encoding='utf-8-sig')
    monkeypatch.setenv('TF3_CONFIG_ROOT', str(tmp_path))
    monkeypatch.setenv('TF3_RECOVERY_CONFIG', '$TF3_CONFIG_ROOT/Recovery config 中文.json')
    assert asyncio.run(server.recovery_control('status'))['monitorEnabled'] is False
