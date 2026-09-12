from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from scientific_brain import __version__
from scientific_brain.providers import provider_configuration_summary


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "service": "ScientificBrain",
            "version": __version__,
            "status": "ok",
            **provider_configuration_summary("research"),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
