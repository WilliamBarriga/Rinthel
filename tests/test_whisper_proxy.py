"""services/whisper-stt/proxy.py — wrapper de auth/CORS delante de
whisper-server (que no tiene forma propia de autenticar). Igual que
test_tts_server.py, se carga por path con importlib porque el módulo vive
fuera de `rinthel_tui` (no es un paquete dotted-importable). El "upstream"
(whisper-server real) se simula con un segundo ThreadingHTTPServer en otro
puerto efímero de loopback — no se levanta ningún binario real.
"""

import contextlib
import http.client
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_PROXY_PATH = Path(__file__).resolve().parent.parent / "services" / "whisper-stt" / "proxy.py"

_TOKEN = "test-token"
_AUTH_HEADER = {"Authorization": f"Bearer {_TOKEN}"}


def _load_proxy_module():
    spec = importlib.util.spec_from_file_location("whisper_proxy", _PROXY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proxy = _load_proxy_module()


class _FakeUpstreamHandler(BaseHTTPRequestHandler):
    """Reemplaza whisper-server: responde /inference con un body fijo,
    reflejando el método para poder assertear el forward."""

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"text": "transcripcion fake"}')


@contextlib.contextmanager
def _fake_upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextlib.contextmanager
def _proxy_server(upstream_port: int, **handler_kwargs):
    handler_kwargs.setdefault("auth_token", _TOKEN)
    handler_kwargs.setdefault("allowed_origin", "")
    handler_cls = proxy.make_handler(upstream_host="127.0.0.1", upstream_port=upstream_port, **handler_kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_inference_forwards_to_upstream_with_valid_token():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port) as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = b"fake-multipart-audio"
        conn.request("POST", "/inference", body=body, headers={"Content-Length": str(len(body)), **_AUTH_HEADER})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()

        assert resp.status == 200
        assert data == b'{"text": "transcripcion fake"}'


def test_inference_rejects_missing_token():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port) as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/inference", body=b"x", headers={"Content-Length": "1"})
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 401


def test_inference_rejects_wrong_token():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port) as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST", "/inference", body=b"x",
            headers={"Content-Length": "1", "Authorization": "Bearer wrong"},
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 401


def test_inference_rejects_mismatched_origin():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port, allowed_origin="http://trusted.local") as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST", "/inference", body=b"x",
            headers={"Content-Length": "1", "Origin": "http://evil.example", **_AUTH_HEADER},
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 403


def test_inference_allows_missing_origin_header():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port, allowed_origin="http://trusted.local") as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/inference", body=b"x", headers={"Content-Length": "1", **_AUTH_HEADER})
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 200


def test_health_check_does_not_require_auth():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port) as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        data = resp.read()
        conn.close()

        assert resp.status == 200
        assert data == b"whisper-stt ok"


def test_options_returns_cors_preflight_headers():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port, allowed_origin="http://trusted.local") as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("OPTIONS", "/inference")
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 204
        assert resp.getheader("Access-Control-Allow-Origin") == "http://trusted.local"


def test_unknown_path_returns_404():
    with _fake_upstream() as upstream_port, _proxy_server(upstream_port) as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/whatever", body=b"x", headers={"Content-Length": "1", **_AUTH_HEADER})
        resp = conn.getresponse()
        resp.read()
        conn.close()

        assert resp.status == 404
