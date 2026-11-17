"""Secret rotation against a real daemon. Each test starts its own: rotating
invalidates the secret the rest of the suite talks with, so the session's
daemon is never rotated."""

import httpx
from dotenv import dotenv_values

SERVICE_KEY = "RINTHEL_SERVICE_SECRET"
PANEL_KEY = "RINTHEL_PANEL_SECRET"


def _get_config(daemon, secret: str) -> int:
    return httpx.get(f"{daemon.base_url}/config", headers={"X-Rinthel-Service-Secret": secret}).status_code


def _rotate(daemon, key: str) -> httpx.Response:
    return httpx.post(f"{daemon.base_url}/secrets/rotate", json={"key": key}, headers=daemon.service_headers, timeout=30)


def test_rotating_the_service_secret_swaps_which_one_passes(spawn_daemon):
    daemon = spawn_daemon()

    response = _rotate(daemon, SERVICE_KEY)

    assert response.status_code == 200, response.text
    new_secret = response.json()["service_secret"]
    assert dotenv_values(daemon.root / ".env")[SERVICE_KEY] == new_secret != daemon.service_secret
    assert _get_config(daemon, daemon.service_secret) == 401
    assert _get_config(daemon, new_secret) == 200


def test_rotating_the_panel_secret_logs_users_out_but_not_the_service(spawn_daemon):
    daemon = spawn_daemon()
    with httpx.Client(base_url=daemon.base_url) as http:
        token = http.post(
            "/identity/login", json={"username": daemon.admin_username, "password": daemon.admin_password}
        ).json()["access_token"]
        assert http.get("/identity/users", headers={"Authorization": f"Bearer {token}"}).status_code == 200

        response = _rotate(daemon, PANEL_KEY)

        assert response.status_code == 200, response.text
        assert dotenv_values(daemon.root / ".env")[PANEL_KEY]
        assert http.get("/identity/users", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert _get_config(daemon, daemon.service_secret) == 200
