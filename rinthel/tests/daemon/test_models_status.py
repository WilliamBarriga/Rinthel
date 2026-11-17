"""``models_status`` on ``/ws/monitor`` through the real ``create_app``
composition: one line per Capability (active Local model, service state,
optional error) and one row per managed service the Instance runs on its
Platform. The catalog and the active ids are the in-memory doubles; whether a
service answers is the ``Probe`` of the ``Host`` doubles."""

import dataclasses
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rinthel_tui.api import create_app
from rinthel_tui.api.adapters import real_telemetry
from rinthel_tui.models.domain.types import CatalogEntry, LocalModel

LLAMA_READY = "http://127.0.0.1:8080/v1/models"


@pytest.fixture
def catalog(model_adapters, daemon_cfg):
    model_adapters.catalog.set_entries([
        CatalogEntry(daemon_cfg.local_model.id, daemon_cfg.local_model),
        CatalogEntry("roto", None, "GGUF no encontrado: /m/roto.gguf"),
        CatalogEntry("whisper", LocalModel("whisper", "Whisper", "stt", Path("/m/whisper.bin"), 1)),
    ])
    return model_adapters


def _models_status(cfg, adapters, host, service_headers) -> dict:
    # Only ``models_status`` comes from the real composition; the other
    # sources stay in memory.
    models = real_telemetry(lambda: app.state.cfg, host, adapters.models).models
    app = create_app(cfg, adapters=dataclasses.replace(
        adapters, telemetry=dataclasses.replace(adapters.telemetry, models=models),
    ))
    token = service_headers["x-rinthel-service-secret"]
    with TestClient(app).websocket_connect(f"/ws/monitor?token={token}") as ws:
        while (message := ws.receive_json())["type"] != "models_status":
            pass
    return message["data"]


def _without_portal(cfg):
    """Only Understory among the managed services, as in the shared fixture: both portals off."""
    return dataclasses.replace(
        cfg,
        pithagoras=dataclasses.replace(cfg.pithagoras, enabled=False),
        deck=dataclasses.replace(cfg.deck, enabled=False),
    )


def test_the_active_llm_model_that_answers_is_ready(daemon_cfg, adapters, host, catalog, service_headers):
    catalog.active.set("llm", daemon_cfg.local_model.id)
    host.probe.script_http(LLAMA_READY, True)

    data = _models_status(daemon_cfg, adapters, host, service_headers)

    assert data["capabilities"] == [
        {"capability": "llm", "model": daemon_cfg.local_model.id, "state": "ready", "error": None},
    ]


def test_an_active_llm_model_that_does_not_answer_is_down(daemon_cfg, adapters, host, catalog, service_headers):
    catalog.active.set("llm", daemon_cfg.local_model.id)

    data = _models_status(daemon_cfg, adapters, host, service_headers)

    assert data["capabilities"][0]["state"] == "down"


@pytest.mark.parametrize(("active", "error"), [("nadie", "desconocido"), ("roto", "GGUF no encontrado")])
def test_an_unusable_active_id_is_off_with_its_error(daemon_cfg, adapters, host, catalog, service_headers, active, error):
    catalog.active.set("llm", active)
    host.probe.script_http(LLAMA_READY, True)

    (llm,) = _models_status(daemon_cfg, adapters, host, service_headers)["capabilities"]

    assert (llm["model"], llm["state"]) == (active, "off")
    assert error in llm["error"]


def test_no_active_llm_model_has_no_model_and_says_how_to_pick_one(
    daemon_cfg, adapters, host, catalog, service_headers
):
    (llm,) = _models_status(daemon_cfg, adapters, host, service_headers)["capabilities"]

    assert (llm["model"], llm["state"]) == (None, "off")
    assert "models use" in llm["error"]


def test_a_disabled_llama_server_leaves_llm_off(daemon_cfg, adapters, host, catalog, service_headers):
    catalog.active.set("llm", daemon_cfg.local_model.id)
    host.probe.script_http(LLAMA_READY, True)
    cfg = dataclasses.replace(daemon_cfg, llama=dataclasses.replace(daemon_cfg.llama, enabled=False))

    (llm,) = _models_status(cfg, adapters, host, service_headers)["capabilities"]

    assert llm["state"] == "off"


def test_voice_is_reported_only_when_active_on_linux(daemon_cfg, adapters, host, catalog, service_headers):
    catalog.active.set("stt", "whisper")

    linux = _models_status(daemon_cfg, adapters, host, service_headers)["capabilities"]
    windows = _models_status(dataclasses.replace(daemon_cfg, platform="windows"), adapters, host, service_headers)

    assert [c["capability"] for c in linux] == ["llm", "stt"]
    assert linux[1]["model"] == "whisper"
    assert [c["capability"] for c in windows["capabilities"]] == ["llm"]


def test_each_enabled_managed_service_is_a_row_with_its_state(daemon_cfg, adapters, host, catalog, service_headers):
    host.probe.script_http(f"http://127.0.0.1:{daemon_cfg.understory.port}/", True)

    services = _models_status(_without_portal(daemon_cfg), adapters, host, service_headers)["services"]

    assert services == [{"name": "Understory", "state": "ready"}]


def test_deck_is_a_row_when_enabled(daemon_cfg, adapters, host, catalog, service_headers):
    host.probe.script_http(f"http://127.0.0.1:{daemon_cfg.understory.port}/", True)
    host.probe.script_http(f"http://127.0.0.1:{daemon_cfg.deck.port}/api/auth/status", True)
    cfg = dataclasses.replace(daemon_cfg, pithagoras=dataclasses.replace(daemon_cfg.pithagoras, enabled=False))

    services = _models_status(cfg, adapters, host, service_headers)["services"]

    assert services == [{"name": "Understory", "state": "ready"}, {"name": "Deck", "state": "ready"}]


def test_a_service_that_does_not_answer_is_down(daemon_cfg, adapters, host, catalog, service_headers):
    services = _models_status(_without_portal(daemon_cfg), adapters, host, service_headers)["services"]

    assert services == [{"name": "Understory", "state": "down"}]
