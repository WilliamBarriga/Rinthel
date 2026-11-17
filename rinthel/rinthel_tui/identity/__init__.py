"""Identity of the Instance: the users (``admin`` or ``miembro``), their
passwords and their Panel tokens, stored in ``rinthel.db`` (ADR 0007).

- ``domain/``: the ``Identity`` port, its types and errors, the user use
  cases with the last-admin and self-lockout guards, and the ``DeckSessions``
  port that retires a user's Sessions before the user is deleted.
- ``adapters/``: ``SqliteIdentity``, the HTTP adapter of ``DeckSessions`` and
  the in-memory doubles of both.
- ``tokens.py``: password hashing (``hashlib.scrypt``) and the Panel token
  (HS256 access JWT plus a rotating refresh token stored as a hash).
- ``admin.py`` and ``__main__.py``: the first admin of INSTALL and the local
  ``reset-admin`` command.
"""
