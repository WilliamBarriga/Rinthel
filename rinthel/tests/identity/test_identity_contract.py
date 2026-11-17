"""Contract of the ``Identity`` port: the same suite against the in-memory
double (so the fake does not lie) and against ``SqliteIdentity`` on a
temporary ``rinthel.db`` migrated by the real migrator."""

import threading
from datetime import UTC, datetime

import pytest

from rinthel_tui import database
from rinthel_tui.clock import ManualClock
from rinthel_tui.identity.adapters.memory import InMemoryIdentity
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.domain.errors import UsernameTaken

FAR = "2999-01-01T00:00:00+00:00"
START = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(params=["memory", "sqlite"])
def identity(request, tmp_path):
    clock = ManualClock(START)
    if request.param == "memory":
        return InMemoryIdentity(clock=clock)
    path = tmp_path / "rinthel.db"
    database.migrate(path)
    return SqliteIdentity(path, clock=clock)


def test_a_created_user_reads_back_by_id_and_by_username(identity):
    user = identity.create_user(username="ana", password_hash="hash1", role="miembro")

    assert identity.get_user(user.id) == user
    assert identity.get_user_by_username("ana") == user
    assert (user.username, user.role, user.notes, user.disabled, user.created_at) == (
        "ana", "miembro", "", False, START.isoformat(),
    )


def test_an_unknown_user_is_none(identity):
    assert identity.get_user(999) is None
    assert identity.get_user_by_username("nadie") is None


def test_users_are_listed_by_username(identity):
    identity.create_user(username="beto", password_hash="h", role="miembro")
    identity.create_user(username="ana", password_hash="h", role="miembro")

    assert [u.username for u in identity.list_users()] == ["ana", "beto"]


def test_username_is_unique(identity):
    identity.create_user(username="ana", password_hash="hash1", role="miembro")

    with pytest.raises(UsernameTaken):
        identity.create_user(username="ana", password_hash="hash2", role="admin")


def test_has_admin_ignores_disabled_admins(identity):
    assert identity.has_admin() is False
    admin = identity.create_user(username="root", password_hash="h", role="admin")
    assert identity.has_admin() is True

    identity.update_user(admin.id, disabled=True)

    assert identity.has_admin() is False
    assert identity.get_user(admin.id).disabled_at == START.isoformat()


def test_update_user_changes_only_what_is_passed(identity):
    user = identity.create_user(username="ana", password_hash="h", role="miembro", notes="vieja")

    identity.update_user(user.id, role="admin")
    assert (identity.get_user(user.id).role, identity.get_user(user.id).notes) == ("admin", "vieja")

    updated = identity.update_user(user.id, notes="nueva")
    assert (updated.role, updated.notes) == ("admin", "nueva")


def test_enabling_a_user_clears_disabled(identity):
    user = identity.create_user(username="ana", password_hash="h", role="miembro")
    identity.update_user(user.id, disabled=True)

    identity.update_user(user.id, disabled=False)

    assert identity.get_user(user.id).disabled is False


def test_update_of_an_unknown_user_is_none(identity):
    assert identity.update_user(999, notes="x") is None


def test_set_password_replaces_the_hash(identity):
    user = identity.create_user(username="ana", password_hash="viejo", role="miembro")

    identity.set_password(user.id, "nuevo")

    assert identity.get_user(user.id).password_hash == "nuevo"


def test_delete_user_takes_their_refresh_tokens(identity):
    user = identity.create_user(username="ana", password_hash="h", role="miembro")
    identity.store_refresh_token(user_id=user.id, token_hash="th1", expires_at=FAR)

    identity.delete_user(user.id)

    assert identity.get_user(user.id) is None
    assert identity.get_refresh_token("th1") is None


def test_a_stored_refresh_token_reads_back(identity):
    user = identity.create_user(username="ana", password_hash="h", role="miembro")

    identity.store_refresh_token(user_id=user.id, token_hash="th1", expires_at=FAR)

    token = identity.get_refresh_token("th1")
    assert (token.user_id, token.token_hash, token.issued_at, token.expires_at, token.revoked_at) == (
        user.id, "th1", START.isoformat(), FAR, None,
    )
    assert identity.get_refresh_token("otro") is None


def test_revoking_a_refresh_token_marks_it_and_keeps_it(identity):
    user = identity.create_user(username="ana", password_hash="h", role="miembro")
    identity.store_refresh_token(user_id=user.id, token_hash="th1", expires_at=FAR)

    identity.revoke_refresh_token("th1")

    assert identity.get_refresh_token("th1").revoked_at == START.isoformat()


def test_revoke_all_refresh_tokens_for_user_only_touches_that_user(identity):
    a = identity.create_user(username="a", password_hash="h", role="miembro")
    b = identity.create_user(username="b", password_hash="h", role="miembro")
    identity.store_refresh_token(user_id=a.id, token_hash="ta", expires_at=FAR)
    identity.store_refresh_token(user_id=b.id, token_hash="tb", expires_at=FAR)

    identity.revoke_all_refresh_tokens_for_user(a.id)

    assert identity.get_refresh_token("ta").revoked_at is not None
    assert identity.get_refresh_token("tb").revoked_at is None


def test_a_transaction_that_exits_with_an_exception_saves_nothing(identity):
    class Boom(Exception):
        pass

    with pytest.raises(Boom), identity.transaction() as tx:
        tx.create_user(username="ana", password_hash="h", role="miembro")
        raise Boom

    assert identity.list_users() == []


def test_a_transaction_that_exits_cleanly_saves_everything(identity):
    with identity.transaction() as tx:
        ana = tx.create_user(username="ana", password_hash="h", role="miembro")
        tx.store_refresh_token(user_id=ana.id, token_hash="t", expires_at=FAR)

    assert identity.get_refresh_token("t").user_id == identity.get_user_by_username("ana").id


def test_count_active_admins_ignores_members_and_disabled_admins(identity):
    assert identity.count_active_admins() == 0
    root = identity.create_user(username="root", password_hash="h", role="admin")
    other = identity.create_user(username="otro", password_hash="h", role="admin")
    identity.create_user(username="ana", password_hash="h", role="miembro")
    gone = identity.create_user(username="baja", password_hash="h", role="admin")
    identity.update_user(gone.id, disabled=True)

    assert identity.count_active_admins() == 2
    assert identity.count_active_admins(excluding=root.id) == 1
    assert identity.count_active_admins(excluding=other.id) == 1


def test_count_active_admins_works_inside_a_transaction(identity):
    identity.create_user(username="root", password_hash="h", role="admin")

    with identity.transaction() as tx:
        assert tx.count_active_admins() == 1


def test_a_transaction_holds_off_other_writers_until_it_ends(identity):
    """The last-admin guard counts inside a transaction: a concurrent write
    must wait for its end (``BEGIN IMMEDIATE`` on SQLite, a lock in memory)."""
    root = identity.create_user(username="root", password_hash="h", role="admin")
    done = threading.Event()

    def disable() -> None:
        identity.update_user(root.id, disabled=True)
        done.set()

    with identity.transaction() as tx:
        tx.count_active_admins()
        thread = threading.Thread(target=disable, daemon=True)
        thread.start()
        assert not done.wait(0.3), "a write must wait for the open transaction"
    assert done.wait(5)
    thread.join()
