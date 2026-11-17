"""Auth de las rutas, vista por HTTP: el secreto de servicio
(``X-Rinthel-Service-Secret``) que la TUI manda en cada ruta."""

import dataclasses

import pytest

from rinthel_tui.config import Secrets

SERVICE_ROUTES = ["/config", "/theme"]


@pytest.mark.parametrize("route", SERVICE_ROUTES)
def test_service_route_accepts_the_service_secret(client, service_headers, route):
    assert client.get(route, headers=service_headers).status_code == 200


@pytest.mark.parametrize("route", SERVICE_ROUTES)
def test_service_route_rejects_a_wrong_secret(client, route):
    response = client.get(route, headers={"x-rinthel-service-secret": "wrong-secret"})
    assert (response.status_code, response.json()["detail"]) == (401, "invalid or missing service secret")


@pytest.mark.parametrize("route", SERVICE_ROUTES)
def test_service_route_rejects_a_missing_secret(client, route):
    response = client.get(route)
    assert (response.status_code, response.json()["detail"]) == (401, "invalid or missing service secret")


def test_service_route_rejects_everyone_when_the_configured_secret_is_empty(app, client):
    app.state.cfg = dataclasses.replace(app.state.cfg, secrets=Secrets(service="", panel=""))
    response = client.get("/config", headers={"x-rinthel-service-secret": ""})
    assert response.status_code == 401


def test_lifecycle_commands_never_run_without_the_service_secret(client, host):
    for command in ("/boot", "/terminate", "/reload", "/install"):
        assert client.post(command).status_code == 401
    assert host.runner.calls == []
