"""``ServiceReadiness`` sobre un GET a la URL de readiness del servicio: el
mismo ``ready_url`` que ``phase_wait_ready`` espera en boot/reload, una sola
vez y sin backoff."""

from __future__ import annotations

from collections.abc import Awaitable, Callable


class HttpReadiness:
    """``url_of`` da la URL vigente (sale del ``cfg`` vivo: un ``POST /config``
    que cambia el puerto se ve en la próxima muestra). ``http_ok`` es el que
    pregunta: la composición le pasa el ``Probe.http_ok`` del ``Host``."""

    def __init__(self, url_of: Callable[[], str], http_ok: Callable[[str], Awaitable[bool]]) -> None:
        self._url_of = url_of
        self._http_ok = http_ok

    async def ready(self) -> bool:
        return await self._http_ok(self._url_of())
