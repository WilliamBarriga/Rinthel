"""Local models por HTTP: la ruta que el daemon entrega a Deck
(``GET /model-provider/routing``), el listado del catálogo y el cambio de
modelo (``POST /models/activate``). El cambio corre el Lifecycle plan real
de llama sobre el ``Host`` de dobles: un ``llama-server`` que muere al
arrancar es un argv con ``exits=True`` en ``FakeProcesses``."""

import dataclasses
import json
from pathlib import Path

import httpx
import pytest

from rinthel_tui.config import with_local_model
from rinthel_tui.lifecycle.services import _llama_argv
from rinthel_tui.models.domain.types import CatalogEntry, LocalModel

READY = "http://127.0.0.1:8080/v1/models"


@pytest.fixture
def new_model(tmp_path) -> LocalModel:
    return LocalModel("nuevo", "Nuevo", "llm", tmp_path / "nuevo.gguf", 32768, reasoning_format="deepseek")


@pytest.fixture
def catalog_entries(daemon_cfg, new_model):
    return [
        CatalogEntry(daemon_cfg.local_model.id, daemon_cfg.local_model),
        CatalogEntry(new_model.id, new_model),
        CatalogEntry("roto", None, "GGUF no encontrado: /m/roto.gguf"),
        CatalogEntry("voz", LocalModel("voz", "Voz", "tts", Path("/m/voz.gguf"), 1)),
    ]


@pytest.fixture(autouse=True)
def _catalog(model_adapters, catalog_entries, daemon_cfg, host):
    model_adapters.catalog.set_entries(catalog_entries)
    model_adapters.active.set("llm", daemon_cfg.local_model.id)
    host.probe.script_http(READY, True)


@pytest.fixture
def admin_headers(seed_user, bearer) -> dict:
    """The Panel token of an admin, as Deck sends it."""
    seed_user("root", role="admin")
    return bearer("root")


def _activate(client, admin_headers, model_id: str):
    return client.post("/models/activate", json={"id": model_id}, headers=admin_headers)


def _dies_on_start(host, cfg, model: LocalModel) -> None:
    host.processes.script(_llama_argv(with_local_model(cfg, model)), exits=True)


# ── GET /model-provider/routing ──────────────────────────────────────────


def test_routing_hands_deck_the_active_model_at_the_deck_host_address(app, client, service_headers, daemon_cfg):
    app.state.cfg = dataclasses.replace(daemon_cfg, deck=dataclasses.replace(daemon_cfg.deck, host_address="host.docker.internal"))

    response = client.get("/model-provider/routing", headers=service_headers)

    assert response.status_code == 200
    assert response.json() == {"capabilities": {"llm": {
        "url": "http://host.docker.internal:8080",
        "model": "test-model",
        "context_window": 112000,
        "reasoning_format": "qwen-chat-template",
    }}}


def test_routing_has_no_llm_route_without_an_active_model(app, client, service_headers, daemon_cfg):
    app.state.cfg = dataclasses.replace(daemon_cfg, local_model=None)

    assert client.get("/model-provider/routing", headers=service_headers).json() == {"capabilities": {}}


def test_routing_is_for_the_service_only(client):
    assert client.get("/model-provider/routing").status_code == 401


# ── GET /models ──────────────────────────────────────────────────────────


def test_models_lists_the_catalog_with_what_can_be_activated(client, admin_headers):
    body = client.get("/models", headers=admin_headers).json()

    assert body["active"] == {"llm": "test-model", "stt": None, "tts": None}
    by_id = {m["id"]: m for m in body["models"]}
    assert [m["id"] for m in body["models"]] == ["test-model", "nuevo", "roto", "voz"]
    assert by_id["nuevo"] == {
        "id": "nuevo", "name": "Nuevo", "capability": "llm", "activable": True, "problem": None,
        "context_window": 32768, "reasoning_format": "deepseek",
    }
    assert (by_id["roto"]["activable"], by_id["roto"]["problem"]) == (False, "GGUF no encontrado: /m/roto.gguf")


# ── POST /models/activate ────────────────────────────────────────────────


def test_a_switch_kills_spawns_the_new_model_and_makes_it_active(
    app, client, admin_headers, service_headers, host, model_adapters
):
    response = _activate(client, admin_headers, "nuevo")

    assert response.status_code == 200
    body = response.json()
    assert (body["ok"], body["active"], body["rolled_back"]) == (True, "nuevo", None)
    (spawn,) = host.processes.spawns
    assert spawn.argv[spawn.argv.index("-m") + 1].endswith("nuevo.gguf")
    assert model_adapters.active.get("llm") == "nuevo"
    route = client.get("/model-provider/routing", headers=service_headers).json()["capabilities"]["llm"]
    assert (route["model"], route["context_window"], route["reasoning_format"]) == ("nuevo", 32768, "deepseek")
    assert app.state.cfg.local_model.id == "nuevo"


def test_a_model_that_does_not_come_up_is_rolled_back(app, client, admin_headers, host, daemon_cfg, new_model,
                                                      model_adapters):
    _dies_on_start(host, daemon_cfg, new_model)

    body = _activate(client, admin_headers, "nuevo").json()

    assert (body["ok"], body["active"], body["rolled_back"]) == (False, "test-model", True)
    assert [s.argv[s.argv.index("-m") + 1] for s in host.processes.spawns] == [
        str(new_model.gguf), str(daemon_cfg.local_model.gguf),
    ]
    assert [r["ok"] for r in body["results"]] == [False, True]
    assert model_adapters.active.get("llm") == "test-model"
    assert app.state.cfg.local_model.id == "test-model"


def test_a_failed_rollback_is_reported(client, admin_headers, host, daemon_cfg, new_model, model_adapters):
    _dies_on_start(host, daemon_cfg, new_model)
    _dies_on_start(host, daemon_cfg, daemon_cfg.local_model)

    body = _activate(client, admin_headers, "nuevo").json()

    assert (body["ok"], body["active"], body["rolled_back"]) == (False, "test-model", False)
    assert model_adapters.active.get("llm") == "test-model"


def test_switching_with_turns_in_flight_is_409_and_touches_nothing(client, admin_headers, host, model_adapters):
    model_adapters.turns.busy = True

    response = _activate(client, admin_headers, "nuevo")

    assert (response.status_code, response.json()["detail"]) == (409, "turns_in_flight")
    assert host.processes.spawns == []
    assert model_adapters.active.get("llm") == "test-model"


@pytest.mark.parametrize("model_id,status,detail", [
    ("nadie", 404, "unknown_model"),
    ("roto", 422, "not_activable: GGUF no encontrado: /m/roto.gguf"),
    ("voz", 422, "not_activable: la Capability tts todavía no tiene managed service"),
])
def test_what_cannot_be_activated_is_rejected_before_touching_llama(client, admin_headers, host, model_id, status,
                                                                   detail):
    response = _activate(client, admin_headers, model_id)

    assert (response.status_code, response.json()["detail"]) == (status, detail)
    assert host.processes.spawns == []


@pytest.mark.parametrize("method,path", [("GET", "/models"), ("POST", "/models/activate")])
def test_model_administration_is_for_an_admin_only(client, service_headers, seed_user, bearer, host, method, path):
    seed_user("ana")
    body = {"json": {"id": "nuevo"}} if method == "POST" else {}

    assert client.request(method, path, **body).status_code == 401
    assert client.request(method, path, headers=service_headers, **body).status_code == 401
    assert client.request(method, path, headers=bearer("ana"), **body).status_code == 403
    assert host.processes.spawns == []


# ── el lock global contra boot, terminate, reload e install ─────────────


@pytest.fixture
def aclient(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://daemon")


async def test_a_switch_while_a_lifecycle_command_runs_is_409(app, aclient, admin_headers, host):
    async with aclient, app.state.lifecycle_lock.hold():
        response = await aclient.post("/models/activate", json={"id": "nuevo"}, headers=admin_headers)

    assert (response.status_code, response.json()["detail"]) == (409, "lifecycle_busy")
    assert host.processes.spawns == []


@pytest.mark.parametrize("command", ["boot", "terminate", "reload", "install"])
async def test_a_lifecycle_command_while_a_switch_runs_is_409(app, aclient, service_headers, command):
    async with aclient, app.state.lifecycle_lock.hold():
        response = await aclient.post(f"/{command}", headers=service_headers)

    assert (response.status_code, response.json()["detail"]) == (409, "lifecycle_busy")
