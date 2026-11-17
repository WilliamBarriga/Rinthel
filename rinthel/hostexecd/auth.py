"""The shared token of ``hostexecd``: written by INSTALL in the root ``.env``,
handed to this process by the daemon that starts it, sent by Deck in a header
of every request and compared in constant time."""

from __future__ import annotations

import hmac
import os

TOKEN_HEADER = "X-Rinthel-Token"


def expected_token() -> str | None:
    """The configured token, or ``None`` when there is none."""
    token = os.getenv("RINTHEL_HOSTEXECD_TOKEN", "").strip()
    return token or None


def check_token(received: str | None) -> bool:
    """True only when ``received`` matches the expected token
    (``hmac.compare_digest``, so timing does not leak it).

    Without a configured token it fails closed and never authenticates, not
    even an empty header: the Instance's containers reach the host loopback,
    so an open ``hostexecd`` would answer any of them."""
    expected = expected_token()
    if expected is None or not received:
        return False
    return hmac.compare_digest(received, expected)
