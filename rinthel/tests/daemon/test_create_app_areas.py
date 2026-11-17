"""``create_app`` es la lista ordenada de áreas: no construye módulos de dominio
ni importa nada de ``<modulo>/domain``; cada área los arma en su ``compose``."""

import ast
from pathlib import Path

from rinthel_tui import api
from rinthel_tui.api.access import routes_of


def test_create_app_module_imports_no_domain_module():
    tree = ast.parse(Path(api.__file__).read_text())
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and ".domain" in node.module
    }

    assert imported == set()


def test_the_daemon_serves_only_the_areas_of_the_trimmed_skeleton(app):
    paths = {route.path for route in routes_of(app)}

    assert paths == {
        "/theme", "/config", "/ws/monitor", "/boot", "/terminate", "/reload", "/install",
        "/secrets/rotate", "/openapi.json", "/model-provider/routing", "/models", "/models/activate",
    }
