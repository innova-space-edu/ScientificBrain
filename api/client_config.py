from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from scientific_brain.auth import supabase_public_config


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = supabase_public_config()
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
