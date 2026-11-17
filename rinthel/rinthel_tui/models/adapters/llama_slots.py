"""``Turns`` over llama-server's ``GET /slots``: a turn is in flight while any
slot reports ``is_processing``. A llama-server that does not answer (down,
or the endpoint disabled) is generating nothing."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Callable


class LlamaSlotsTurns:
    def __init__(self, base_url_of: Callable[[], str], *, timeout: float = 2.0) -> None:
        self._base_url_of = base_url_of
        self._timeout = timeout

    async def in_flight(self) -> bool:
        return await asyncio.to_thread(self._read)

    def _read(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._base_url_of()}/slots", timeout=self._timeout) as response:
                slots = json.loads(response.read())
        except (OSError, ValueError, urllib.error.URLError):
            return False
        if not isinstance(slots, list):
            return False
        return any(isinstance(slot, dict) and slot.get("is_processing") is True for slot in slots)
