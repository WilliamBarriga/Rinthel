"""Identity over HTTP: ``create_app`` on a temporary Instance root with its
``rinthel.db`` migrated (``SqliteIdentity``) and a fake Deck. Login, refresh
and logout; user administration with its guards; deletion that retires
Deck's Sessions first; and ``session-principal`` for Deck's service."""

from dataclasses import replace

import jwt
import pytest
from fastapi.testclient import TestClient

from rinthel_tui.api import create_app
from rinthel_tui.identity.adapters.memory import InMemoryDeckSessions
from rinthel_tui.identity.domain.errors import DeckSessionsError

PASSWORD = "pw123456"


@pytest.fixture
def deck() -> InMemoryDeckSessions:
    return InMemoryDeckSessions()


@pytest.fixture
def adapters(adapters, deck, clock):
    """The daemon with Deck enabled (its fake) and a manual clock, so token
    expiry is a ``clock.advance``."""
    return replace(adapters, deck_sessions=deck, clock=clock)


@pytest.fixture
def login(client):
    def do(username: str, password: str = PASSWORD):
        return client.post("/identity/login", json={"username": username, "password": password})

    return do


@pytest.fixture
def admin(seed_user, bearer) -> dict:
    seed_user("admin", role="admin")
    return bearer("admin")


def _new_user(client, headers, username="ana", role="miembro", **more) -> dict:
    response = client.post(
        "/identity/users", json={"username": username, "password": PASSWORD, "role": role, **more}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── login / refresh / logout ─────────────────────────────────────────────


def test_login_returns_a_panel_token_for_the_user(seed_user, login, daemon_cfg):
    seed_user("admin", role="admin")

    body = login("admin").json()

    assert body["user"] == {"id": 1, "username": "admin", "role": "admin"}
    assert body["access_expires_in"] == 86400
    claims = jwt.decode(
        body["access_token"], daemon_cfg.secrets.panel, algorithms=["HS256"], options={"verify_exp": False}
    )
    assert claims["exp"] - claims["iat"] == 86400
    assert (claims["sub"], claims["username"], claims["role"], claims["typ"]) == ("1", "admin", "admin", "access")
    assert "group" not in claims and "permissions" not in claims
    assert body["refresh_token"]


def test_login_rejects_a_wrong_password_an_unknown_user_and_a_disabled_one(seed_user, login, identity):
    user = seed_user("ana")
    assert login("ana", "wrong-pass").status_code == 401
    assert login("nadie").status_code == 401

    identity.update_user(user.id, disabled=True)

    assert login("ana").status_code == 401


def test_without_a_panel_secret_nobody_logs_in(seed_user, client, daemon_cfg, app):
    seed_user("admin", role="admin")
    app.state.cfg = replace(daemon_cfg, secrets=replace(daemon_cfg.secrets, panel=""))

    response = client.post("/identity/login", json={"username": "admin", "password": PASSWORD})

    assert response.status_code == 503


def test_refresh_rotates_and_the_spent_token_stops_working(seed_user, login, client):
    seed_user("ana")
    first = login("ana").json()["refresh_token"]

    refreshed = client.post("/identity/refresh", json={"refresh_token": first})

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != first
    assert client.post("/identity/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/identity/refresh", json={"refresh_token": refreshed.json()["refresh_token"]}).status_code == 200


def test_refresh_rejects_an_unknown_token(client):
    assert client.post("/identity/refresh", json={"refresh_token": "not-a-real-token"}).status_code == 401


def test_an_expired_refresh_token_is_rejected(seed_user, login, client, clock):
    seed_user("ana")
    refresh = login("ana").json()["refresh_token"]

    clock.advance(30 * 86400)

    assert client.post("/identity/refresh", json={"refresh_token": refresh}).status_code == 401


def test_logout_revokes_the_refresh_token(seed_user, login, client):
    seed_user("ana")
    refresh = login("ana").json()["refresh_token"]

    assert client.post("/identity/logout", json={"refresh_token": refresh}).json() == {"ok": True}

    assert client.post("/identity/refresh", json={"refresh_token": refresh}).status_code == 401


def test_logout_without_a_token_is_a_no_op(client):
    assert client.post("/identity/logout", json={}).json() == {"ok": True}


# ── policies: user, admin ────────────────────────────────────────────────


def test_user_administration_needs_an_admin_bearer(seed_user, bearer, client):
    seed_user("ana")

    assert client.get("/identity/users").status_code == 401
    assert client.get("/identity/users", headers={"Authorization": "Bearer basura"}).status_code == 401
    assert client.get("/identity/users", headers=bearer("ana")).status_code == 403


def test_the_service_secret_is_not_an_admin(client, service_headers):
    assert client.get("/identity/users", headers=service_headers).status_code == 401


def test_an_expired_access_token_is_rejected(admin, client, clock):
    clock.advance(86400)

    assert client.get("/identity/users", headers=admin).status_code == 401


def test_a_token_signed_with_another_secret_is_rejected(seed_user, client):
    seed_user("admin", role="admin")
    forged = jwt.encode({"sub": "1", "typ": "access", "exp": 4102444800}, "other-secret-of-32-bytes-or-more!", "HS256")

    assert client.get("/identity/users", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_a_demoted_admin_loses_access_on_the_next_request(admin, seed_user, bearer, client, identity):
    seed_user("otro", role="admin")
    headers = bearer("otro")
    other = identity.get_user_by_username("otro")

    client.patch(f"/identity/users/{other.id}", json={"role": "miembro"}, headers=admin)

    assert client.get("/identity/users", headers=headers).status_code == 403


def test_a_disabled_user_loses_access_before_the_token_expires(admin, seed_user, bearer, client, identity):
    seed_user("otro", role="admin")
    headers = bearer("otro")

    identity.update_user(identity.get_user_by_username("otro").id, disabled=True)

    assert client.get("/identity/users", headers=headers).status_code == 401


# ── user administration ──────────────────────────────────────────────────


def test_an_admin_creates_lists_and_edits_users(admin, client, login):
    created = _new_user(client, admin, notes="recepción")
    assert {k: created[k] for k in ("username", "role", "notes", "disabled")} == {
        "username": "ana", "role": "miembro", "notes": "recepción", "disabled": False,
    }

    patched = client.patch(f"/identity/users/{created['id']}", json={"role": "admin", "notes": ""}, headers=admin)

    assert (patched.json()["role"], patched.json()["notes"]) == ("admin", "")
    listed = client.get("/identity/users", headers=admin).json()["users"]
    assert [u["username"] for u in listed] == ["admin", "ana"]
    assert all("password_hash" not in u for u in listed)
    assert login("ana").status_code == 200


def test_a_duplicate_username_is_409(admin, client):
    response = client.post(
        "/identity/users", json={"username": "admin", "password": PASSWORD, "role": "miembro"}, headers=admin
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "username_taken"


def test_the_admin_changes_a_password_including_their_own(admin, client, login):
    ana = _new_user(client, admin)

    client.patch(f"/identity/users/{ana['id']}", json={"password": "nuevo-pw-99"}, headers=admin)
    client.patch("/identity/users/1", json={"password": "otra-pw-99"}, headers=admin)

    assert login("ana", "nuevo-pw-99").status_code == 200
    assert login("ana").status_code == 401
    assert login("admin", "otra-pw-99").status_code == 200


def test_a_member_cannot_edit_anyone_not_even_themselves(seed_user, bearer, client):
    ana = seed_user("ana")

    response = client.patch(f"/identity/users/{ana.id}", json={"password": "nuevo-pw-99"}, headers=bearer("ana"))

    assert response.status_code == 403


def test_disabling_a_user_revokes_their_refresh_tokens(admin, client, login):
    ana = _new_user(client, admin)
    refresh = login("ana").json()["refresh_token"]

    response = client.patch(f"/identity/users/{ana['id']}", json={"disabled": True}, headers=admin)

    assert response.json()["disabled"] is True
    assert client.post("/identity/refresh", json={"refresh_token": refresh}).status_code == 401
    assert login("ana").status_code == 401


def test_enabling_a_user_again_lets_them_log_in(admin, client, login):
    ana = _new_user(client, admin)
    client.patch(f"/identity/users/{ana['id']}", json={"disabled": True}, headers=admin)

    client.patch(f"/identity/users/{ana['id']}", json={"disabled": False}, headers=admin)

    assert login("ana").status_code == 200


def test_editing_an_unknown_user_is_404(admin, client):
    assert client.patch("/identity/users/999", json={"notes": "x"}, headers=admin).status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/identity/login", {"username": "admin"}),
        ("POST", "/identity/refresh", {}),
        ("POST", "/identity/users", {"username": "ana", "password": PASSWORD}),
        ("POST", "/identity/users", {"username": "ana", "password": PASSWORD, "role": "root"}),
        ("POST", "/identity/users", {"username": "ana", "password": "corto", "role": "miembro"}),
        ("POST", "/identity/users", {"username": "   ", "password": PASSWORD, "role": "miembro"}),
        ("POST", "/identity/users", {"username": "ana", "password": PASSWORD, "role": "miembro", "group_id": 1}),
        ("PATCH", "/identity/users/1", {"role": "root"}),
        ("PATCH", "/identity/users/1", {"disabled": "maybe"}),
        ("PATCH", "/identity/users/1", {"permissions": ["browser.personal"]}),
    ],
)
def test_a_malformed_body_is_422(admin, client, method, path, body):
    assert client.request(method, path, json=body, headers=admin).status_code == 422


# ── guards: self-lockout and last admin ──────────────────────────────────


@pytest.mark.parametrize("body", [{"disabled": True}, {"role": "miembro"}])
def test_an_admin_cannot_lock_themselves_out(admin, client, body):
    response = client.patch("/identity/users/1", json=body, headers=admin)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_lockout"


def test_an_admin_cannot_delete_themselves(admin, client, deck):
    response = client.delete("/identity/users/1", headers=admin)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_lockout"
    assert deck.retire_calls == []


def test_an_admin_can_edit_their_own_notes(admin, client):
    assert client.patch("/identity/users/1", json={"notes": "yo"}, headers=admin).status_code == 200


def test_an_admin_can_disable_and_delete_another_admin(admin, client, seed_user, identity):
    otro = seed_user("otro", role="admin")

    assert client.patch(f"/identity/users/{otro.id}", json={"disabled": True}, headers=admin).status_code == 200
    assert client.delete(f"/identity/users/{otro.id}", headers=admin).json() == {"ok": True}
    assert identity.get_user(otro.id) is None


# ── deletion: Deck's Sessions first ──────────────────────────────────────


def test_deleting_a_user_retires_their_deck_sessions_first(admin, client, seed_user, identity, deck, login):
    ana = seed_user("ana")
    refresh = login("ana").json()["refresh_token"]
    deck.add(ana.id)
    deck.add(ana.id)
    deck.add(1)

    response = client.delete(f"/identity/users/{ana.id}", headers=admin)

    assert (response.status_code, response.json()) == (200, {"ok": True})
    assert deck.retire_calls == [ana.id]
    assert deck.sessions_of(ana.id) == [] and len(deck.sessions_of(1)) == 1
    assert identity.get_user(ana.id) is None
    assert client.post("/identity/refresh", json={"refresh_token": refresh}).status_code == 401


@pytest.mark.parametrize("how", ["down", "refuses"])
def test_if_deck_fails_the_user_stays_and_the_admin_gets_a_clear_error(admin, client, seed_user, identity, deck, how):
    ana = seed_user("ana")
    deck.add(ana.id)
    if how == "down":
        deck.fail_next("retire_user_sessions", DeckSessionsError("deck unreachable"))
    else:
        deck.refuse = True

    response = client.delete(f"/identity/users/{ana.id}", headers=admin)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "sessions_not_retired"
    assert "Deck" in detail["message"] and "Sessions" in detail["message"]
    assert identity.get_user(ana.id) is not None


def test_a_retried_deletion_finishes_once_deck_is_back(admin, client, seed_user, identity, deck):
    ana = seed_user("ana")
    deck.fail_next("retire_user_sessions", DeckSessionsError("deck unreachable"))
    assert client.delete(f"/identity/users/{ana.id}", headers=admin).status_code == 502

    assert client.delete(f"/identity/users/{ana.id}", headers=admin).status_code == 200
    assert identity.get_user(ana.id) is None


def test_deleting_an_unknown_user_is_ok_and_does_not_call_deck(admin, client, deck):
    assert client.delete("/identity/users/999", headers=admin).json() == {"ok": True}
    assert deck.retire_calls == []


def test_without_deck_deleting_a_user_skips_the_retirement(daemon_cfg, adapters, seed_user, identity, deck):
    client = TestClient(create_app(daemon_cfg, adapters=replace(adapters, deck_sessions=None)))
    seed_user("admin", role="admin")
    ana = seed_user("ana")
    token = client.post("/identity/login", json={"username": "admin", "password": PASSWORD}).json()["access_token"]

    response = client.delete(f"/identity/users/{ana.id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert identity.get_user(ana.id) is None
    assert deck.retire_calls == []


# ── service_as_user: only session-principal ──────────────────────────────


def _as(service_headers, user_id) -> dict:
    return {**service_headers, "x-rinthel-user-id": str(user_id)}


def test_session_principal_reads_the_live_role_for_deck(client, seed_user, service_headers, identity):
    ana = seed_user("ana", role="admin")

    response = client.get("/identity/me/session-principal", headers=_as(service_headers, ana.id))
    assert (response.status_code, response.json()) == (200, {"user_id": ana.id, "role": "admin"})

    identity.update_user(ana.id, role="miembro")
    assert client.get("/identity/me/session-principal", headers=_as(service_headers, ana.id)).json() == {
        "user_id": ana.id, "role": "miembro",
    }


@pytest.mark.parametrize("how", ["disabled", "deleted", "unknown", "not_a_number", "missing"])
def test_session_principal_of_a_user_that_cannot_act_is_401(client, seed_user, service_headers, identity, how):
    ana = seed_user("ana")
    user_id: object = ana.id
    if how == "disabled":
        identity.update_user(ana.id, disabled=True)
    elif how == "deleted":
        identity.delete_user(ana.id)
    elif how == "unknown":
        user_id = 999
    elif how == "not_a_number":
        user_id = "ana"
    headers = service_headers if how == "missing" else _as(service_headers, user_id)

    assert client.get("/identity/me/session-principal", headers=headers).status_code == 401


def test_session_principal_needs_the_service_secret(client, seed_user, bearer):
    ana = seed_user("ana", role="admin")

    assert client.get("/identity/me/session-principal", headers=bearer("ana")).status_code == 401
    wrong = {"x-rinthel-service-secret": "otro", "x-rinthel-user-id": str(ana.id)}
    assert client.get("/identity/me/session-principal", headers=wrong).status_code == 401


def test_identity_routes_close_every_connection_they_open(admin, client, login, resource_warnings):
    with resource_warnings() as leaked:
        session = login("admin").json()
        client.post("/identity/refresh", json={"refresh_token": session["refresh_token"]})
        ana = _new_user(client, admin)
        client.patch(f"/identity/users/{ana['id']}", json={"disabled": True}, headers=admin)
        client.get("/identity/users", headers=admin)
        client.delete(f"/identity/users/{ana['id']}", headers=admin)

    assert leaked == []


def test_an_unavailable_identity_store_is_503(admin, client, identity_path):
    identity_path.unlink()
    identity_path.mkdir()

    assert client.get("/identity/users", headers=admin).status_code == 503
    assert client.post("/identity/login", json={"username": "admin", "password": PASSWORD}).status_code == 503

