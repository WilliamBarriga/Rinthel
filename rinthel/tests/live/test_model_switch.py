"""Local model switch against a real llama-server: kill, spawn and ready, and
the real rollback when the new model does not come up. Needs ``--start-llm``.

The daemon runs on a temporary root whose llama-server listens on a free port
of its own, so the switch only ever kills what this test started. The catalog
holds the base model (the real Instance's active one, or ``RINTHEL_LIVE_GGUF``),
the same GGUF under another id and context window (a switch that changes
something observable), and a file with the GGUF magic and garbage after it
(``llama-server`` exits while loading it)."""

import dataclasses

import httpx
import pytest

SWITCH_TIMEOUT_S = 420  # the daemon waits up to 90 s per start; a rollback starts twice


@pytest.fixture
def models(base_model, tmp_path_factory):
    other = dataclasses.replace(base_model, id="live-other", name="Live other", context_window=base_model.context_window // 2)
    broken_file = tmp_path_factory.mktemp("broken") / "broken.gguf"
    broken_file.write_bytes(b"GGUF" + b"\x00" * 64)
    broken = dataclasses.replace(
        base_model, id="live-broken", name="Live broken", gguf=broken_file, mmproj=None, mtp=False
    )
    return base_model, other, broken


@pytest.fixture
def switching(spawn_daemon, real_llama, models):
    daemon = spawn_daemon(models=models, active=models[0].id)
    real_llama(daemon)
    admin = httpx.post(
        f"{daemon.base_url}/identity/login",
        json={"username": daemon.admin_username, "password": daemon.admin_password},
    ).json()["access_token"]
    return daemon, {"Authorization": f"Bearer {admin}"}


def _llama_ready(daemon) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{daemon.llama_port}/v1/models", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def _listener_pid(port: int) -> int:
    import psutil

    (pid,) = {
        c.pid for c in psutil.net_connections(kind="tcp") if c.status == psutil.CONN_LISTEN and c.laddr.port == port
    }
    return pid


def _activate(daemon, auth, model_id: str) -> httpx.Response:
    return httpx.post(
        f"{daemon.base_url}/models/activate", json={"id": model_id}, headers=auth, timeout=SWITCH_TIMEOUT_S
    )


def _routing(daemon) -> dict:
    return httpx.get(f"{daemon.base_url}/model-provider/routing", headers=daemon.service_headers).json()["capabilities"]["llm"]


def test_a_switch_kills_the_old_llama_and_spawns_the_new_model(switching, models):
    daemon, admin = switching
    before = _listener_pid(daemon.llama_port)

    response = _activate(daemon, admin, "live-other")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["ok"], body["active"], body["rolled_back"]) == (True, "live-other", None)
    assert _llama_ready(daemon)
    assert _listener_pid(daemon.llama_port) != before
    route = _routing(daemon)
    assert (route["model"], route["context_window"]) == ("live-other", models[1].context_window)


def test_a_model_that_does_not_start_rolls_back_to_the_previous_one(switching, models):
    daemon, admin = switching

    response = _activate(daemon, admin, "live-broken")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["ok"], body["active"], body["rolled_back"]) == (False, "live-base", True)
    assert _llama_ready(daemon), "the previous model must be serving again after the rollback"
    route = _routing(daemon)
    assert (route["model"], route["context_window"]) == ("live-base", models[0].context_window)
    listing = httpx.get(f"{daemon.base_url}/models", headers=admin).json()
    assert listing["active"]["llm"] == "live-base"
