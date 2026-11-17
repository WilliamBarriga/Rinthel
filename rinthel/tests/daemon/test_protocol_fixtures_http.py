"""Fixtures doradas del protocolo (``tests/protocol_fixtures/``) contra la
respuesta HTTP real de su ruta — el contrato que el cliente Rust lee de las
mismas fixtures (``rinthel-client/tests/protocol_fixtures.rs``). Donde la
ruta se puede llevar a producir exactamente la fixture, se exige igualdad;
``config_payload`` depende del ``cfg`` del test, así que ahí se exige la
misma forma. Los envelopes del WebSocket no tienen ruta HTTP y siguen en
``tests/protocol/test_fixtures.py``."""

import json
from pathlib import Path

import pytest

from rinthel_tui.api.deps import get_lifecycle
from rinthel_tui.lifecycle.domain.types import UnitOutcome

FIXTURES = Path(__file__).parent.parent / "protocol_fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_theme_response_is_its_golden_fixture(client, service_headers):
    response = client.get("/theme", headers=service_headers)

    assert response.status_code == 200
    assert response.json() == _load("theme.json")


@pytest.mark.parametrize("command", ["boot", "terminate"])
def test_lifecycle_command_response_is_its_golden_fixture(app, client, service_headers, command):
    golden = _load(f"{command}_result.json")

    class GoldenLifecycle:
        def __getattr__(self, name: str):
            async def run() -> list[UnitOutcome]:
                return [UnitOutcome(**r) for r in golden["results"]] if name == command else []

            return run

    app.dependency_overrides[get_lifecycle] = GoldenLifecycle

    response = client.post(f"/{command}", headers=service_headers)

    assert response.status_code == 200
    assert response.json() == golden


def test_rejected_config_save_is_its_golden_fixture(client, service_headers, daemon_cfg):
    collision = {"RINTHEL_UNDERSTORY_PORT": str(daemon_cfg.llama.port)}

    response = client.post("/config", json={"overrides": collision}, headers=service_headers)

    assert response.status_code == 200
    assert response.json() == _load("config_save_result.json")


def _shape(value):
    """Forma de un valor JSON: claves y tipos en todos los niveles, sin los
    valores. Los arrays se reducen al conjunto de formas de sus elementos."""
    if isinstance(value, dict):
        return {key: _shape(v) for key, v in value.items()}
    if isinstance(value, list):
        return sorted({json.dumps(_shape(v), sort_keys=True) for v in value})
    return type(value).__name__


def test_config_payload_has_the_shape_of_its_golden_fixture(client, service_headers):
    golden = _load("config_payload.json")

    body = client.get("/config", headers=service_headers).json()

    by_attr = {s["attr"]: s for s in body["services"]}
    for service in golden["services"]:
        assert _shape(by_attr[service["attr"]]) == _shape(service), service["attr"]


def test_service_secret_rotation_has_the_shape_of_its_golden_fixture(client, service_headers):
    # El secreto nuevo es aleatorio: se exige la forma, no los valores.
    golden = _load("rotate_result.json")

    response = client.post("/secrets/rotate", json={"key": "RINTHEL_SERVICE_SECRET"}, headers=service_headers)

    assert response.status_code == 200
    assert _shape(response.json()) == _shape(golden)
