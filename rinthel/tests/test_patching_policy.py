"""Guardia de la política de pruebas (ADR 0005): una prueba cruza el interface
y no parchea. Recorre el AST de ``tests/`` y cuenta los parches contra un
nombre privado (``_run``), contra una constante (``MAX_UPLOAD_BYTES``) o contra
un global de la stdlib o de un driver (``asyncio``, ``shutil``, ``os``,
``urllib``, ``socket``, ``time``, ``psycopg``). No marca ``setenv``,
``chdir`` ni ``delitem``, que no parchean código.

``FROZEN`` es el tope por archivo de los parches que queden: la guardia falla
si el número sube y también si baja sin actualizar ``FROZEN``. Hoy está vacío. La regla
sobre funciones públicas de otro module no tiene guardia: el AST no distingue
una función pública de un puerto, y la hace cumplir la revisión."""

import ast
from pathlib import Path

STDLIB_GLOBALS = {"asyncio", "shutil", "os", "urllib", "socket", "time", "psycopg"}

# archivo (relativo a ``tests/``) -> parches contra privados o stdlib que aún tiene.
# Vacío: un parche nuevo no entra (ADR 0005).
FROZEN: dict[str, int] = {}


def _dotted(node: ast.AST) -> list[str]:
    """``a.b.c`` -> ``["a", "b", "c"]``; lo que no es una cadena de nombres, ``[]``."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return [node.id, *reversed(parts)]
    return []


def _str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _patch_target(call: ast.Call) -> list[str] | None:
    """El destino que parchea la llamada, como cadena de nombres, o ``None`` si
    no es un parche de código (``monkeypatch.setattr``, ``patch``, ``patch.object``)."""
    func = _dotted(call.func)
    if func[-2:] == ["monkeypatch", "setattr"] or func == ["monkeypatch", "setattr"]:
        if len(call.args) >= 2 and (name := _str(call.args[1])) is not None:
            return [*_dotted(call.args[0]), name]
        if call.args and (target := _str(call.args[0])) is not None:
            return target.split(".")
    elif func[-1:] == ["patch"] and call.args and (target := _str(call.args[0])) is not None:
        return target.split(".")
    elif func[-2:] == ["patch", "object"] and len(call.args) >= 2 and (name := _str(call.args[1])) is not None:
        return [*_dotted(call.args[0]), name]
    return None


def _is_forbidden(target: list[str]) -> bool:
    name = target[-1]
    private = name.startswith("_") and not name.startswith("__")
    constant = name.isupper()
    return private or constant or bool(STDLIB_GLOBALS & set(target[:-1]))


def forbidden_patches(source: str) -> int:
    targets = (_patch_target(n) for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call))
    return sum(1 for t in targets if t is not None and _is_forbidden(t))


def _counts() -> dict[str, int]:
    tests = Path(__file__).parent
    counts = {str(path.relative_to(tests)): forbidden_patches(path.read_text()) for path in tests.rglob("*.py")}
    return {name: n for name, n in sorted(counts.items()) if n}


def test_no_test_gains_a_patch_and_each_ticket_lowers_its_cap():
    assert _counts() == FROZEN


def test_the_guard_flags_a_private_and_a_stdlib_patch():
    source = (
        "def test_a(monkeypatch):\n"
        "    monkeypatch.setattr(ms, '_run', fake)\n"
        "    monkeypatch.setattr(asyncio, 'sleep', fake)\n"
        "    monkeypatch.setattr('shutil.which', fake)\n"
        "    monkeypatch.setattr(ms.asyncio, 'create_subprocess_exec', fake)\n"
        "    with patch('urllib.request.urlopen'):\n"
        "        pass\n"
        "    with mock.patch.object(thing, '_private'):\n"
        "        pass\n"
        "    monkeypatch.setattr(mod, 'MAX_UPLOAD_BYTES', 1)\n"
        "    monkeypatch.setattr(psycopg, 'connect', fake)\n"
    )
    assert forbidden_patches(source) == 8


def test_the_guard_lets_through_what_does_not_patch_code():
    source = (
        "def test_a(monkeypatch):\n"
        "    monkeypatch.setenv('X', '1')\n"
        "    monkeypatch.chdir(tmp)\n"
        "    monkeypatch.delitem(sys.modules, 'x')\n"
        "    monkeypatch.setattr(thing, 'public', fake)\n"
        "    monkeypatch.setattr(thing, '__class__', fake)\n"
    )
    assert forbidden_patches(source) == 0
