"""Ejemplo de la categoría 'services/tts-piper' — wrapper HTTP sobre piper.

`services/tts-piper/server.py` vive fuera del paquete `rinthel_tui` (no es
importable por nombre por el guion en `tts-piper/`), así que se carga por
path con importlib. Estilo de mocking: se reemplaza `subprocess.run` (todo
lo que `_synthesize` usa para invocar el binario real) y el servidor HTTP en
sí se levanta real en un puerto efímero de loopback, para probar el
parseo de request/response tal cual lo ve un cliente.
"""

import http.client
import importlib.util
import json
import subprocess
import threading
from pathlib import Path

import pytest

_SERVER_PATH = Path(__file__).resolve().parent.parent / "services" / "tts-piper" / "server.py"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("tts_piper_server", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tts_server = _load_server_module()


@pytest.fixture
def running_server(monkeypatch):
    def fake_run(argv, input=None, capture_output=None, check=None):
        out_path = argv[argv.index("--output_file") + 1]
        Path(out_path).write_bytes(b"RIFF....WAVEfake")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    voices = {"es": "voice-es.onnx", "en": "voice-en.onnx"}
    handler_cls = tts_server.make_handler(voices, "piper-bin")
    server = tts_server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_speak_returns_wav_for_valid_payload(running_server):
    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "hola", "lang": "es"}).encode()
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body))})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    assert resp.status == 200
    assert resp.getheader("Content-Type") == "audio/wav"
    assert data == b"RIFF....WAVEfake"


def test_speak_rejects_malformed_json(running_server):
    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = b"not json"
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body))})
    resp = conn.getresponse()
    resp.read()
    conn.close()

    assert resp.status == 400


def test_speak_falls_back_to_spanish_voice_for_unknown_lang(monkeypatch, running_server):
    used_voice = {}

    def fake_run(argv, input=None, capture_output=None, check=None):
        used_voice["path"] = argv[argv.index("--model") + 1]
        out_path = argv[argv.index("--output_file") + 1]
        Path(out_path).write_bytes(b"fake")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "bonjour", "lang": "fr"}).encode()
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body))})
    resp = conn.getresponse()
    resp.read()
    conn.close()

    assert resp.status == 200
    assert used_voice["path"] == "voice-es.onnx"


def test_speak_returns_500_when_piper_fails(monkeypatch, running_server):
    def fake_run(argv, input=None, capture_output=None, check=None):
        raise subprocess.CalledProcessError(1, argv, stderr=b"piper blew up")

    monkeypatch.setattr(subprocess, "run", fake_run)

    port = running_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps({"text": "hola"}).encode()
    conn.request("POST", "/speak", body=body, headers={"Content-Length": str(len(body))})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    assert resp.status == 500
    assert b"piper blew up" in data
