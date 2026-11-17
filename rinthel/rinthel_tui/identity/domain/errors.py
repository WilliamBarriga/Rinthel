"""Identity domain errors. Their HTTP answer is the identity error table
(``api/identity/routes.py::ERRORS``)."""

from __future__ import annotations


class UsernameTaken(Exception):
    """There is already a user with that ``username``."""


class IdentityUnavailable(Exception):
    """The Identity store could not serve the call (the file is locked past
    ``busy_timeout``, unreadable, or the disk failed)."""


class SelfLockout(Exception):
    """An admin tried to disable, delete or demote themselves."""


class LastAdmin(Exception):
    """The change would leave the Instance without an active admin."""


class DeckSessionsError(Exception):
    """Deck did not retire the Sessions: it is down, answered 5xx, or refused
    the credential or the request."""


class SessionsNotRetired(Exception):
    """A user was not deleted because Deck did not retire their Sessions.
    Nothing changed on the daemon side; the deletion can be retried."""

    def __init__(self, user_id: int, cause: Exception) -> None:
        super().__init__(
            f"user {user_id} was not deleted: Deck did not retire their Sessions ({cause}); "
            "nothing changed, retry once Deck is up"
        )
        self.user_id = user_id
