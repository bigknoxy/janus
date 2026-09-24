"""P1: portable end-to-end gate — the REAL janus CLI process against a stub
OpenAI endpoint, no laptop required. This is the commit-blocking e2e; the
real-model harness (dev/e2e_real_model.sh) is the eval floor."""

import json
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

GOOD_PATCH = (
    "file: mod.py\n<<<<<<< SEARCH\n    return items[: n - 1]  # BUG\n"
    "=======\n    return items[:n]\n>>>>>>> REPLACE"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Stub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps({"data": [{"id": "stub"}]}).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps(
            {"choices": [{"message": {"content": GOOD_PATCH}}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_cli_end_to_end(tmp_path: Path):
    (tmp_path / "mod.py").write_text(
        "def first_n(items, n):\n    return items[: n - 1]  # BUG\n"
    )
    (tmp_path / "test_mod.py").write_text(
        "from mod import first_n\n\n\ndef test():\n    assert first_n([1, 2], 2) == [1, 2]\n"
    )

    server = HTTPServer(("127.0.0.1", _free_port()), _Stub)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = {
            "PATH": f"{Path(sys.executable).parent}:{'/usr/bin:/bin'}",
            "JANUS_S1_BACKEND": "mock",
            "JANUS_S2_BASE_URL": f"http://127.0.0.1:{port}/v1",
            "JANUS_VERIFY_COMMAND": f"{sys.executable} -m pytest -q test_mod.py",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "janus.cli", "run", "--yes",
             "fix first_n in mod.py: it returns one item too few",
             "--root", str(tmp_path)],
            capture_output=True, text=True, env=env, timeout=120,
        )
    finally:
        server.shutdown()

    assert proc.returncode == 0, proc.stderr[-500:]
    assert "patched_verified" in proc.stdout
    assert (tmp_path / "mod.py").read_text() == (
        "def first_n(items, n):\n    return items[:n]\n"
    )
