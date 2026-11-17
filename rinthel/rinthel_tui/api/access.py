"""Access policy de cada ruta: una dependency de FastAPI que decide solo
*quién* llama. Cada ruta declara exactamente una — como parámetro tipado del
handler o en ``dependencies=[...]`` — y la security de la ruta en OpenAPI sale
de esa misma declaración (``openapi.py``).

Hoy hay dos: ``public`` y ``service`` (la TUI, con el secreto de servicio).
Las de usuario con Panel token se suman acá con la identidad."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Iterable

from fastapi import Depends, FastAPI, HTTPException, WebSocketException
from fastapi.routing import APIRoute
from starlette.requests import HTTPConnection
from starlette.routing import BaseRoute

from rinthel_tui.api.deps import state
from rinthel_tui.config import RinthelConfig

_cfg = state("cfg")

SERVICE_SECRET_SCHEME = {
    "type": "apiKey",
    "in": "header",
    "name": "X-Rinthel-Service-Secret",
    "description": "Secreto compartido para auth backend-a-backend (TUI → daemon).",
}


def _policy(schemes: dict[str, dict]) -> Callable[[Callable], Callable]:
    """Marca una dependency como Access policy y le cuelga sus schemes de
    OpenAPI (``schemes``) y la security que exige (``security``). Sin
    schemes, la security es ``[]``: la ruta no pide credenciales."""

    def mark(fn: Callable) -> Callable:
        fn.schemes = schemes
        fn.security = [{name: [] for name in schemes}] if schemes else []
        return fn

    return mark


@_policy({})
def public() -> None:
    """Cualquier Caller, anónimo incluido — solo la documentación en modo
    desarrollo (``RINTHEL_DAEMON_DOCS=1``)."""


@_policy({"service_secret": SERVICE_SECRET_SCHEME})
def service(conn: HTTPConnection, cfg: RinthelConfig = Depends(_cfg)) -> None:
    """La TUI: ``X-Rinthel-Service-Secret`` comparado en tiempo constante.
    Con el secreto configurado vacío no pasa nadie. Un handshake WebSocket no
    lleva headers custom desde un browser, así que ahí el secreto viaja en
    ``?token=`` y el rechazo es un close 4401 antes de ``accept()`` — uvicorn
    rechaza el handshake en vez de aceptar y cortar."""
    websocket = conn.scope["type"] == "websocket"
    expected = cfg.secrets.service
    given = conn.query_params.get("token", "") if websocket else conn.headers.get("x-rinthel-service-secret", "")
    if expected and hmac.compare_digest(given, expected):
        return
    if websocket:
        raise WebSocketException(4401, "invalid or missing service secret")
    raise HTTPException(401, "invalid or missing service secret")


def routes_of(app: FastAPI) -> list[BaseRoute]:
    """Las rutas de ``app`` con los routers incluidos aplanados (también los
    anidados) — FastAPI deja un ``_IncludedRouter`` por ``include_router`` en
    ``app.routes``."""
    return _flatten(app.routes)


def _flatten(routes: Iterable[BaseRoute]) -> list[BaseRoute]:
    flat: list[BaseRoute] = []
    for route in routes:
        included = getattr(route, "original_router", None)
        flat.extend([route] if included is None else _flatten(included.routes))
    return flat


def policies_of(route: BaseRoute) -> list[Callable]:
    """Las policies que ``route`` declara, en cualquiera de las dos formas."""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return []
    return [dep.call for dep in dependant.dependencies if hasattr(dep.call, "security")]


def apply_security(app: FastAPI, schema: dict) -> None:
    """Escribe en ``schema`` los schemes y la security de cada ruta que
    declara policy."""
    schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
    for route in routes_of(app):
        policies = policies_of(route)
        if not isinstance(route, APIRoute) or not route.include_in_schema or len(policies) != 1:
            continue
        (policy,) = policies
        schemes.update(policy.schemes)
        for method in route.methods:
            operation = schema["paths"][route.path_format][method.lower()]
            operation["security"] = policy.security
