"""POST /secrets/rotate — por HTTP: chequeo del env del shell,
``Instance.rotate_secret``, swap del ``cfg`` vivo y la forma de la respuesta."""

import pytest


@pytest.fixture
def rotate(client, service_headers):
    return lambda key: client.post("/secrets/rotate", json={"key": key}, headers=service_headers)


def test_rotating_the_service_secret_returns_the_new_one_and_only_it_is_accepted(client, rotate, service_headers):
    response = rotate("RINTHEL_SERVICE_SECRET")

    assert response.status_code == 200
    new = response.json()["service_secret"]
    assert new != service_headers["x-rinthel-service-secret"]
    assert client.get("/config", headers={"x-rinthel-service-secret": new}).status_code == 200
    assert client.get("/config", headers=service_headers).status_code == 401


def test_rotating_the_panel_secret_writes_a_new_one_and_keeps_the_service_secret(
    client, rotate, daemon_cfg, service_headers
):
    response = rotate("RINTHEL_PANEL_SECRET")

    assert response.status_code == 200
    assert response.json() == {"results": []}
    assert daemon_cfg.instance.get("RINTHEL_PANEL_SECRET") not in (None, daemon_cfg.secrets.panel)
    assert client.app.state.cfg.secrets.panel == daemon_cfg.instance.get("RINTHEL_PANEL_SECRET")
    assert client.get("/config", headers=service_headers).status_code == 200


def test_a_key_that_is_not_rotatable_is_rejected(rotate):
    assert rotate("UNDERSTORY_TOKEN").status_code == 422


def test_a_key_set_in_the_daemon_shell_env_is_refused_before_writing(
    client, rotate, monkeypatch, daemon_cfg, service_headers
):
    # Las RINTHEL_* del shell ganan sobre el .env: rotar el archivo no
    # cambiaría nada.
    monkeypatch.setenv("RINTHEL_SERVICE_SECRET", "from-the-shell")

    response = rotate("RINTHEL_SERVICE_SECRET")

    assert response.status_code == 409
    assert daemon_cfg.instance.get("RINTHEL_SERVICE_SECRET") is None
    assert client.get("/config", headers=service_headers).status_code == 200
