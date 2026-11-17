"""Local models over HTTP.

- ``GET /model-provider/routing`` (``service``): where Deck sends each
  Capability, straight to the managed service, built with
  ``deck.host_address``, and where Understory is for Memoria
  (``understory_url``, per Platform). It describes what runs: the live
  ``cfg``.
- ``GET /models`` and ``POST /models/activate`` (``admin``): the
  catalog and the switch (kill, spawn, ready, rollback) under the global
  lifecycle lock; 409 ``lifecycle_busy`` or ``turns_in_flight`` (``llm``
  only). Voice (``stt``/``tts``) switches the same way, Linux only.
- ``POST /models/off`` (``admin``): ``stt`` or ``tts`` off, same lock."""

from __future__ import annotations

from collections.abc import Coroutine
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from rinthel_tui.api.access import admin, service
from rinthel_tui.api.deps import state
from rinthel_tui.api.lifecycle.routes import wire
from rinthel_tui.api.models.dtos import ActivateRequest, ActivateResult, ModelListing, OffRequest, Routing
from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.commands import LifecycleBusy, LifecycleLock
from rinthel_tui.lifecycle.domain.types import UnitOutcome
from rinthel_tui.lifecycle.services import MODEL_SERVICES, understory_url
from rinthel_tui.models.domain.errors import CatalogUnavailable, NotActivable, TurnsInFlight, UnknownModel
from rinthel_tui.models.domain.models import route
from rinthel_tui.models.domain.types import CAPABILITIES, Switched

_cfg = state("cfg")
_area = state("models")
_lock = state("lifecycle_lock")

router = APIRouter()


@router.get("/model-provider/routing", response_model=Routing, dependencies=[Depends(service)])
def routing(cfg: RinthelConfig = Depends(_cfg)):
    capabilities = {}
    for capability in CAPABILITIES:
        model, managed = cfg.model_of(capability), MODEL_SERVICES[capability]
        # A disabled llama-server, or voice off Linux, has no route.
        if model is not None and managed.enabled_of(cfg) and managed.port_of is not None:
            capabilities[capability] = asdict(
                route(model, host_address=cfg.deck.host_address, port=managed.port_of(cfg))
            )
    return {"capabilities": capabilities, "understory_url": understory_url(cfg)}


@router.get("/models", response_model=ModelListing, dependencies=[Depends(admin)])
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


@router.post("/models/activate", response_model=ActivateResult, dependencies=[Depends(admin)])
async def activate(
    body: ActivateRequest, area=Depends(_area), lock: LifecycleLock = Depends(_lock)
):
    switched = await _switching(lock, area.switch.activate(body.id))
    warnings = area.adopt(switched.model) if switched.ok and switched.model is not None else []
    return _result(switched, warnings)


@router.post("/models/off", response_model=ActivateResult, dependencies=[Depends(admin)])
async def off(body: OffRequest, area=Depends(_area), lock: LifecycleLock = Depends(_lock)):
    """Turns ``stt`` or ``tts`` off: stops its service and drops its key from
    ``instance.toml``. Same lock as the switch; ``llm`` is never off."""
    switched = await _switching(lock, area.switch.deactivate(body.capability))
    if switched.ok:
        area.drop(body.capability)
    return _result(switched, [])


async def _switching(lock: LifecycleLock, change: Coroutine[Any, Any, Switched]) -> Switched:
    try:
        async with lock.hold():
            return await change
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
    finally:
        change.close()


def _result(switched: Switched, warnings: list[str]) -> dict:
    name = MODEL_SERVICES[switched.capability].display_name
    results = [
        UnitOutcome(service=name, ok=run.ok, message=" — ".join(run.messages) or "sin mensaje") for run in switched.runs
    ]
    return {
        "ok": switched.ok,
        "active": switched.active,
        "rolled_back": switched.rolled_back,
        "results": wire(results),
        "warnings": warnings,
    }
