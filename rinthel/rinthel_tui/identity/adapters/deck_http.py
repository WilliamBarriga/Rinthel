"""``DeckSessions`` over Deck's HTTP API: ``POST /api/agent/retire-sessions``
with ``X-Rinthel-Service-Secret`` and the user in ``X-Rinthel-User-Id``,
never in the body. Deck answers ``{"retired": n}``. httpx lives only here:
every failure comes out as ``DeckSessionsError``. ``client`` carries Deck's
``base_url`` and timeouts."""

from __future__ import annotations

import httpx

from rinthel_tui.identity.domain.errors import DeckSessionsError

SERVICE_SECRET_HEADER = "X-Rinthel-Service-Secret"
USER_ID_HEADER = "X-Rinthel-User-Id"
RETIRE_PATH = "/api/agent/retire-sessions"


class HttpDeckSessions:
    def __init__(self, client: httpx.Client, *, service_secret: str) -> None:
        self._client = client
        self._secret = service_secret

    def retire_user_sessions(self, user_id: int) -> int:
        headers = {SERVICE_SECRET_HEADER: self._secret, USER_ID_HEADER: str(user_id)}
        try:
            response = self._client.post(RETIRE_PATH, json={}, headers=headers)
        except httpx.TransportError as exc:
            raise DeckSessionsError(f"deck unreachable: {type(exc).__name__}") from exc
        if not response.is_success:
            raise DeckSessionsError(f"deck answered {response.status_code}")
        try:
            return int(response.json()["retired"])
        except (ValueError, KeyError, TypeError) as exc:
            raise DeckSessionsError("deck answered a retirement without a count") from exc
