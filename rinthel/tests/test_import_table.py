"""Guardia de la regla de dependencias (ADR 0004): un solo recorrido AST sobre
la tabla de ``import_table.py``. Mira el código sin importarlo, así un import
dentro de una función tampoco se escapa. Un módulo nuevo es una fila de la tabla.

Aquí también: la guardia del reloj del sistema y la autoprueba del helper con
módulos de fixture."""

import ast
from pathlib import Path

import pytest
from import_table import INFRA, RULES, UNGUARDED, Rule

import rinthel_tui

ROOT = Path(rinthel_tui.__file__).parent.parent


# ── Helper AST ────────────────────────────────────────────────────────


def _imports(source: str) -> tuple[set[str], set[str]]:
    """(módulos importados, módulos posibles incluyendo ``from a import b`` -> ``a.b``)."""
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules, modules | names


def _under(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == p or module.startswith(p + ".") for p in prefixes)


def _reads_the_system_clock(source: str) -> list[str]:
    """Las llamadas ``….now()``, ``utcnow()`` y ``today()`` que no son del
    ``Clock`` inyectado (cuyo receptor se llama ``clock``)."""
    return [
        ast.unparse(node.func)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"now", "utcnow", "today"}
        and "clock" not in ast.unparse(node.func.value).lower()
    ]


def _files(root: Path, rule: Rule) -> list[Path]:
    excluded = {root / e for e in rule.exclude}
    found: list[Path] = []
    for scope in rule.scope:
        path = root / scope
        found.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return [p for p in found if p not in excluded]


def violations(root: Path, rule: Rule) -> dict[str, list[str]]:
    """Archivo (relativo a ``root``) -> lo que rompe de ``rule``."""
    out: dict[str, list[str]] = {}
    for path in _files(root, rule):
        rel = path.relative_to(root).as_posix()
        source = path.read_text()
        modules, names = _imports(source)
        bad: set[str] = set()
        roots = {m.split(".")[0] for m in modules}
        banned = ((INFRA - rule.infra_allowed) if rule.infra else set()) | rule.infra_extra
        bad |= roots & banned
        daemon = {m for m in modules if m.startswith("rinthel_tui.")}
        if rule.only is not None:
            allowed = (*rule.only, *rule.per_file.get(rel, ((), ""))[0])
            bad |= {m for m in daemon if not _under(m, allowed)}
        if rule.forbid:
            bad |= {m for m in modules if _under(m, rule.forbid) and not _under(m, rule.forbid_except)}
        if rule.no_adapters:
            bad |= {m for m in modules if ".adapters" in m}
        if rule.no_system_clock:
            bad |= set(_reads_the_system_clock(source))
        if rule.no_foreign_errors:
            bad |= {m for m in names if _under(m, rule.no_foreign_errors) and m.endswith(".errors")}
        if bad:
            out[rel] = sorted(bad)
    return out


def unlisted(package_dir: Path, rules: dict, unguarded: dict) -> set[str]:
    """Módulos de primer nivel de ``package_dir`` que ni la tabla ni ``UNGUARDED`` nombran
    (y entradas de la tabla que ya no existen)."""
    present = {
        p.stem if p.is_file() else p.name
        for p in package_dir.iterdir()
        if (p.is_file() and p.suffix == ".py" and p.stem not in {"__init__", "__main__"})
        or (p.is_dir() and any(p.rglob("*.py")))
    }
    return present ^ (set(rules) | set(unguarded))


# ── La tabla contra el código real ────────────────────────────────────

ALL_RULES = [(name, rule) for name, rules in RULES.items() for rule in rules]


@pytest.mark.parametrize(
    "name, rule",
    ALL_RULES,
    ids=[f"{n}:{'+'.join(Path(s).name for s in r.scope)}" for n, r in ALL_RULES],
)
def test_module_respects_its_import_rule(name, rule):
    assert violations(ROOT, rule) == {}, rule.why


def test_every_rule_scope_exists():
    missing = [s for _, r in ALL_RULES for s in r.scope if not (ROOT / s).exists()]
    missing += [f for _, r in ALL_RULES for f in r.per_file if not (ROOT / f).exists()]
    assert missing == []


def test_every_module_is_in_the_table_or_explained():
    assert unlisted(Path(rinthel_tui.__file__).parent, RULES, UNGUARDED) == set()


# ── Autoprueba del helper con módulos de fixture ─────────────────────


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, source in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return tmp_path


def test_infra_rule_catches_infrastructure_even_inside_a_function(tmp_path):
    root = _tree(tmp_path, {
        "bad/domain/a.py": "def f():\n    import httpx\nfrom sqlite3 import connect\n",
        "bad/domain/b.py": "import dataclasses\n",
    })
    rule = Rule(scope=("bad/domain",), infra=True)
    assert violations(root, rule) == {"bad/domain/a.py": ["httpx", "sqlite3"]}


def test_infra_allowed_and_extra_adjust_the_banned_roots(tmp_path):
    root = _tree(tmp_path, {"m/domain/a.py": "import pathlib\nimport socket\n"})
    assert violations(root, Rule(scope=("m/domain",), infra=True)) == {"m/domain/a.py": ["pathlib"]}
    rule = Rule(scope=("m/domain",), infra=True, infra_allowed=frozenset({"pathlib"}), infra_extra=frozenset({"socket"}))
    assert violations(root, rule) == {"m/domain/a.py": ["socket"]}


def test_only_rule_allows_listed_prefixes_and_per_file_exceptions(tmp_path):
    root = _tree(tmp_path, {
        "m/ok.py": "from rinthel_tui.clock import Clock\nimport os\n",
        "m/bad.py": "from rinthel_tui.notes import x\nfrom rinthel_tui.clockwork import y\n",
        "m/bridge.py": "from rinthel_tui.notes import x\n",
    })
    rule = Rule(
        scope=("m",), only=("rinthel_tui.clock",),
        per_file={"m/bridge.py": (("rinthel_tui.notes",), "puente")},
    )
    assert violations(root, rule) == {"m/bad.py": ["rinthel_tui.clockwork", "rinthel_tui.notes"]}


def test_forbid_rule_lets_through_only_the_excepted_modules(tmp_path):
    root = _tree(tmp_path, {
        "m/a.py": (
            "from rinthel_tui.models.domain.types import Model\n"
            "from rinthel_tui.models.domain.ports import Catalog\n"
            "import rinthel_tui.ledger.domain.types\n"
        ),
    })
    rule = Rule(
        scope=("m",), forbid=("rinthel_tui.models", "rinthel_tui.ledger"),
        forbid_except=("rinthel_tui.models.domain.types", "rinthel_tui.ledger.domain.types"),
    )
    assert violations(root, rule) == {"m/a.py": ["rinthel_tui.models.domain.ports"]}


def test_no_adapters_rule(tmp_path):
    root = _tree(tmp_path, {"d/a.py": "from rinthel_tui.x.adapters.pg import P\n", "d/b.py": "import json\n"})
    assert violations(root, Rule(scope=("d",), no_adapters=True)) == {"d/a.py": ["rinthel_tui.x.adapters.pg"]}


def test_foreign_errors_rule_sees_the_imported_name_and_honours_exclude(tmp_path):
    root = _tree(tmp_path, {
        "m/a.py": "from rinthel_tui.models.domain import errors\n",
        "m/b.py": "from rinthel_tui.notes.domain import errors\n",
        "m/access.py": "from rinthel_tui.models.domain import errors\n",
    })
    rule = Rule(scope=("m",), exclude=("m/access.py",), no_foreign_errors=("rinthel_tui.models",))
    assert violations(root, rule) == {"m/a.py": ["rinthel_tui.models.domain.errors"]}


def test_a_file_scope_checks_only_that_file(tmp_path):
    root = _tree(tmp_path, {"m/sup.py": "from rinthel_tui.inbox import x\n", "m/other.py": "from rinthel_tui.inbox import x\n"})
    rule = Rule(scope=("m/sup.py",), forbid=("rinthel_tui.inbox",))
    assert violations(root, rule) == {"m/sup.py": ["rinthel_tui.inbox"]}


def test_a_module_missing_from_the_table_is_reported(tmp_path):
    pkg = _tree(tmp_path, {"known/a.py": "", "new_module/a.py": "", "helper.py": "", "__init__.py": "", "empty/x.txt": ""})
    assert unlisted(pkg, {"known": []}, {"helper": "porque sí"}) == {"new_module"}
    assert unlisted(pkg, {"known": [], "new_module": [], "gone": []}, {"helper": "x"}) == {"gone"}


def test_system_clock_guard_catches_a_system_read_but_not_the_injected_clock(tmp_path):
    assert _reads_the_system_clock("def f():\n    return datetime.now(UTC)\n") == ["datetime.now"]
    assert _reads_the_system_clock("import datetime as d\nx = d.datetime.utcnow()\n") == ["d.datetime.utcnow"]
    assert _reads_the_system_clock("def f(self):\n    return self._clock.now()\n") == []
    root = _tree(tmp_path, {"w/a.py": "x = datetime.now()\n", "w/b.py": "x = self.clock.now()\n"})
    assert violations(root, Rule(scope=("w",), no_system_clock=True)) == {"w/a.py": ["datetime.now"]}
