"""The rules of Local models: which one is active for a Capability, what route
Deck gets for it, and the switch (kill, spawn, ready, rollback)."""

from __future__ import annotations

from rinthel_tui.models.domain.errors import CatalogUnavailable, NotActivable, TurnsInFlight, UnknownModel
from rinthel_tui.models.domain.ports import ActiveModels, Catalog, ModelService, Turns
from rinthel_tui.models.domain.types import Active, Capability, CatalogEntry, LocalModel, Route, Switched


def resolve(catalog: Catalog, active: ActiveModels, capability: Capability) -> Active:
    """The active Local model of ``capability`` if it can run. Never raises:
    an unknown id, an invalid entry or an unreadable catalog leave no model
    and a warning, and the managed service does not start."""
    model_id = active.get(capability)
    if model_id is None:
        return Active(None, None, f"sin Local model activo para {capability}: elegí uno con «models use <id>»")
    try:
        entry = _find(catalog.entries(), model_id)
    except CatalogUnavailable as exc:
        return Active(model_id, None, f"catálogo de Local models ilegible: {exc}")
    if entry is None:
        return Active(model_id, None, f"Local model activo desconocido: {model_id} (no está en el catálogo)")
    if not entry.activable or entry.model is None:
        return Active(model_id, None, f"Local model activo {model_id} no activable: {entry.problem}")
    if entry.model.capability != capability:
        return Active(model_id, None, f"Local model activo {model_id} es de {entry.model.capability}, no de {capability}")
    return Active(model_id, entry.model)


def route(model: LocalModel, *, host_address: str, port: int) -> Route:
    """The route of ``model`` as Deck reaches it: the address the daemon gives
    Deck for the host (``deck.host_address``) and the service port."""
    return Route(
        url=f"http://{host_address}:{port}",
        model=model.id,
        context_window=model.context_window,
        reasoning_format=model.reasoning_format,
    )


def activable(catalog: Catalog, model_id: str) -> LocalModel:
    """The model behind ``model_id``, or ``UnknownModel``/``NotActivable``."""
    entry = _find(catalog.entries(), model_id)
    if entry is None:
        raise UnknownModel(model_id)
    if not entry.activable or entry.model is None:
        raise NotActivable(entry.problem or "entrada inválida")
    return entry.model


class ModelSwitch:
    """Changes the active Local model of a Capability: kill, spawn and wait
    for the new one; if it does not come up, the previous one is restarted
    (rollback) and stays active. Exclusion against other lifecycle commands
    is the caller's (the global lifecycle lock)."""

    def __init__(
        self,
        catalog: Catalog,
        active: ActiveModels,
        services: dict[Capability, ModelService],
        turns: Turns,
    ) -> None:
        self._catalog = catalog
        self._active = active
        self._services = services
        self._turns = turns

    async def activate(self, model_id: str) -> Switched:
        model = activable(self._catalog, model_id)
        capability = model.capability
        service = self._service(capability)
        # Only llama-server reports turns: a voice switch does not wait for them.
        if capability == "llm" and await self._turns.in_flight():
            raise TurnsInFlight()
        previous = resolve(self._catalog, self._active, capability).model
        run = await service.restart(model)
        if run.ok:
            self._active.set(capability, model.id)
            return Switched(ok=True, active=model.id, rolled_back=None, runs=(run,), model=model, capability=capability)
        if previous is None:
            return Switched(
                ok=False, active=self._active.get(capability), rolled_back=None, runs=(run,), capability=capability,
            )
        restored = await service.restart(previous)
        return Switched(
            ok=False, active=previous.id, rolled_back=restored.ok, runs=(run, restored), model=previous,
            capability=capability,
        )

    async def deactivate(self, capability: Capability) -> Switched:
        """Turns ``capability`` off (``models off``): stops its service and
        drops its key. If the service does not stop, the key stays."""
        service = self._service(capability)
        run = await service.stop()
        if run.ok:
            self._active.clear(capability)
            return Switched(ok=True, active=None, rolled_back=None, runs=(run,), capability=capability)
        return Switched(
            ok=False, active=self._active.get(capability), rolled_back=None, runs=(run,), capability=capability,
        )

    def _service(self, capability: Capability) -> ModelService:
        service = self._services.get(capability)
        if service is None:
            raise NotActivable(f"la Capability {capability} no tiene managed service")
        reason = service.unavailable()
        if reason is not None:
            raise NotActivable(reason)
        return service


def _find(entries: list[CatalogEntry], model_id: str) -> CatalogEntry | None:
    return next((entry for entry in entries if entry.id == model_id), None)

