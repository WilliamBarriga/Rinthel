"""Harness HTTP de los tests de rutas: ``TestClient`` sobre
``create_app(cfg)`` con un ``cfg`` propio del test (Instance en
``tmp_path``, secretos fijos). Lifecycle corre sobre un ``Host`` de dobles y
las fuentes de telemetría son las en memoria — nada de monkeypatch de
globals del daemon."""

import dataclasses

import pytest
from fastapi.testclient import TestClient

from rinthel_tui.api import create_app
from rinthel_tui.api.adapters import Adapters
from rinthel_tui.config import Secrets
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
PANEL_SECRET = "test-panel-secret"


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
def adapters(telemetry, host) -> Adapters:
    return Adapters(telemetry=telemetry, lifecycle_host=host)


@pytest.fixture
def app(daemon_cfg, adapters):
    return create_app(daemon_cfg, adapters=adapters)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def service_headers() -> dict:
    return {"x-rinthel-service-secret": SERVICE_SECRET}
