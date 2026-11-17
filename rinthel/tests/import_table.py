"""Tabla de imports permitidos por módulo (ADR 0004).

Un solo dato: ``RULES`` dice, por módulo, qué puede importar cada parte de él.
``tests/test_import_table.py`` la recorre con un único helper AST. Un módulo
nuevo del daemon es una fila acá (o una entrada en ``UNGUARDED`` con su motivo);
una excepción es un campo de la regla con su motivo al lado.

Las rutas son relativas a ``rinthel/`` (la raíz que contiene ``rinthel_tui/``). Los prefijos de módulo se comparan con límite de punto:
``rinthel_tui.clock`` cubre ``rinthel_tui.clock`` y ``rinthel_tui.clock.x``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Lo que un ``domain/`` no puede importar: infraestructura.
INFRA = frozenset({
    "fastapi", "starlette", "httpx", "sqlite3", "docker", "tomllib", "pathlib", "os", "io",
    "subprocess", "psutil", "urllib",
})

@dataclass(frozen=True)
class Rule:
    """Qué puede importar el código bajo ``scope``.

    - ``scope``: archivos o directorios (``*.py`` recursivo); ``exclude``, rutas que se saltan.
    - ``infra``: aplica ``INFRA`` (menos ``infra_allowed``, más ``infra_extra``) a las raíces importadas.
      ``infra_extra`` también vale sin ``infra``.
    - ``only``: si no es ``None``, todo import ``rinthel_tui.*`` debe caer bajo uno de estos prefijos;
      ``per_file`` suma prefijos a un archivo, con su motivo.
    - ``forbid``: prefijos vetados; ``forbid_except``, los que se salvan de ese veto.
    - ``no_adapters``: ningún import de un módulo ``.adapters``.
    - ``no_system_clock``: ninguna lectura de ``now()``/``utcnow()``/``today()`` que no sea de un ``Clock``.
    - ``no_foreign_errors``: ningún módulo ``*.errors`` bajo estos prefijos (incluido ``from x import errors``).
    """

    scope: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    infra: bool = False
    infra_allowed: frozenset[str] = frozenset()
    infra_extra: frozenset[str] = frozenset()
    only: tuple[str, ...] | None = None
    per_file: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)
    forbid: tuple[str, ...] = ()
    forbid_except: tuple[str, ...] = ()
    no_adapters: bool = False
    no_system_clock: bool = False
    no_foreign_errors: tuple[str, ...] = ()
    why: str = ""


def _domain(pkg: str, **kw) -> Rule:
    return Rule(scope=(f"rinthel_tui/{pkg}/domain",), infra=True, **kw)


def _pkg(pkg: str, **kw) -> Rule:
    return Rule(scope=(f"rinthel_tui/{pkg}",), **kw)


# módulo -> reglas. Un módulo con ``domain/`` lleva al menos la de infraestructura.
RULES: dict[str, list[Rule]] = {
    "monitoring": [
        _domain("monitoring", no_adapters=True),
        _pkg("monitoring",
             only=("rinthel_tui.monitoring", "rinthel_tui.clock", "rinthel_tui.config", "rinthel_tui.lifecycle.services"),
             why="el Clock neutral y, en los adapters, el cfg vivo y la lista de servicios compose (de dónde "
                 "corre cada ``docker compose ps``); nada del dominio de lifecycle"),
    ],
    "lifecycle": [
        _domain("lifecycle", no_adapters=True, forbid=("rinthel_tui.config",),
                infra_allowed=frozenset({"pathlib"}), infra_extra=frozenset({"socket", "urllib", "shutil", "time"}),
                why="arma rutas (pathlib) y su entorno base nunca lo lee; la red, el filesystem global, los procesos "
                    "y el reloj tienen su puerto (Probe, HostInfo, Processes, Clock)"),
    ],
    "identity": [
        _domain("identity", no_adapters=True, no_system_clock=True,
                why="users and guards only: SQLite and Deck's HTTP live behind Identity and DeckSessions"),
        _pkg("identity",
             only=("rinthel_tui.identity", "rinthel_tui.clock", "rinthel_tui.faults", "rinthel_tui.database"),
             per_file={"rinthel_tui/identity/__main__.py": (
                 ("rinthel_tui.config", "rinthel_tui.instance"), "the operator command finds the Instance and its rinthel.db",
             )},
             why="the neutral Clock, the shared fault injection of the doubles and the rinthel.db connection; "
                 "nothing of lifecycle or the HTTP layer"),
    ],
}

# Módulos de ``rinthel_tui/`` sin regla de imports, con el motivo. Un módulo nuevo
# o está en ``RULES`` o está acá; el test lo exige en las dos direcciones.
_PLAIN = "capa de infraestructura o de composición: sin dominio ni regla de dependencias propia"
UNGUARDED: dict[str, str] = {
    "api": "rutas HTTP: capa de composición, importa lo que enchufa",
    "atomic_write": _PLAIN,
    "clock": "el Clock neutral que los dominios toman",
    "code_version": _PLAIN,
    "config": _PLAIN,
    "config_edits": _PLAIN,
    "daemon": "raíz de composición",
    "database": "rinthel.db connection and migrator: infrastructure shared by the startup gate and the SQLite adapters",
    "env_file": _PLAIN,
    "faults": "la inyección de fallos que comparten los dobles en memoria (ADR 0005), sin dependencias",
    "install": _PLAIN,
    "instance": _PLAIN,
    "theme": "TUI, no es del daemon",
    "tools": "herramientas del agente, sin dominio",
}
