"""Access policy de cada ruta: una dependency de FastAPI que decide solo
*quién* llama. Cada ruta declara exactamente una — como parámetro tipado del
handler o en ``dependencies=[...]`` — y la security de la ruta en OpenAPI sale
de esa misma declaración (``openapi.py``).

Policies (ADR 0003): ``public``, ``service`` (the TUI or Deck, with the
service secret), ``service_as_user`` (Deck acting for a user named in
``X-Rinthel-User-Id``; only ``GET /identity/me/session-principal``), ``user``
(Panel token) and ``admin``. ``any_of`` combines them as alternatives and
counts as one (``service_or_admin``). User policies return a fresh
``UserRow`` read from the Identity store, never the token's claims."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Iterable

from fastapi import Depends, FastAPI, HTTPException, WebSocketException
from fastapi.routing import APIRoute
from starlette.requests import HTTPConnection
from starlette.routing import BaseRoute

from rinthel_tui.api.deps import state
from rinthel_tui.config import RinthelConfig
from rinthel_tui.identity import tokens as identity_tokens
from rinthel_tui.identity.domain.types import UserRow

_cfg = state("cfg")

SERVICE_SECRET_SCHEME = {
    "type": "apiKey",
    "in": "header",
    "name": "X-Rinthel-Service-Secret",
    "description": "Secreto compartido para auth backend-a-backend (TUI o Deck → daemon).",
}

BEARER_JWT_SCHEME = {
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT",
    "description": "Panel token JWT emitido por POST /identity/login.",
}

USER_ID_SCHEME = {
    "type": "apiKey",
    "in": "header",
    "name": "X-Rinthel-User-Id",
    "description": "Id del usuario en nombre del cual actúa Deck con el secreto de servicio.",
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


@_policy({"service_secret": SERVICE_SECRET_SCHEME, "acting_user": USER_ID_SCHEME})
def service_as_user(conn: HTTPConnection, cfg: RinthelConfig = Depends(_cfg)) -> UserRow:
    """``service`` acting for a user: the user travels only in
    ``X-Rinthel-User-Id``, never in the body, and is read again from the
    Identity store; disabled or deleted is a 401. Only
    ``GET /identity/me/session-principal`` declares it."""
    service(conn, cfg)
    try:
        user_id = int(conn.headers.get("x-rinthel-user-id", ""))
    except ValueError:
        raise HTTPException(401, "invalid or missing X-Rinthel-User-Id") from None
    found = conn.app.state.identity.get_user(user_id)
    if found is None or found.disabled:
        raise HTTPException(401, "invalid or missing X-Rinthel-User-Id")
    return found


@_policy({"bearer_jwt": BEARER_JWT_SCHEME})
def user(conn: HTTPConnection, cfg: RinthelConfig = Depends(_cfg)) -> UserRow:
    """A user with a Panel token. Only ``sub`` is taken from the token: the
    user is read again from the Identity store, so a deleted or disabled one
    is out on their next request even if the token has not expired."""
    header = conn.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        claims = identity_tokens.decode_access_token(
            secret=cfg.secrets.panel, token=header[7:], now=conn.app.state.clock.now()
        )
        user_id = int(claims["sub"])
    except (identity_tokens.InvalidToken, KeyError, ValueError) as exc:
        raise HTTPException(401, "invalid token") from exc
    found = conn.app.state.identity.get_user(user_id)
    if found is None or found.disabled:
        raise HTTPException(401, "invalid token")
    return found


@_policy({"bearer_jwt": BEARER_JWT_SCHEME})
def admin(conn: HTTPConnection, cfg: RinthelConfig = Depends(_cfg)) -> UserRow:
    """``user`` whose role is ``admin`` in the Identity store, not in the token."""
    caller = user(conn, cfg)
    if not caller.is_admin:
        raise HTTPException(403, "admin required")
    return caller


def any_of(*policies: Callable) -> Callable:
    """Policies as alternatives: passes if any of them does not raise, and
    counts as a single policy. Its OpenAPI security lists each policy as an
    alternative (one entry per policy, not one requirement with every scheme,
    which would be AND). The error is the last policy's."""

    def combined(conn: HTTPConnection, cfg: RinthelConfig = Depends(_cfg)):
        last: HTTPException | WebSocketException | None = None
        for policy in policies:
            try:
                return policy(conn, cfg)
            except (HTTPException, WebSocketException) as exc:
                last = exc
        raise last  # type: ignore[misc]

    combined.schemes = {name: scheme for policy in policies for name, scheme in policy.schemes.items()}
    combined.security = [entry for policy in policies for entry in policy.security]
    return combined


service_or_admin = any_of(service, admin)


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
