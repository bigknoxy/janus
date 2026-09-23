#!/usr/bin/env python3
"""Dev-only stub of an OpenAI-compatible System 2 endpoint.

Serves POST /v1/chat/completions (scripted patch) and GET /v1/models so the
real janus binary can be dogfooded end-to-end without a live LLM.

Usage: python3 dev/stub_s2.py <port> <mode>   # mode: good | bad
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

GOOD = (
    "file: calc.py\n<<<<<<< SEARCH\n"
    "    total = amount * rate\n=======\n"
    "    total = amount * (1 + rate)\n>>>>>>> REPLACE"
)
BAD = (
    "file: calc.py\n<<<<<<< SEARCH\n"
    "    total = amount * rate\n=======\n"
    "    total = amount  # broken\n>>>>>>> REPLACE"
)


class Handler(BaseHTTPRequestHandler):
    mode = "good"
    calls = 0

    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json({"data": [{"id": "stub-qwen3-4b"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # consume body
        Handler.calls += 1
        content = GOOD if self.mode == "good" else BAD
        self._json({"choices": [{"message": {"content": content}}]})

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8199
    Handler.mode = sys.argv[2] if len(sys.argv) > 2 else "good"
    print(f"stub s2 listening on {port} mode={Handler.mode}", file=sys.stderr)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
