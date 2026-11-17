"""Inventario de rutas contra su Access policy: cada ruta declara
exactamente una, sin credenciales la rechaza y su security en
``/openapi.json`` es la que la policy declara. El handshake de
``/ws/monitor`` se cubre aparte (``test_ws_monitor.py``)."""

import re

from fastapi.routing import APIRoute, APIWebSocketRoute

from rinthel_tui.api import access
from rinthel_tui.api.access import policies_of, routes_of


def _http_routes(app) -> list[tuple[str, str, APIRoute]]:
    return [
        (method, route.path_format, route)
        for route in routes_of(app)
        if isinstance(route, APIRoute)
        for method in sorted(route.methods)
    ]


def _guarded(app) -> list[tuple[str, str, APIRoute]]:
    return [(m, p, r) for m, p, r in _http_routes(app) if policies_of(r) != [access.public]]


def test_no_route_is_public_outside_development_docs(app):
    public = {(m, p) for m, p, r in _http_routes(app) if policies_of(r) == [access.public]}
    assert public == set()


def test_every_route_declares_exactly_one_policy(app):
    wrong = {(m, p): len(policies_of(r)) for m, p, r in _http_routes(app) if len(policies_of(r)) != 1}
    assert wrong == {}


def test_every_route_is_http_or_the_ws_monitor(app):
    others = [r.path for r in routes_of(app) if not isinstance(r, APIRoute) and r.path != "/ws/monitor"]
    assert others == []


def test_every_guarded_route_rejects_a_caller_without_credentials(app, client):
    accepted = {}
    for method, path, _ in _guarded(app):
        status = client.request(method, re.sub(r"\{[^}]+\}", "1", path)).status_code
        if status not in (401, 403):
            accepted[(method, path)] = status
    assert accepted == {}


def test_openapi_security_of_every_route_is_the_one_its_policy_declares(app, client, service_headers):
    paths = client.get("/openapi.json", headers=service_headers).json()["paths"]
    mismatched = {}
    for method, path, route in _http_routes(app):
        if not route.include_in_schema:
            continue
        (policy,) = policies_of(route)
        documented = paths[path][method.lower()].get("security")
        if documented != policy.security:
            mismatched[(method, path)] = (documented, policy.security)
    assert mismatched == {}


def test_ws_monitor_declares_the_service_policy(app):
    (route,) = [r for r in routes_of(app) if isinstance(r, APIWebSocketRoute) and r.path == "/ws/monitor"]
    assert policies_of(route) == [access.service]
