"""Local models over HTTP.

- ``GET /model-provider/routing`` (``service``): where Deck sends each
  Capability, straight to the managed service, built with
  ``deck.host_address``. It describes what runs: the live ``cfg``.
- ``GET /models`` and ``POST /models/activate`` (``model_admin``): the
  catalog and the switch (kill, spawn, ready, rollback) under the global
  lifecycle lock; 409 ``lifecycle_busy`` or ``turns_in_flight``."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from rinthel_tui.api.access import service
from rinthel_tui.api.deps import state
from rinthel_tui.api.lifecycle.routes import wire
from rinthel_tui.api.models.dtos import ActivateRequest, ActivateResult, ModelListing, Routing
from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.commands import LifecycleBusy, LifecycleLock
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.models.domain.errors import CatalogUnavailable, NotActivable, TurnsInFlight, UnknownModel
from rinthel_tui.models.domain.models import route
from rinthel_tui.models.domain.types import CAPABILITIES

# The policy that guards model administration (listing and switch). The
# decisions make it admin-only; until the ``admin`` policy exists in
# ``api/access.py`` the service (the TUI) holds it. Swapping this one name
# for ``admin`` is the whole change.
model_admin = service

_cfg = state("cfg")
_area = state("models")
_lock = state("lifecycle_lock")

router = APIRouter()


@router.get("/model-provider/routing", response_model=Routing, dependencies=[Depends(service)])
def routing(cfg: RinthelConfig = Depends(_cfg)):
    capabilities = {}
    if cfg.local_model is not None and cfg.llama.enabled:
        capabilities["llm"] = asdict(route(cfg.local_model, host_address=cfg.deck.host_address, port=cfg.llama.port))
    return {"capabilities": capabilities}


@router.get("/models", response_model=ModelListing, dependencies=[Depends(model_admin)])
def listing(area=Depends(_area)):
    try:
        entries = area.catalog.entries()
    except CatalogUnavailable as exc:
        raise HTTPException(503, f"catalog_unavailable: {exc}") from exc
    return {
        "active": {capability: area.active.get(capability) for capability in CAPABILITIES},
        "models": [
            {
                "id": entry.id,
                "name": entry.model.name if entry.model else None,
                "capability": entry.model.capability if entry.model else None,
                "activable": entry.activable,
                "problem": entry.problem,
                "context_window": entry.model.context_window if entry.model else None,
                "reasoning_format": entry.model.reasoning_format if entry.model else None,
            }
            for entry in entries
        ],
    }


@router.post("/models/activate", response_model=ActivateResult, dependencies=[Depends(model_admin)])
async def activate(
    body: ActivateRequest, area=Depends(_area), lock: LifecycleLock = Depends(_lock)
):
    try:
        async with lock.hold():
            switched = await area.switch.activate(body.id)
    except LifecycleBusy as exc:
        raise HTTPException(409, "lifecycle_busy") from exc
    except TurnsInFlight as exc:
        raise HTTPException(409, "turns_in_flight") from exc
    except UnknownModel as exc:
        raise HTTPException(404, "unknown_model") from exc
    except NotActivable as exc:
        raise HTTPException(422, f"not_activable: {exc}") from exc
    except CatalogUnavailable as exc:
        raise HTTPException(503, f"catalog_unavailable: {exc}") from exc
    warnings = area.adopt(switched.model) if switched.ok and switched.model is not None else []
    results = [
        UnitOutcome(service="llama-server", ok=run.ok, message=" — ".join(run.messages) or "sin mensaje")
        for run in switched.runs
    ]
    return {
        "ok": switched.ok,
        "active": switched.active,
        "rolled_back": switched.rolled_back,
        "results": wire(results),
        "warnings": warnings,
    }
