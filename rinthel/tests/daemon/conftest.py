"""Harness HTTP de los tests de rutas: ``TestClient`` sobre
``create_app(cfg)`` con un ``cfg`` propio del test (Instance en
``tmp_path``, secretos fijos). Lifecycle corre sobre un ``Host`` de dobles y
las fuentes de telemetría son las en memoria — nada de monkeypatch de
globals del daemon. Identity is the real ``SqliteIdentity`` on the temporary
root's ``rinthel.db``, migrated by the real migrator; the clock is manual."""

import dataclasses

import pytest
from fastapi.testclient import TestClient

from rinthel_tui import database
from rinthel_tui.api import create_app
from rinthel_tui.api.adapters import Adapters
from rinthel_tui.clock import ManualClock
from rinthel_tui.config import Secrets
from rinthel_tui.identity import tokens
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.domain.types import UserRow
from rinthel_tui.models.adapters.memory import InMemoryActiveModels, InMemoryCatalog, InMemoryTurns
from rinthel_tui.models.composition import ModelAdapters
from rinthel_tui.monitoring.adapters.memory import (
    InMemoryContainers,
    InMemoryGpu,
    InMemoryHost,
    InMemoryLog,
    InMemoryReadiness,
)
from rinthel_tui.monitoring.domain.monitor import TelemetrySources
from tests.lifecycle.fakes import fake_host

SERVICE_SECRET = "test-service-secret"
# 32+ bytes: PyJWT warns on shorter HMAC keys.
PANEL_SECRET = "test-panel-secret-of-at-least-32-bytes"
PASSWORD = "pw123456"


@pytest.fixture
def daemon_cfg(cfg):
    return dataclasses.replace(cfg, secrets=Secrets(service=SERVICE_SECRET, panel=PANEL_SECRET))


@pytest.fixture
def telemetry() -> TelemetrySources:
    """Sin docker/nvidia-smi/psutil ni archivos reales detrás de
    ``/ws/monitor``."""
    log = InMemoryLog()
    log.write("arranque")
    return TelemetrySources(
        gpu=InMemoryGpu(), host=InMemoryHost(), containers=InMemoryContainers(), log=log, llama=InMemoryReadiness()
    )


@pytest.fixture
def host():
    """El ``Host`` de dobles donde corren los planes de lifecycle."""
    return fake_host()[0]


@pytest.fixture
def model_adapters() -> ModelAdapters:
    """Catálogo, modelo activo y turnos en memoria: los Local models que el
    test declare."""
    return ModelAdapters(catalog=InMemoryCatalog(), active=InMemoryActiveModels(), turns=InMemoryTurns())


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def identity_path(daemon_cfg):
    path = daemon_cfg.instance.database_path
    database.migrate(path)
    return path


@pytest.fixture
def identity(identity_path, clock) -> SqliteIdentity:
    return SqliteIdentity(identity_path, clock=clock)


@pytest.fixture
def adapters(telemetry, host, identity, model_adapters) -> Adapters:
    """The app's clock stays the system one: the Monitor samples on it. A
    test that moves time for tokens swaps in ``clock``."""
    return Adapters(telemetry=telemetry, lifecycle_host=host, identity=identity, models=model_adapters)


@pytest.fixture
def app(daemon_cfg, adapters):
    return create_app(daemon_cfg, adapters=adapters)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def service_headers() -> dict:
    return {"x-rinthel-service-secret": SERVICE_SECRET}


@pytest.fixture
def seed_user(identity):
    """Creates a user straight in the Identity store (password ``pw123456``)."""

    def seed(username: str, role: str = "miembro", **kwargs) -> UserRow:
        return identity.create_user(username=username, password_hash=tokens.hash_password(PASSWORD), role=role, **kwargs)

    return seed


@pytest.fixture
def bearer(client):
    """Headers with the Panel token of ``username``, obtained through
    ``POST /identity/login`` as Deck would."""

    def headers(username: str) -> dict:
        body = client.post("/identity/login", json={"username": username, "password": PASSWORD}).json()
        return {"Authorization": f"Bearer {body['access_token']}"}

    return headers
