import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import urllib.error

from src.llm import _backoff_base, _post


class _Handler(BaseHTTPRequestHandler):
    mode = "flaky"  # flaky: 429 một lần rồi 200 | down: luôn 429
    hits = 0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        type(self).hits += 1
        if type(self).mode == "down" or (type(self).mode == "flaky" and type(self).hits == 1):
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "rate limited"}')
            return
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def local_url():
    _Handler.hits = 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/x"
    srv.shutdown()


def test_backoff_base_default_and_env(monkeypatch):
    monkeypatch.delenv("BACKOFF_BASE_S", raising=False)
    assert _backoff_base() == 30.0
    monkeypatch.setenv("BACKOFF_BASE_S", "10")
    assert _backoff_base() == 10.0
    monkeypatch.setenv("BACKOFF_BASE_S", "abc")
    assert _backoff_base() == 30.0


def test_post_succeeds_after_429(local_url, monkeypatch):
    _Handler.mode = "flaky"
    monkeypatch.setenv("BACKOFF_BASE_S", "0")
    stats: dict = {"attempts": [], "sleep_s": 0.0}
    data = _post(local_url, {"a": 1}, {}, retries=2, stats=stats)
    assert data["ok"] is True
    assert len(stats["attempts"]) == 2
    assert stats["attempts"][0]["ok"] is False
    assert stats["attempts"][0]["code"] == 429
    assert stats["attempts"][1]["ok"] is True
    assert stats["sleep_s"] == 0.0
    assert "127.0.0.1" in stats["attempts"][0]["host"]


def test_post_fast_fail_no_sleep_on_retries_1(local_url, monkeypatch):
    _Handler.mode = "down"
    monkeypatch.setenv("BACKOFF_BASE_S", "30")
    stats: dict = {"attempts": [], "sleep_s": 0.0}
    t0 = time.time()
    with pytest.raises(urllib.error.HTTPError):
        _post(local_url, {"a": 1}, {}, retries=1, stats=stats)
    assert time.time() - t0 < 10
    assert len(stats["attempts"]) == 1
    assert stats["sleep_s"] == 0.0


def test_post_records_sleep_time(local_url, monkeypatch):
    _Handler.mode = "down"
    monkeypatch.setenv("BACKOFF_BASE_S", "1")
    stats: dict = {"attempts": [], "sleep_s": 0.0}
    with pytest.raises(urllib.error.HTTPError):
        _post(local_url, {"a": 1}, {}, retries=2, stats=stats)
    assert len(stats["attempts"]) == 2
    assert stats["sleep_s"] == 1.0
