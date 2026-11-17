"""Recovering admin access: ``reset_admin`` and the first admin of INSTALL on
both ``Identity`` adapters, and the operator command
(``python -m rinthel_tui.identity reset-admin``) on a temporary Instance."""

import pytest

from rinthel_tui import database
from rinthel_tui.identity import tokens
from rinthel_tui.identity.__main__ import main
from rinthel_tui.identity.adapters.memory import InMemoryIdentity
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.admin import ensure_first_admin, reset_admin
from rinthel_tui.instance import Instance

FAR = "2999-01-01T00:00:00+00:00"


@pytest.fixture(params=["memory", "sqlite"])
def identity(request, tmp_path):
    if request.param == "memory":
        return InMemoryIdentity()
    path = tmp_path / "rinthel.db"
    database.migrate(path)
    return SqliteIdentity(path)


def _logs_in(identity, username, password) -> bool:
    user = identity.get_user_by_username(username)
    return user is not None and not user.disabled and tokens.verify_password(password, user.password_hash)


def test_without_any_user_it_creates_an_admin_that_logs_in(identity):
    password = reset_admin(identity, "admin")

    assert identity.has_admin()
    assert _logs_in(identity, "admin", password)


def test_an_existing_admin_gets_a_new_password_and_loses_their_refresh_tokens(identity):
    old = identity.create_user(username="admin", password_hash=tokens.hash_password("vieja-pw"), role="admin")
    identity.store_refresh_token(user_id=old.id, token_hash="t1", expires_at=FAR)

    password = reset_admin(identity, "admin")

    assert not _logs_in(identity, "admin", "vieja-pw")
    assert _logs_in(identity, "admin", password)
    assert identity.get_refresh_token("t1").revoked_at is not None


def test_a_disabled_admin_is_enabled_again(identity):
    admin = identity.create_user(username="admin", password_hash="h", role="admin")
    identity.update_user(admin.id, disabled=True)

    reset_admin(identity, "admin")

    assert identity.has_admin()


def test_a_member_with_that_username_is_promoted_not_duplicated(identity):
    identity.create_user(username="ana", password_hash="h", role="miembro")

    reset_admin(identity, "ana")

    assert [(u.username, u.role) for u in identity.list_users()] == [("ana", "admin")]


def test_the_first_admin_is_created_only_when_there_is_no_active_admin(identity):
    password = ensure_first_admin(identity)

    assert password is not None and _logs_in(identity, "admin", password)
    assert ensure_first_admin(identity) is None
    assert len(identity.list_users()) == 1


def test_the_first_admin_reuses_a_disabled_admin_user(identity):
    admin = identity.create_user(username="admin", password_hash="h", role="admin")
    identity.update_user(admin.id, disabled=True)

    password = ensure_first_admin(identity)

    assert _logs_in(identity, "admin", password)


def test_the_command_migrates_the_instance_db_and_prints_the_password_once(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "reset-admin", "--username", "root"]) == 0

    out = capsys.readouterr().out
    identity = SqliteIdentity(Instance(tmp_path).database_path)
    user = identity.get_user_by_username("root")
    assert user.is_active_admin
    password = next(w for w in out.split() if tokens.verify_password(w, user.password_hash))
    assert out.count(password) == 1


def test_the_command_fails_clearly_on_a_newer_schema(tmp_path, capsys):
    path = Instance(tmp_path).database_path
    database.migrate(path, migrations=(*database.MIGRATIONS, "SELECT 1;"))

    assert main(["--root", str(tmp_path), "reset-admin"]) == 1

    assert "schema version" in capsys.readouterr().err
