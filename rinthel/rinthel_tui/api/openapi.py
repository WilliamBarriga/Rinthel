"""Security schemes del schema OpenAPI. `openapi_components` no es parámetro
válido de FastAPI() — se usa el patrón de override para inyectarlo en el
schema resultante."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

from rinthel_tui.api import access


def install_security_schemes(app: FastAPI) -> None:
    """Agrega al schema de ``app`` los security schemes y la security de
    cada ruta, derivados de la Access policy que declara
    (``access.apply_security``)."""
    original_openapi = app.openapi

    def openapi() -> dict:
        if not app.openapi_schema:
            app.openapi_schema = original_openapi()
        access.apply_security(app, app.openapi_schema)
        return app.openapi_schema

    app.openapi = openapi


def mount_docs(app: FastAPI, *, public: bool) -> None:
    """Monta ``/openapi.json`` como una ruta más, con su Access policy
    declarada: ``service_or_admin`` en producción, así el mapa de la API no queda
    público. Con ``public`` (``RINTHEL_DAEMON_DOCS=1``) monta además
    ``/docs`` y ``/redoc`` y las tres pasan a ``public`` — Swagger abre sin
    credenciales y Authorize manda las de cada ruta, que sigue aplicando su
    policy. Las tres quedan fuera del schema propio."""
    policy = access.public if public else access.service_or_admin

    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(policy)])
    def openapi_json() -> dict:
        return app.openapi()

    if not public:
        return

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(access.public)])
    def swagger() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")

    @app.get("/redoc", include_in_schema=False, dependencies=[Depends(access.public)])
    def redoc() -> HTMLResponse:
        return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")
