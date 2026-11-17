"""``running_model_services`` (the live suite harness) against fake services
that are real processes: a tiny Python HTTP server with ``/health``. Nothing
is mocked; the fake ``LocalProcessService`` has the same fields as the ones
in ``lifecycle/services.py``."""

import dataclasses
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from rinthel_tui.lifecycle.service_defs import LocalProcessService
from tests.live.model_services import running_model_services

_SERVER = (
    "import http.server, sys\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')\n"
    "    def log_message(self, *a): pass\n"
    "http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _responds(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1).read()
    except (urllib.error.URLError, OSError):
        return False
    return True


def _fake_service(port: int, log_dir, name: str = "fake-server") -> LocalProcessService:
    return LocalProcessService(
        display_name=name,
        menu_label=name,
        wait_label=name,
        kill_label=name,
        build_argv=lambda cfg: [sys.executable, "-c", _SERVER, str(port)],
        port_of=lambda cfg: port,
        log_of=lambda cfg: log_dir / f"{name}.log",
        ready_url_of=lambda cfg: f"http://127.0.0.1:{port}/health",
        default_ready_timeout=15,
        ready_poll_interval=0.1,
    )


CFG = SimpleNamespace()


def test_starts_a_service_that_is_down_and_stops_it_on_exit(tmp_path):
    port = _free_port()
    service = _fake_service(port, tmp_path)

    with running_model_services(CFG, [service]) as started:
        assert started == ["fake-server"]
        assert _responds(port)

    assert not _responds(port)


@pytest.fixture
def already_up(tmp_path):
    """A real service already running before the suite starts."""
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", _SERVER, str(port)])
    try:
        deadline = time.monotonic() + 10
        while not _responds(port):
            assert time.monotonic() < deadline, "the previous service did not start"
            time.sleep(0.05)  # real wait: polls an external service that starts on its own
        yield port, proc
    finally:
        proc.kill()
        proc.wait()


def test_leaves_a_service_that_was_already_up_alone(tmp_path, already_up):
    port, proc = already_up
    service = _fake_service(port, tmp_path)

    with running_model_services(CFG, [service]) as started:
        assert started == []

    assert _responds(port)
    assert proc.poll() is None


def test_refuses_to_start_llama_without_the_explicit_flag(tmp_path):
    port = _free_port()
    llama = _fake_service(port, tmp_path, name="llama-server")

    with pytest.raises(RuntimeError, match="--start-llm"), running_model_services(CFG, [llama]):
        pytest.fail("should not have entered")

    assert not _responds(port)


def test_starts_llama_when_the_flag_is_given(tmp_path):
    port = _free_port()
    llama = _fake_service(port, tmp_path, name="llama-server")

    with running_model_services(CFG, [llama], allow_llm=True) as started:
        assert started == ["llama-server"]
        assert _responds(port)

    assert not _responds(port)


def test_fails_when_the_port_is_taken_by_something_that_does_not_answer(tmp_path):
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        service = _fake_service(squatter.getsockname()[1], tmp_path)

        with pytest.raises(RuntimeError, match="busy"), running_model_services(CFG, [service]):
            pytest.fail("should not have entered")


def test_stops_what_it_started_even_when_a_later_service_fails(tmp_path):
    good_port = _free_port()
    good = _fake_service(good_port, tmp_path, name="good")
    bad = dataclasses.replace(
        good,
        display_name="bad",
        build_argv=lambda cfg: [sys.executable, "-c", "raise SystemExit(3)"],
        port_of=lambda cfg: _free_port(),
        ready_url_of=lambda cfg: "http://127.0.0.1:1/health",
    )

    with pytest.raises(RuntimeError, match="bad"), running_model_services(CFG, [good, bad]):
        pytest.fail("should not have entered")

    assert not _responds(good_port)
