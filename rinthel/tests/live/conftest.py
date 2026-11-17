"""Harness of the ``live`` suite: a real daemon in a subprocess (the same
``main`` as ``rinthel-boot.sh``) on a temporary root, with its own SQLite file
and a free port. It runs by hand with ``python -m pytest -m live``; the default
run excludes it.

It never touches the real Instance: the temporary root brings its own
``.env``, ``rinthel.db`` and Local model catalog, every port is a free one
(llama-server included, so a model switch only kills listeners of that port),
and the root, the listeners and the processes of the run are cleaned on exit.
The real Instance's config is only *read*, for the llama-server binary, its
hardware tuning and the Local model to load.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import httpx
import psutil
import pytest

from rinthel_tui import database
from rinthel_tui.config import LLAMA_FIELDS, RinthelConfig, default_config
from rinthel_tui.identity import tokens as identity_tokens
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle.services import LLAMA_SERVICE
from rinthel_tui.models.adapters.json_catalog import write_catalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from rinthel_tui.models.domain.types import LocalModel
from tests.live import garbage
from tests.live.model_services import running_model_services

READY_TIMEOUT_S = 30
# Llama fields that are not hardware tuning: the temporary Instance sets its own.
_OWN_LLAMA_FIELDS = {"bin", "port", "log", "enabled"}


def pytest_collection_modifyitems(config, items):
    live_dir = Path(__file__).parent
    for item in items:
        if live_dir in Path(item.fspath).parents:
            item.add_marker(pytest.mark.live)


@dataclass
class LiveDaemon:
    base_url: str
    root: Path
    service_secret: str
    panel_secret: str
    admin_username: str
    admin_password: str
    llama_port: int
    llama_log: Path
    proc: subprocess.Popen | None = None

    @property
    def pid(self) -> int:
        return self.proc.pid

    @property
    def log(self) -> str:
        return (self.root / "daemon.log").read_text()

    @property
    def service_headers(self) -> dict[str, str]:
        return {"X-Rinthel-Service-Secret": self.service_secret}

    @property
    def ws_monitor_url(self) -> str:
        return self.base_url.replace("http://", "ws://") + f"/ws/monitor?token={self.service_secret}"

    def stop(self) -> None:
        """Stops it like a Ctrl+C (idempotent); ``log`` stays complete."""
        _stop(self.proc)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def real_cfg() -> RinthelConfig:
    """The config of the real Instance, only read: the llama-server binary,
    its hardware tuning and the active Local model."""
    return default_config(Instance.discover())


@pytest.fixture(scope="session", autouse=True)
def no_garbage_left(request):
    """When the session ends (after the daemons are stopped), the run left no
    directory ``/tmp/rinthel-live-*`` nor container ``rinthel-live-*``. With
    ``--sweep-leftovers`` it first removes what dead runs left."""
    resources = garbage.live_resources()
    if request.config.getoption("--sweep-leftovers"):
        garbage.sweep(resources)
    yield
    left = garbage.find_garbage(resources)
    assert not left, "the live suite left garbage:\n  " + "\n  ".join(left)


def _clean_env(root: Path) -> dict[str, str]:
    """The shell env without ``RINTHEL_*``/``COMPOSE_*``: the temporary
    ``.env`` rules, and nothing can point the daemon at the real Instance."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RINTHEL_", "COMPOSE_"))}
    env["RINTHEL_INSTANCE_ROOT"] = str(root)
    return env


def _write_env(root: Path, values: dict[str, str]) -> None:
    (root / ".env").write_text("".join(f"{k}={v}\n" for k, v in values.items()))


def _llama_tuning(real_cfg: RinthelConfig) -> dict[str, str]:
    """The hardware tuning of the real Instance as ``.env`` lines, so the
    llama-server of the run loads the model the way this machine does."""
    values = {}
    for f in LLAMA_FIELDS:
        if f.attr in _OWN_LLAMA_FIELDS:
            continue
        value = getattr(real_cfg.llama, f.attr)
        values[f.env] = str(value).lower() if isinstance(value, bool) else str(value)
    return values


@pytest.fixture(scope="session")
def base_model(real_cfg: RinthelConfig) -> LocalModel:
    """The Local model the live runs load: ``RINTHEL_LIVE_GGUF`` (a small GGUF
    for a machine whose GPU is busy) or the active one of the real Instance."""
    if gguf := os.environ.get("RINTHEL_LIVE_GGUF"):
        window = int(os.environ.get("RINTHEL_LIVE_CONTEXT", "8192"))
        return LocalModel("live-base", "Live base", "llm", Path(gguf), window)
    if real_cfg.local_model is None:
        pytest.fail(
            "no Local model to load: the real Instance has no active one; set RINTHEL_LIVE_GGUF to a GGUF file",
            pytrace=False,
        )
    return dataclasses.replace(real_cfg.local_model, id="live-base", name="Live base")


def seed_admin(root: Path, username: str, password: str) -> None:
    """As INSTALL does: the first admin goes straight to ``rinthel.db``,
    before the daemon starts."""
    path = Instance(root).database_path
    database.migrate(path)
    identity = SqliteIdentity(path)
    with identity.transaction() as tx:
        tx.create_user(username=username, password_hash=identity_tokens.hash_password(password), role="admin")


def _wait_ready(proc: subprocess.Popen, daemon: LiveDaemon) -> None:
    log_path = daemon.root / "daemon.log"
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"the daemon exited with {proc.returncode}:\n{log_path.read_text()}", pytrace=False)
        with contextlib.suppress(httpx.TransportError):
            httpx.get(f"{daemon.base_url}/config", headers=daemon.service_headers, timeout=1)
            return
        time.sleep(0.2)
    pytest.fail(f"the daemon did not answer within {READY_TIMEOUT_S}s:\n{log_path.read_text()}", pytrace=False)


def _stop(proc: subprocess.Popen) -> None:
    """SIGINT, like a Ctrl+C: uvicorn closes the lifespan cleanly."""
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def stop_listeners(port: int) -> None:
    """Kills whatever listens on ``port``. Only ever called with the free port
    the run picked for its own llama-server, never a port of the real Instance."""
    for conn in psutil.net_connections(kind="tcp"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port and conn.pid:
            with contextlib.suppress(psutil.Error):
                psutil.Process(conn.pid).kill()


@contextlib.contextmanager
def _running_daemon(
    real_cfg: RinthelConfig,
    *,
    models: tuple[LocalModel, ...] = (),
    active: str | None = None,
    **env_overrides: str,
) -> Iterator[LiveDaemon]:
    """A real daemon on its own temporary root, stopped and cleaned on exit.
    ``models`` fill its catalog and ``active`` is the active one; with models
    its llama-server is enabled (on a free port of its own).
    ``env_overrides`` overrides entries of its ``.env``."""
    root = Path(tempfile.mkdtemp(prefix=garbage.TMP_PREFIX, dir=garbage.TMP_ROOT))
    port = _free_port()
    live = LiveDaemon(
        base_url=f"http://127.0.0.1:{port}",
        root=root,
        service_secret=secrets.token_urlsafe(32),
        panel_secret=secrets.token_urlsafe(32),
        admin_username="live-admin",
        admin_password=secrets.token_urlsafe(12),
        llama_port=_free_port(),
        llama_log=root / "llama-server.log",
    )
    log_path = root / "daemon.log"
    log_text = ""

    def read_log() -> None:
        nonlocal log_text
        if log_path.exists():
            log_text = log_path.read_text()

    # Callbacks run in reverse order even if the setup fails halfway: nothing
    # of the run stays outside this stack.
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(shutil.rmtree, root, ignore_errors=True)
        cleanup.callback(read_log)
        cleanup.callback(stop_listeners, live.llama_port)
        live.llama_log.touch()
        # compose directories exist (empty): the Monitor's `docker compose ps` is a real child process.
        for name in ("understory", "pithagoras"):
            (root / name).mkdir()
        _write_env(
            root,
            {
                **_llama_tuning(real_cfg),
                "RINTHEL_LLAMA_BIN": str(real_cfg.llama.bin),
                "RINTHEL_LLAMA_PORT": str(live.llama_port),
                "RINTHEL_LLAMA_LOG_PATH": str(live.llama_log),
                "RINTHEL_LLAMA_ENABLED": "true" if models else "false",
                "RINTHEL_DAEMON_PORT": str(port),
                "RINTHEL_SERVICE_SECRET": live.service_secret,
                "RINTHEL_PANEL_SECRET": live.panel_secret,
                **env_overrides,
            },
        )
        instance = Instance(root)
        if models:
            write_catalog(instance.models_catalog_path, list(models))
            TomlActiveModels(instance.instance_toml_path).set("llm", active or models[0].id)
        seed_admin(root, live.admin_username, live.admin_password)

        log_file = log_path.open("w")
        cleanup.callback(log_file.close)
        proc = subprocess.Popen(
            [sys.executable, "-m", "rinthel_tui.daemon"],
            env=_clean_env(root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        cleanup.callback(_stop, proc)
        live.proc = proc
        _wait_ready(proc, live)
        yield live
    # Only if the test got to the end: a failure of its own is not covered by this one.
    if "Traceback" in log_text:
        at = log_text.index("Traceback")
        pytest.fail(f"the daemon left a Traceback in its daemon.log:\n{log_text[at : at + 2000]}", pytrace=False)


@pytest.fixture(scope="session")
def daemon(real_cfg):
    """One daemon for the whole session, llama-server disabled."""
    with _running_daemon(real_cfg) as live:
        yield live


@pytest.fixture
def spawn_daemon(real_cfg):
    """``spawn_daemon(**kwargs) -> LiveDaemon`` (see ``_running_daemon``): a
    throwaway daemon apart from the session's, stopped when the test ends."""
    with contextlib.ExitStack() as stack:
        yield lambda **kwargs: stack.enter_context(_running_daemon(real_cfg, **kwargs))


@pytest.fixture
def real_llama(request, real_cfg):
    """``real_llama(daemon)``: guarantees a real llama-server up on the
    daemon's own free port, loaded with the daemon's active Local model. It
    starts one only with ``--start-llm`` and fails (not skips: a false green
    is worse than a red) without it. Stopped when the test ends."""
    if not request.config.getoption("--start-llm"):
        pytest.fail("this live test needs a real llama-server: pass --start-llm", pytrace=False)
    if not Path(real_cfg.llama.bin).exists():
        pytest.fail(
            f"llama-server binary not found: {real_cfg.llama.bin} (set RINTHEL_LLAMA_BIN in the .env)", pytrace=False
        )
    stack = contextlib.ExitStack()

    def start(live: LiveDaemon) -> None:
        with mock.patch.dict(os.environ, _clean_env(live.root), clear=True):
            cfg = default_config(Instance(live.root))
        try:
            stack.enter_context(running_model_services(cfg, [LLAMA_SERVICE], allow_llm=True))
        except RuntimeError as exc:
            pytest.fail(str(exc), pytrace=False)

    with stack:
        yield start


@pytest.fixture
def http(daemon):
    with httpx.Client(base_url=daemon.base_url, timeout=30) as client:
        yield client


def login(http: httpx.Client, username: str, password: str) -> dict[str, str]:
    """``Authorization`` header of ``username``, through ``POST /identity/login`` as Deck does."""
    response = http.post("/identity/login", json={"username": username, "password": password})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@dataclass(frozen=True)
class LiveUser:
    id: int
    username: str
    password: str
    auth: dict[str, str]


@pytest.fixture
def admin_auth(daemon, http):
    return login(http, daemon.admin_username, daemon.admin_password)


@pytest.fixture
def make_user(http, admin_auth):
    """``make_user(username, role=...) -> LiveUser``, already logged in,
    through the admin routes; deleted when the test ends."""
    created: list[int] = []

    def make(username: str, *, role: str = "miembro") -> LiveUser:
        password = secrets.token_urlsafe(12)
        response = http.post(
            "/identity/users", json={"username": username, "password": password, "role": role}, headers=admin_auth
        )
        response.raise_for_status()
        created.append(response.json()["id"])
        return LiveUser(created[-1], username, password, login(http, username, password))

    yield make
    for user_id in created:
        http.delete(f"/identity/users/{user_id}", headers=admin_auth)
