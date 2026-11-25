import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


@pytest.fixture
def populated_db(db):
    for en, uk in [("cat", "кіт, кішка"), ("dog", "собака"), ("house", "будинок"),
                   ("apple", "яблуко"), ("to run away", "втекти")]:
        db.add_word(en, uk, "/x/", f"Example {en}")
    return db


class _Handler(BaseHTTPRequestHandler):
    hits = 0

    def log_message(self, *args):  # тихо
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        type(self).hits += 1
        if self.path.startswith("/limited"):
            self.send_response(429)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path.startswith("/quota"):
            self._send({"responseStatus": 429, "responseDetails": "quota", "responseData": {"translatedText": ""}})
        elif self.path.startswith("/api/tags"):
            self._send({"models": [{"name": "llama3.2:1b"}, {"name": "qwen2.5:1.5b"}]})
        else:  # MyMemory
            self._send({"responseStatus": 200, "responseData": {"translatedText": "Привіт"}})

    def do_POST(self):
        type(self).hits += 1
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.path.startswith("/limited"):
            self.send_response(429)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/api/chat":
            self._send({"message": {"content": "**Great!** What do you like most about it?"}})
        else:
            self._send({"matches": [
                {"offset": 3, "length": 2, "message": "Use 'goes'", "replacements": [{"value": "goes"}],
                 "rule": {"category": {"id": "GRAMMAR"}}},
                {"offset": 0, "length": 1, "message": "x", "replacements": [{"value": "X"}],
                 "rule": {"category": {"id": "TYPOGRAPHY"}}},
            ]})


@pytest.fixture
def fake_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def server_hits():
    _Handler.hits = 0
    return lambda: _Handler.hits
