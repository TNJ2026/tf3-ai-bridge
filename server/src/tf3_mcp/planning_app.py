"""MCP Apps planning card and explicit-click loopback HTML links."""
from __future__ import annotations

import atexit
import base64
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp
from mcp.types import CallToolResult, TextContent

RESOURCE_URI = 'ui://tf3/planning-card.html'
TOOL_META = {'ui': {'resourceUri': RESOURCE_URI}}
apps = Apps()
apps.add_html_resource(RESOURCE_URI, Path(__file__).with_name('planning_card.html').read_text(encoding='utf-8'),
                       title='TF3 规划图', prefers_border=False,
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


def card_result(plan, report, summary):
    """Image data stays in UI metadata; text-only clients retain useful paths and findings."""
    png = Path(report.get('cardImage', report['files']['png'])).read_bytes()
    html_url = links.register(report['files']['html'])
    payload = dict(title=plan['title'], scope=plan['scope'],
                   image='data:image/png;base64,'+base64.b64encode(png).decode('ascii'),
                   htmlUrl=html_url, htmlPath=report['files']['html'],
                   width=report.get('cardWidth', report['width']), height=report.get('cardHeight', report['height']))
    result = dict(summary, files=report['files'], html_url=html_url,
                  display='MCP Apps card; do not automatically open HTML', scope=plan['scope'])
    return CallToolResult(content=[TextContent(type='text',text=json.dumps(result,ensure_ascii=False))],
                          structured_content=result, meta={'planningCard':payload})
