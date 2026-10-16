import asyncio
import base64
import json
import io

from PIL import Image
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from test_development_planner import snapshot, site
from tf3_mcp.development_planner import plan_global, plan_local, save_json
from tf3_mcp.planning_app import ReportLinks, RESOURCE_URI
from tf3_mcp.planning_report import report_bounds


def test_local_card_crops_global_snapshot():
    s=snapshot()
    assert report_bounds(plan_global(s,1))['max']['x']==1000
    b=report_bounds(plan_local(s,[site()]))
    assert b==dict(min=dict(x=350,y=350),max=dict(x=650,y=650))


def test_html_links_only_serve_registered_report(tmp_path):
    path=tmp_path/'plan.html';path.write_text('<h1>report</h1>')
    links=ReportLinks()
    try:
        url=links.register(path)
        assert urlopen(url).read()==b'<h1>report</h1>'
        with pytest.raises(HTTPError) as e:urlopen(url+'/../../secret')
        assert e.value.code==404
        with pytest.raises(HTTPError) as e:urlopen(Request(url,headers={'Host':'evil.example'}))
        assert e.value.code==403
    finally:links.close()


@pytest.mark.parametrize('apps_enabled',[False,True])
def test_actual_mcp_card_resource_and_result(tmp_path,apps_enabled):
    path=save_json(snapshot(),tmp_path,'snapshot')
    async def run():
        params=StdioServerParameters(command=sys.executable,args=['-m','tf3_mcp.server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            extensions={'io.modelcontextprotocol/ui':{'mimeTypes':['text/html;profile=mcp-app']}} if apps_enabled else None
            async with ClientSession(read,write,extensions=extensions) as session:
                init=await session.initialize()
                # The installed SDK's legacy stdio handshake omits extensions on 2025-11-25.
                # Resource/tool metadata remains available to both UI and text-only clients.
                assert init.server_info.name=='tf3'
                definitions={t.name:t for t in (await session.list_tools()).tools}
                for name in ('plan_global_development','plan_local_development','plan_rail_connection','find_facility_sites'):
                    assert not (definitions[name].meta or {}).get('ui')
                assert definitions['export_planning_report'].meta['ui']['resourceUri']==RESOURCE_URI
                resource=(await session.read_resource(RESOURCE_URI)).contents[0]
                assert resource.mime_type=='text/html;profile=mcp-app'
                assert 'ui/notifications/tool-result' in resource.text
                assert resource.meta['ui']['csp']['connectDomains']==[]
                r=await session.call_tool('plan_local_development',dict(snapshot_path=path,output_dir=str(tmp_path),sites=[site()]))
                assert not r.is_error
                assert r.structured_content['scope']=='local'
                assert not (r.meta or {}).get('planningCard')
                assert not list(tmp_path.glob('report-*'))
                svg = tmp_path/'existing.svg'
                original = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 950"><text x="10" y="30">原图</text></svg>'.encode('utf-8')
                svg.write_bytes(original)
                r=await session.call_tool('export_planning_report',dict(svg_path=str(svg),output_dir=str(tmp_path)))
                assert not r.is_error
                card=r.meta['planningCard']
                assert card['language'] in ('en', 'zh-CN')
                image_data=base64.b64decode(card['image'].split(',',1)[1])
                assert card['image'].startswith('data:image/svg+xml;base64,')
                assert image_data == original
                assert Path(r.structured_content['files']['svg']).read_bytes() == original
                assert (card['width'],card['height'])==(1000,950)
                assert card['imageFit']=='contain'
                assert r.structured_content['redrawn'] is False
                assert 'png' not in r.structured_content['files']
                assert 'base64' not in r.content[0].text
                assert 'do not automatically open' in r.structured_content['display']
                body=await asyncio.to_thread(lambda:urlopen(card['htmlUrl']).read())
                assert b'data:image/svg+xml;base64,' in body
    asyncio.run(run())


def test_export_svg_never_invokes_renderer(tmp_path, monkeypatch):
    from tf3_mcp import server, planning_report
    def forbidden(*args, **kwargs):
        raise AssertionError('Existing SVG must never be redrawn')
    monkeypatch.setattr(planning_report, 'export_report', forbidden)
    svg = tmp_path/'original.svg'
    raw = b'\xef\xbb\xbf<svg xmlns="http://www.w3.org/2000/svg" width="300px" height="200"><!-- preserve --></svg>'
    svg.write_bytes(raw)
    result = asyncio.run(server.export_planning_report(str(svg), str(tmp_path), title='<original>'))
    assert base64.b64decode(result.meta['planningCard']['image'].split(',',1)[1]) == raw
    assert '&lt;original&gt;' in Path(result.structured_content['files']['html']).read_text()
    assert (result.meta['planningCard']['width'],result.meta['planningCard']['height']) == (300,200)


@pytest.mark.parametrize('name,contents',[
    ('plan.json','{}'),
    ('bad.svg','<svg>'),
    ('bad.svg','<html/>'),
    ('bad.svg','<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>'),
    ('bad.svg','<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 -1 0"/>'),
])
def test_invalid_svg_is_not_exported(tmp_path, name, contents):
    from tf3_mcp.planning_app import export_svg_card
    import xml.etree.ElementTree as ET
    source=tmp_path/name;source.write_text(contents)
    with pytest.raises((ValueError, ET.ParseError)):
        export_svg_card(source,tmp_path)
    assert not list(tmp_path.glob('report-*'))
