"""``POST /boot``/``/terminate``/``/reload``/``/install``: cada una corre su
comando de ``Lifecycle`` y devuelve ``{"results": [ServiceOutcome]}``. Con
otro comando o un cambio de Local model en curso, 409 ``lifecycle_busy``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from rinthel_tui.api.access import service
from rinthel_tui.api.deps import get_lifecycle
from rinthel_tui.api.lifecycle.dtos import InstallRequest, ServiceOutcome
from rinthel_tui.config import with_voice_from_instance
from rinthel_tui.lifecycle.commands import Lifecycle, LifecycleBusy
from rinthel_tui.lifecycle.domain.types import UnitOutcome

router = APIRouter()

Results = dict[str, list[ServiceOutcome]]


def wire(outcomes: list[UnitOutcome]) -> list[ServiceOutcome]:
    """Los ``UnitOutcome`` del dominio de lifecycle, a su forma en el wire."""
    return [ServiceOutcome(service=o.service, ok=o.ok, message=o.message) for o in outcomes]


async def _run(command: Callable[[], Awaitable[list[UnitOutcome]]]) -> Results:
    try:
        return {"results": wire(await command())}
    except LifecycleBusy as exc:
        raise HTTPException(409, "lifecycle_busy") from exc


@router.post("/boot", response_model=Results, dependencies=[Depends(service)])
async def boot(lifecycle: Lifecycle = Depends(get_lifecycle)):
    return await _run(lifecycle.boot)


@router.post("/terminate", response_model=Results, dependencies=[Depends(service)])
async def terminate(lifecycle: Lifecycle = Depends(get_lifecycle)):
    return await _run(lifecycle.terminate)


@router.post("/reload", response_model=Results, dependencies=[Depends(service)])
async def reload(lifecycle: Lifecycle = Depends(get_lifecycle)):
    return await _run(lifecycle.reload)


@router.post("/install", response_model=Results, dependencies=[Depends(service)])
async def install(request: Request, body: InstallRequest | None = None, lifecycle: Lifecycle = Depends(get_lifecycle)):
    """``{"voice": true}`` is INSTALL ``--voice`` (opt-in): afterwards the live
    ``cfg`` takes the voice models INSTALL left active, so routing and the
    next boot or reload see them."""
    voice = body is not None and body.voice
    results = await _run(lambda: lifecycle.install(voice=voice))
    if voice:
        request.app.state.cfg = with_voice_from_instance(request.app.state.cfg)
    return results
