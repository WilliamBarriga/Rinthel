"""Admin access from the host, without HTTP: the first admin of INSTALL and
``reset-admin``, the only recovery. The new password is generated here and
only whoever runs the command sees it. Both talk to ``Identity`` directly,
outside the self-lockout and last-admin guards (they only ever add an
active admin)."""

from __future__ import annotations

from rinthel_tui.identity import tokens
from rinthel_tui.identity.domain.ports import Identity

FIRST_ADMIN = "admin"


def reset_admin(identity: Identity, username: str) -> str:
    """Leaves ``username`` as an active admin with a random password and
    returns it. Creates the user if missing; otherwise (admin, member or
    disabled) sets the password, enables them, makes them admin and revokes
    their refresh tokens."""
    password = tokens.random_password()
    password_hash = tokens.hash_password(password)
    with identity.transaction() as tx:
        user = tx.get_user_by_username(username)
        if user is None:
            tx.create_user(username=username, password_hash=password_hash, role="admin", notes="created by reset-admin")
        else:
            tx.set_password(user.id, password_hash)
            tx.update_user(user.id, role="admin", disabled=False)
            tx.revoke_all_refresh_tokens_for_user(user.id)
    return password


def ensure_first_admin(identity: Identity) -> str | None:
    """With no active admin, ``admin`` becomes one and its password is
    returned (shown once by INSTALL). With one, nothing changes: ``None``."""
    if identity.has_admin():
        return None
    return reset_admin(identity, FIRST_ADMIN)
