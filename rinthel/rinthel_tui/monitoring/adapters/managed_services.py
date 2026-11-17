"""``ModelsSensor`` over the live ``cfg``, the active Local models and one GET
to each service's readiness URL (the same ``ready_url`` that boot waits on).

What gets reported depends on the Platform: ``llm`` always; ``stt``/``tts``
only with an active model and never on Windows (voice is Linux only); a
managed service only while it is enabled. The client groups and orders what
arrives and never adds a row of its own."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.services import DOCKER_SERVICES, LLAMA_SERVICE, MODEL_SERVICES
from rinthel_tui.monitoring.domain.types import CapabilityStatus, ModelsStatus, ServiceState, ServiceStatus

# Capability -> (active id or ``None``, why it cannot run or ``None``).
Resolve = Callable[[str], tuple[str | None, str | None]]

_VOICE = ("stt", "tts")


class ManagedServicesSensor:
    """``cfg_of`` is the live ``cfg``; ``resolve`` resolves the active Local
    model of a Capability against the catalog; ``http_ok`` is the ``Probe``
    of the ``Host``."""

    def __init__(
        self, cfg_of: Callable[[], RinthelConfig], resolve: Resolve, http_ok: Callable[[str], Awaitable[bool]]
    ) -> None:
        self._cfg_of = cfg_of
        self._resolve = resolve
        self._http_ok = http_ok

    async def read(self) -> ModelsStatus:
        cfg = self._cfg_of()
        services = [s for s in DOCKER_SERVICES if s.enabled_of(cfg)]
        voice = () if cfg.platform == "windows" else _VOICE
        llm, *rest = await asyncio.gather(
            self._llm(cfg),
            *(self._voice(cfg, capability) for capability in voice),
            *(self._state(s.ready_url_of(cfg) if s.ready_url_of else None) for s in services),
        )
        lines, rows = rest[:len(voice)], rest[len(voice):]
        return ModelsStatus(
            capabilities=[llm, *(line for line in lines if line is not None)],
            services=[ServiceStatus(s.display_name, state) for s, state in zip(services, rows, strict=True)],
        )

    async def _llm(self, cfg: RinthelConfig) -> CapabilityStatus:
        model, error = self._resolve("llm")
        if error is not None or not LLAMA_SERVICE.enabled_of(cfg):
            return CapabilityStatus("llm", model, "off", error)
        ready_url = LLAMA_SERVICE.ready_url_of(cfg) if LLAMA_SERVICE.ready_url_of else None
        return CapabilityStatus("llm", model, await self._state(ready_url))

    async def _voice(self, cfg: RinthelConfig, capability: str) -> CapabilityStatus | None:
        """Voice is opt-in: without an active key it is not listed. An active
        id that cannot run is ``off`` with why; otherwise its service answers
        (``ready``) or not (``down``)."""
        model, error = self._resolve(capability)
        if model is None:
            return None
        if error is not None:
            return CapabilityStatus(capability, model, "off", error)
        service = MODEL_SERVICES[capability]  # type: ignore[index]
        ready_url = service.ready_url_of(cfg) if service.ready_url_of else None
        return CapabilityStatus(capability, model, await self._state(ready_url))

    async def _state(self, ready_url: str | None) -> ServiceState:
        if ready_url is None:
            return "down"
        return "ready" if await self._http_ok(ready_url) else "down"
