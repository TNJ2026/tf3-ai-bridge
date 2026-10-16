"""MCP Apps planning card and explicit-click loopback HTML links."""
from __future__ import annotations

import atexit
import base64
import json
import html
import math
import re
import secrets
import threading
import uuid
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp
from mcp.types import CallToolResult, TextContent

RESOURCE_URI = 'ui://tf3/planning-card.html'
TOOL_META = {'ui': {'resourceUri': RESOURCE_URI}}
apps = Apps()
apps.add_html_resource(RESOURCE_URI, Path(__file__).with_name('planning_card.html').read_text(encoding='utf-8'),
                       title='TF3 Planning', prefers_border=False,
                       csp=ResourceCsp(connect_domains=[], resource_domains=[]))


class ReportLinks:
    """Only registered report bytes are reachable; no arbitrary filesystem serving."""
    def __init__(self):
        self.lock = threading.Lock()
        self.reports = {}
        self.server = None

    def register(self, html_path):
        data = Path(html_path).read_bytes()
        with self.lock:
            if self.server is None:
                owner = self
                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        if self.headers.get('Host') != f'127.0.0.1:{owner.server.server_port}':
                            self.send_error(403);return
                        with owner.lock:
                            body = owner.reports.get(self.path)
                        if body is None:
                            self.send_error(404);return
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html; charset=utf-8')
                        self.send_header('Content-Length', str(len(body)))
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'")
                        self.end_headers()
                        self.wfile.write(body)
                    def log_message(self, *args):
                        pass  # Never write HTTP logs to the MCP stdio channel.
                self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                threading.Thread(target=self.server.serve_forever, daemon=True).start()
            url_path = '/'+secrets.token_urlsafe(24)+'/plan.html'
            self.reports[url_path] = data
            while len(self.reports)>128:
                del self.reports[next(iter(self.reports))]
            return f'http://127.0.0.1:{self.server.server_port}{url_path}'

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


links = ReportLinks()
atexit.register(links.close)


def export_svg_card(svg_path, output_dir, title=None):
    """Package the exact existing SVG as an image; never redraw or rasterize it."""
    source = Path(svg_path).expanduser().resolve()
    if source.suffix.lower() != '.svg':
        raise ValueError('Expected an existing .svg image; pass svg_path. Plan JSON is not rendered.')
    if source.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('SVG exceeds the 8 MiB image limit')
    raw = source.read_bytes()
    text = raw.decode('utf-8-sig')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('SVG must not contain DTD or entity declarations')
    root = ET.fromstring(text)
    if root.tag != '{http://www.w3.org/2000/svg}svg':
        raise ValueError('Expected an SVG root with the SVG namespace')
    def dimension(name):
        match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)(?:px)?\s*', root.get(name, ''))
        return float(match[1]) if match else None
    width, height = dimension('width'), dimension('height')
    if width is None or height is None:
        try:
            _, _, width, height = map(float, re.split(r'[\s,]+', root.get('viewBox', '').strip()))
        except ValueError as exc:
            raise ValueError('SVG needs positive width/height or a valid viewBox') from exc
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError('SVG dimensions must be finite and positive')
    from .localization import language
    title = title or source.stem
    image = 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode('ascii')
    folder = Path(output_dir).expanduser().resolve() / ('report-' + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    svg_file, html_file = folder / source.name, folder / 'index.html'
    svg_file.write_bytes(raw)
    # An image context keeps SVG scripts/foreign content out of the report document.
    html_file.write_text(
        '<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>' + html.escape(title) + '</title><style>body{margin:0;font:16px system-ui}'
        'h1{font-size:18px;padding:12px}img{display:block;max-width:100%;height:auto}</style>'
        '<h1>' + html.escape(title) + '</h1><img alt="' + html.escape(title, quote=True) +
        '" src="' + image + '"></html>', encoding='utf-8')
    result = dict(source_svg=str(source), files={'svg':str(svg_file), 'html':str(html_file)},
                  html_url=links.register(html_file), redrawn=False,
                  display='MCP Apps SVG card; do not automatically open HTML', scope='existing-svg')
    payload = dict(title=title, scope='existing-svg', language=language(), image=image,
                   htmlUrl=result['html_url'], htmlPath=str(html_file), width=width, height=height,
                   imageFit='contain')
    return CallToolResult(content=[TextContent(type='text', text=json.dumps(result, ensure_ascii=False))],
                          structured_content=result, meta={'planningCard':payload})


def card_result(plan, report, summary):
    """Image data stays in UI metadata; text-only clients retain useful paths and findings."""
    png = Path(report.get('cardImage', report['files']['png'])).read_bytes()
    html_url = links.register(report['files']['html'])
    payload = dict(title=plan['title'], scope=plan['scope'], language=report.get('language', plan.get('language')),
                   image='data:image/png;base64,'+base64.b64encode(png).decode('ascii'),
                   htmlUrl=html_url, htmlPath=report['files']['html'],
                   width=report.get('cardWidth', report['width']), height=report.get('cardHeight', report['height']))
    result = dict(summary, files=report['files'], html_url=html_url,
                  display='MCP Apps card; do not automatically open HTML', scope=plan['scope'])
    return CallToolResult(content=[TextContent(type='text',text=json.dumps(result,ensure_ascii=False))],
                          structured_content=result, meta={'planningCard':payload})
