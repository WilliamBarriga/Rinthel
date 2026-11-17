"""Dependencias que las rutas piden por ``Depends`` — el estado de la app y los
colaboradores externos (Lifecycle). Los tests los reemplazan con
``app.dependency_overrides`` o sobre ``app.state``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request
from starlette.requests import HTTPConnection

from rinthel_tui.lifecycle import executor
from rinthel_tui.lifecycle.commands import Lifecycle


def get_lifecycle(request: Request) -> Lifecycle:
    """Lifecycle sobre el ``cfg`` vivo y el ``Host`` de la app."""
    state = request.app.state
    return Lifecycle(
        state.cfg,
        state.broadcaster.broadcast,
        execute=executor.bound_to(state.lifecycle_host),
        lock=state.lifecycle_lock,
    )


def state(attr: str) -> Callable[[HTTPConnection], Any]:
    """El getter de un estado que ``create_app`` siempre deja en ``app.state.<attr>``."""

    def dep(conn: HTTPConnection) -> Any:
        return getattr(conn.app.state, attr)

    return dep
