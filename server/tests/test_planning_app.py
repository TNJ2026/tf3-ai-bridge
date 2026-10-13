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
                r=await session.call_tool('export_planning_report',dict(plan_path=r.structured_content['plan_path'],output_dir=str(tmp_path)))
                assert not r.is_error
                card=r.meta['planningCard']
                assert card['language'] in ('en', 'zh-CN')
                image_data=base64.b64decode(card['image'].split(',',1)[1])
                assert image_data.startswith(b'\x89PNG')
                decoded=Image.open(io.BytesIO(image_data))
                assert decoded.width < 1600 and decoded.height <= 920
                assert decoded.mode=='RGBA'
                assert decoded.getchannel('A').getbbox()==(0,0,*decoded.size)
                assert (card['width'],card['height'])==decoded.size
                assert 'base64' not in r.content[0].text
                assert 'do not automatically open' in r.structured_content['display']
                body=await asyncio.to_thread(lambda:urlopen(card['htmlUrl']).read())
                assert b'<svg' in body
    asyncio.run(run())
