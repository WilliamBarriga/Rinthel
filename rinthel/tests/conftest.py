"""Fixtures compartidas. Ningún test toca red ni subprocesos reales: lo que
varía entra por un puerto con su doble (``tests/lifecycle/fakes.py``) o por
un parámetro (ADR 0005)."""

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

from rinthel_tui.config import default_config
from rinthel_tui.instance import Instance


class FakeReport:
    """PhaseReport de prueba: junta los mensajes en listas en vez de imprimir,
    para poder assertear contra ellos."""

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
    """RinthelConfig real (misma construcción que en prod vía default_config())
    sobre una Instance en tmp_path — layout (.env, data/, understory/,
    pithagoras/) y paths de log fuera del repo real."""
    base = default_config(Instance(tmp_path), platform="posix")
    return dataclasses.replace(base, llama=dataclasses.replace(base.llama, log=tmp_path / "llama-server.log"))


@pytest.fixture(autouse=True)
def _hermetic_llama_env(monkeypatch):
    """El entorno real de la máquina no debe filtrarse a los tests: paths de
    llama.cpp, variables legacy del fork y la raíz de la Instance."""
    for name in (
        "RINTHEL_LLAMA_BIN", "RINTHEL_LLAMACPP_REPO_DIR", "RINTHEL_MOE_CACHE_SLOTS",
        "RINTHEL_MOE_CACHE_PROFILE", "RINTHEL_MOE_TRACE_BUILD",
        "RINTHEL_MOE_TRACE_OUT_DIR", "RINTHEL_SCHED_ASYNC_CPU", "RINTHEL_INSTANCE_ROOT",
        "RINTHEL_SERVICE_SECRET", "RINTHEL_PANEL_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def resource_warnings():
    """Context manager que junta las ``ResourceWarning`` emitidas adentro
    (conexiones sin cerrar, por ejemplo), con un ``gc.collect()`` a
    cada lado para que cuente solo lo que se abrió en el bloque."""

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
    """``serve_http(handler_cls) -> port``: un ``HTTPServer`` local en un
    hilo, apagado y cerrado al terminar el test."""
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
    """``fake_executable(path, body)``: un script Python ejecutable en
    ``path`` con ``body`` como cuerpo. Para los adapters que corren un proceso
    (``nvidia-smi``, ``docker``): se les pasa por constructor."""

    def write(path: Path, body: str) -> None:
        path.write_text(f"#!{sys.executable}\n{body}")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    return write
