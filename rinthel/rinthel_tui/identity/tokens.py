"""Identity cryptography: password hash (stdlib) and Panel token (JWT via
PyJWT).

Two different secrets, on purpose:

- ``password_hash``: ``hashlib.scrypt`` with a per-user salt. A password a
  human picked has low entropy and must be expensive to brute-force.
- Refresh token: generated here (``secrets.token_urlsafe``), high entropy.
  Its plain SHA-256 is stored, with no artificial cost (it is not a password;
  scrypt would be cost without benefit).

The access token carries ``sub``, ``username`` and ``role``. It is not the
authority: every policy reads the user again from the Identity store.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(hash_hex) // 2,
        )
        return hmac.compare_digest(derived.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def random_password() -> str:
    """The one-time password of the first admin and of ``reset-admin``."""
    return secrets.token_urlsafe(12)


# ── Access token (stateless JWT, validated locally by Deck) ─────────────


def issue_access_token(*, secret: str, user_id: int, username: str, role: str, ttl_seconds: int, now: datetime) -> str:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "typ": "access",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class InvalidToken(Exception):
    pass


def decode_access_token(*, secret: str, token: str, now: datetime) -> dict[str, Any]:
    """``exp`` is compared with the ``now`` given, not with PyJWT's clock."""
    if not secret:
        raise InvalidToken("no panel secret configured")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False})
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if "exp" not in payload or now.timestamp() >= payload["exp"]:
        raise InvalidToken("token expired")
    if payload.get("typ") != "access":
        raise InvalidToken("not an access token")
    return payload


# ── Refresh token (opaque, stored as a hash, rotates on every use) ──────


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_expiry(ttl_seconds: int, *, now: datetime) -> str:
    return (now + timedelta(seconds=ttl_seconds)).isoformat()


def is_expired(expires_at_iso: str, *, now: datetime) -> bool:
    expires_at = datetime.fromisoformat(expires_at_iso)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return now >= expires_at
