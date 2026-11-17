"""Suite de contrato del puerto ``PackageRegistry``: el adapter de npm contra
un ``http.server`` local, y ``FakeRegistry``."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rinthel_tui.lifecycle.adapters.npm_registry import NpmRegistry
from tests.lifecycle.fakes import FakeRegistry

PUBLISHED = {"@scope/pkg": "1.2.3"}


class _Registry(BaseHTTPRequestHandler):
    def do_GET(self):
        package = self.path.removeprefix("/").removesuffix("/latest")
        if package in PUBLISHED:
            body = json.dumps({"version": PUBLISHED[package]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(params=["npm", "fake"])
def registry(request):
    if request.param == "fake":
        yield FakeRegistry(PUBLISHED)
        return
    server = HTTPServer(("127.0.0.1", 0), _Registry)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    yield NpmRegistry(registry=f"http://127.0.0.1:{server.server_port}")
    server.shutdown()
    server.server_close()


async def test_latest_is_the_published_version(registry):
    assert await registry.latest("@scope/pkg") == "1.2.3"


async def test_latest_is_none_for_an_unknown_package(registry):
    assert await registry.latest("@scope/nunca-publicado") is None


async def test_latest_is_none_when_the_registry_is_down():
    assert await NpmRegistry(registry="http://127.0.0.1:1").latest("@scope/pkg", timeout=1) is None
