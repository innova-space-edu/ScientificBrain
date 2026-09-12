from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from scientific_brain.templates import theoretical_project_template


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(theoretical_project_template(), ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
