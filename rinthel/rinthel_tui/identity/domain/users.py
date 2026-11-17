"""User administration use cases: the admin edits and deletes users
(creating one is ``Identity.create_user`` directly). Each one runs in one ``Identity.transaction()``, where the guards
count active admins without another writer getting in.

- **Self-lockout:** an admin cannot disable, delete or demote themselves.
- **Last admin:** no change may leave the Instance without an active admin.
- **Disable revokes:** disabling a user revokes their refresh tokens, so they
  lose access when their access token expires and every policy rejects them
  on their next request.
- **Delete:** Deck's Sessions of the user are retired first (a network call,
  idempotent, outside the transaction); only if Deck answered is the user
  deleted, in its own transaction. Without Deck (``sessions`` is ``None``)
  there are no Sessions to retire.

The first admin of INSTALL and ``reset-admin`` talk to ``Identity`` directly
(``identity/admin.py``) and do not go through these guards.
"""

from __future__ import annotations

from rinthel_tui.identity.domain.errors import DeckSessionsError, LastAdmin, SelfLockout, SessionsNotRetired
from rinthel_tui.identity.domain.ports import DeckSessions, Identity, IdentityTx
from rinthel_tui.identity.domain.types import Role, UserRow


def _guard_admin_loss(tx: IdentityTx, acting_id: int, user: UserRow) -> None:
    """Called when ``user`` would stop being an active admin: rejects it if
    that is the caller or if no other active admin would remain."""
    if not user.is_active_admin:
        return
    if acting_id == user.id:
        raise SelfLockout("an admin cannot disable, delete or demote themselves")
    if tx.count_active_admins(excluding=user.id) == 0:
        raise LastAdmin("the Instance cannot be left without an active admin")


def update_user(
    identity: Identity,
    acting_id: int,
    user_id: int,
    *,
    role: Role | None = None,
    notes: str | None = None,
    disabled: bool | None = None,
    password_hash: str | None = None,
) -> UserRow | None:
    """Changes only what is passed; ``None`` if the user does not exist.
    Disabling revokes the user's refresh tokens."""
    with identity.transaction() as tx:
        user = tx.get_user(user_id)
        if user is None:
            return None
        if disabled is True or (role is not None and role != "admin"):
            _guard_admin_loss(tx, acting_id, user)
        tx.update_user(user_id, role=role, notes=notes, disabled=disabled)
        if password_hash is not None:
            tx.set_password(user_id, password_hash)
        if disabled is True:
            tx.revoke_all_refresh_tokens_for_user(user_id)
        return tx.get_user(user_id)


def delete_user(identity: Identity, sessions: DeckSessions | None, acting_id: int, user_id: int) -> bool:
    """Deletes ``user_id`` and returns ``True``; ``False`` if it does not
    exist. The guards are checked before Deck is called (nothing is retired
    for a deletion the guard would reject) and again inside the deletion.
    ``SessionsNotRetired`` if Deck fails: the user stays."""
    with identity.transaction() as tx:
        user = tx.get_user(user_id)
        if user is None:
            return False
        _guard_admin_loss(tx, acting_id, user)
    if sessions is not None:
        try:
            sessions.retire_user_sessions(user_id)
        except DeckSessionsError as exc:
            raise SessionsNotRetired(user_id, exc) from exc
    with identity.transaction() as tx:
        user = tx.get_user(user_id)
        if user is None:
            return False
        _guard_admin_loss(tx, acting_id, user)
        tx.delete_user(user_id)
    return True
