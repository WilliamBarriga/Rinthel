"""``POST /boot``/``/terminate``/``/reload``/``/install``: cada una corre su
comando de ``Lifecycle`` y devuelve ``{"results": [ServiceOutcome]}``."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rinthel_tui.api.access import service
from rinthel_tui.api.deps import get_lifecycle
from rinthel_tui.api.lifecycle.dtos import ServiceOutcome
from rinthel_tui.lifecycle.commands import Lifecycle
from rinthel_tui.lifecycle.domain.types import UnitOutcome

router = APIRouter()

Results = dict[str, list[ServiceOutcome]]


def _wire(outcomes: list[UnitOutcome]) -> Results:
    """Los ``UnitOutcome`` del dominio de lifecycle, a su forma en el wire."""
    return {"results": [ServiceOutcome(service=o.service, ok=o.ok, message=o.message) for o in outcomes]}


@router.post("/boot", response_model=Results, dependencies=[Depends(service)])
async def boot(lifecycle: Lifecycle = Depends(get_lifecycle)):
    return _wire(await lifecycle.boot())


@router.post("/terminate", response_model=Results, dependencies=[Depends(service)])
async def terminate(lifecycle: Lifecycle = Depends(get_lifecycle)):
    return _wire(await lifecycle.terminate())


@router.post("/reload", response_model=Results, dependencies=[Depends(service)])
async def reload(lifecycle: Lifecycle = Depends(get_lifecycle)):
    return _wire(await lifecycle.reload())


@router.post("/install", response_model=Results, dependencies=[Depends(service)])
async def install(lifecycle: Lifecycle = Depends(get_lifecycle)):
    return _wire(await lifecycle.install())
