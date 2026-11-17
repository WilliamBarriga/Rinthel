"""Access policy against the real daemon: who gets through is decided by the
Identity store on every request, not by the token."""

import httpx

ADMIN_ROUTE = "/identity/users"
SESSION_PRINCIPAL = "/identity/me/session-principal"


def test_a_member_with_a_live_token_is_not_an_admin(http, make_user):
    member = make_user("live-member")

    assert http.get(ADMIN_ROUTE, headers=member.auth).status_code == 403


def test_a_disabled_admin_with_a_live_token_is_rejected(http, admin_auth, make_user):
    other_admin = make_user("live-other-admin", role="admin")
    assert http.get(ADMIN_ROUTE, headers=other_admin.auth).status_code == 200

    http.patch(f"/identity/users/{other_admin.id}", json={"disabled": True}, headers=admin_auth).raise_for_status()

    assert http.get(ADMIN_ROUTE, headers=other_admin.auth).status_code == 401


def test_a_disabled_user_is_rejected_when_deck_acts_for_them(http, daemon, admin_auth, make_user):
    member = make_user("live-disabled")
    acting = {**daemon.service_headers, "X-Rinthel-User-Id": str(member.id)}
    assert http.get(SESSION_PRINCIPAL, headers=acting).status_code == 200

    http.patch(f"/identity/users/{member.id}", json={"disabled": True}, headers=admin_auth).raise_for_status()

    assert http.get(SESSION_PRINCIPAL, headers=acting).status_code == 401


def test_an_empty_service_secret_lets_nobody_through(spawn_daemon):
    unconfigured = spawn_daemon(RINTHEL_SERVICE_SECRET="")

    response = httpx.get(f"{unconfigured.base_url}/config", headers={"X-Rinthel-Service-Secret": ""})

    assert response.status_code == 401
