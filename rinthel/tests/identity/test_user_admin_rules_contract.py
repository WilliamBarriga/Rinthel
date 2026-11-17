"""The user administration rules (``identity/domain/users.py``) against both
``Identity`` adapters: the last-admin guard, which over HTTP only shows up
under a race (the caller is an active admin, so another one exists), and the
two admins that remove each other at once."""

import threading

import pytest

from rinthel_tui import database
from rinthel_tui.identity.adapters.memory import InMemoryDeckSessions, InMemoryIdentity
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.domain.errors import LastAdmin, SelfLockout, SessionsNotRetired
from rinthel_tui.identity.domain.users import delete_user, update_user


@pytest.fixture(params=["memory", "sqlite"])
def identity(request, tmp_path):
    if request.param == "memory":
        return InMemoryIdentity()
    path = tmp_path / "rinthel.db"
    database.migrate(path)
    return SqliteIdentity(path)


@pytest.fixture
def two_admins(identity):
    a = identity.create_user(username="a", password_hash="h", role="admin")
    b = identity.create_user(username="b", password_hash="h", role="admin")
    return a, b


@pytest.mark.parametrize("change", [{"disabled": True}, {"role": "miembro"}])
def test_the_last_active_admin_cannot_be_disabled_or_demoted(identity, two_admins, change):
    a, b = two_admins
    identity.update_user(a.id, disabled=True)  # ``a`` was disabled while their request was on its way

    with pytest.raises(LastAdmin):
        update_user(identity, a.id, b.id, **change)

    assert identity.get_user(b.id).is_active_admin


def test_the_last_active_admin_cannot_be_deleted_and_deck_is_not_called(identity, two_admins):
    a, b = two_admins
    identity.update_user(a.id, disabled=True)
    deck = InMemoryDeckSessions()

    with pytest.raises(LastAdmin):
        delete_user(identity, deck, a.id, b.id)

    assert identity.get_user(b.id) is not None
    assert deck.retire_calls == []


def test_self_lockout_wins_over_last_admin(identity, two_admins):
    a, _ = two_admins

    with pytest.raises(SelfLockout):
        update_user(identity, a.id, a.id, disabled=True)


def test_a_member_can_be_disabled_with_a_single_admin(identity):
    root = identity.create_user(username="root", password_hash="h", role="admin")
    ana = identity.create_user(username="ana", password_hash="h", role="miembro")

    assert update_user(identity, root.id, ana.id, disabled=True).disabled


def test_a_failed_deck_leaves_the_user(identity, two_admins):
    a, b = two_admins
    deck = InMemoryDeckSessions()
    deck.refuse = True

    with pytest.raises(SessionsNotRetired):
        delete_user(identity, deck, a.id, b.id)

    assert identity.get_user(b.id) is not None


def test_two_admins_disabling_each_other_at_once_leave_one_active(identity, two_admins):
    a, b = two_admins
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def disable(acting, target):
        barrier.wait()
        try:
            update_user(identity, acting, target, disabled=True)
            outcomes.append("ok")
        except LastAdmin:
            outcomes.append("last_admin")

    threads = [threading.Thread(target=disable, args=(a.id, b.id)), threading.Thread(target=disable, args=(b.id, a.id))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert sorted(outcomes) == ["last_admin", "ok"]
    assert identity.count_active_admins() == 1
