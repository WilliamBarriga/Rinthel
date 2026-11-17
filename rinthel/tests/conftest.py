"""Shared fixtures. No test touches the real network or real subprocesses:
what varies comes in through a port with its double
(``tests/lifecycle/fakes.py``) or through a parameter (testing-policy ADR)."""

import contextlib
import dataclasses
import gc
import stat
import sys
import threading
import warnings
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from rinthel_tui.config import default_config, with_local_model
from rinthel_tui.instance import Instance
from rinthel_tui.models.domain.types import LocalModel


def pytest_addoption(parser):
    parser.addoption(
        "--start-llm",
        action="store_true",
        help="live suite: allow it to start a real llama-server (it never does on its own)",
    )
    parser.addoption(
        "--sweep-leftovers",
        action="store_true",
        help="live suite: delete, before starting, what dead runs left (/tmp/rinthel-live-* and "
        "rinthel-live-* containers); only when nobody else is running the suite",
    )


class FakeReport:
    """Test PhaseReport: collects the messages in lists instead of printing,
    so tests can assert against them."""

    def __init__(self) -> None:
        self.infos: list[str] = []
        self.successes: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    def success(self, msg: str) -> None:
        self.successes.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)


@pytest.fixture
def report() -> FakeReport:
    return FakeReport()


@pytest.fixture
def cfg(tmp_path):
    """Real RinthelConfig (same construction as in prod via default_config())
    over an Instance in tmp_path — layout (.env, data/, subtrees) and log
    paths outside the real repo — with an active Local model, as INSTALL
    leaves it."""
    base = default_config(Instance(tmp_path), platform="linux")
    base = with_local_model(base, LocalModel("test-model", "Test model", "llm", tmp_path / "model.gguf", 112000))
    return dataclasses.replace(base, llama=dataclasses.replace(base.llama, log=tmp_path / "llama-server.log"))


@pytest.fixture(autouse=True)
def _hermetic_llama_env(monkeypatch):
    """The machine's real environment must not leak into the tests: llama.cpp
    paths, the fork's legacy variables and the Instance root."""
    for name in (
        "RINTHEL_LLAMA_BIN", "RINTHEL_LLAMACPP_REPO_DIR", "RINTHEL_MOE_CACHE_SLOTS",
        "RINTHEL_MOE_CACHE_PROFILE", "RINTHEL_MOE_TRACE_BUILD",
        "RINTHEL_MOE_TRACE_OUT_DIR", "RINTHEL_SCHED_ASYNC_CPU", "RINTHEL_INSTANCE_ROOT",
        "RINTHEL_SERVICE_SECRET", "RINTHEL_PANEL_SECRET",
        "RINTHEL_WHISPER_BIN", "RINTHEL_WHISPER_PORT", "RINTHEL_AUDIOCPP_BIN", "RINTHEL_AUDIOCPP_PORT",
        "RINTHEL_HOSTEXECD_TOKEN", "RINTHEL_HOSTEXECD_PORT", "RINTHEL_HOSTEXECD_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def resource_warnings():
    """Context manager that collects the ``ResourceWarning`` emitted inside
    (unclosed connections, for example), with a ``gc.collect()`` on
    each side so it counts only what was opened in the block."""

    @contextlib.contextmanager
    def collect():
        gc.collect()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            found: list[warnings.WarningMessage] = []
            yield found
            gc.collect()
        found.extend(w for w in caught if issubclass(w.category, ResourceWarning))

    return collect


@pytest.fixture
def serve_http():
    """``serve_http(handler_cls) -> port``: a local ``HTTPServer`` in a
    thread, shut down and closed when the test ends."""
    running: list[tuple[HTTPServer, threading.Thread]] = []

    def serve(handler_cls: type[BaseHTTPRequestHandler]) -> int:
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        running.append((server, thread))
        return server.server_port

    yield serve
    for server, thread in running:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def fake_executable():
    """``fake_executable(path, body)``: an executable Python script at
    ``path`` with ``body`` as its body. For the adapters that run a process
    (``nvidia-smi``, ``docker``): it is passed to them via the constructor."""

    def write(path: Path, body: str) -> None:
        path.write_text(f"#!{sys.executable}\n{body}")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    return write
