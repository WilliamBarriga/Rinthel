"""Instance layout: where the root, state and config of an install live, and
the owner of its secrets (see **Instance** in GLOSSARY.md).

The application lives in ``<root>/rinthel/``; state (``data/``), logs
(``logs/``) and the single ``.env`` live at the Instance root. Every layout
path comes from here; nobody else recomputes the root.
"""

import argparse
import os
import secrets
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from dotenv import dotenv_values

from rinthel_tui.env_file import update_env_file


class RotatableSecret(StrEnum):
    """Secrets that can be rotated without breaking anything persisted: they
    only invalidate sessions and clients."""

    SERVICE = "RINTHEL_SERVICE_SECRET"
    PANEL = "RINTHEL_PANEL_SECRET"


@dataclass(frozen=True)
class Instance:
    root: Path

    @classmethod
    def discover(cls, start: Path | None = None) -> "Instance":
        """Nearest ancestor of ``start`` with ``.git``.

        Without ``start``, ``RINTHEL_INSTANCE_ROOT`` wins when set (a daemon
        started from another cwd, or on a temporary root). Falls back to the
        parent of ``rinthel/`` when run outside a git checkout (``start`` is a
        package directory directly under ``rinthel/``).
        """
        if start is None and (root := os.getenv("RINTHEL_INSTANCE_ROOT")):
            return cls(Path(root))
        start = (start or Path(__file__).resolve().parent).resolve()
        for candidate in (start, *start.parents):
            if (candidate / ".git").exists():
                return cls(candidate)
        return cls(start.parent.parent)

    @property
    def app_dir(self) -> Path:
        return self.root / "rinthel"

    @property
    def env_path(self) -> Path:
        return self.root / ".env"

    @property
    def env_example_path(self) -> Path:
        return self.root / ".env.example"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def database_path(self) -> Path:
        """The daemon's SQLite file (identity), see ``database.py``."""
        return self.data_dir / "rinthel.db"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def instance_toml_path(self) -> Path:
        """Instance settings the daemon writes (the active Local model per Capability)."""
        return self.data_dir / "instance.toml"

    @property
    def models_catalog_path(self) -> Path:
        """The Local model catalog, edited by hand; never tracked."""
        return self.root / "models.local.json"

    @property
    def models_example_path(self) -> Path:
        """A documented example of the catalog, written by INSTALL next to it."""
        return self.root / "models.local.example.json"

    @property
    def understory_dir(self) -> Path:
        """Default of ``cfg.understory.dir``."""
        return self.root / "understory"

    @property
    def deck_dir(self) -> Path:
        """Default of ``cfg.deck.dir``."""
        return self.root / "deck"

    @property
    def deck_data_dir(self) -> Path:
        """Deck's volume: ``deck.db``, the home of pi, sessions and slots."""
        return self.data_dir / "deck"

    @property
    def understory_data_dir(self) -> Path:
        """Understory's live bundle, bind-mounted into its container."""
        return self.data_dir / "understory"

    def get(self, key: str) -> str | None:
        """Reads ``key`` from the ``.env`` on disk, uncached: a ``.env`` edited by
        hand after the daemon started is seen here without a restart. Missing,
        empty or no file are the same case: ``None``."""
        if not self.env_path.exists():
            return None
        return dotenv_values(self.env_path).get(key) or None

    def variable(self, name: str, shell: Mapping[str, str] | None = None) -> str | None:
        """The single rule to read an Instance variable: the shell (``shell``,
        default the process environment) and, if missing or empty, the
        ``.env``. Missing in both: ``None``."""
        return (os.environ if shell is None else shell).get(name) or self.get(name)

    def ensure_secret(self, key: str) -> bool:
        """Generates ``key`` in the ``.env`` if missing (seeding the ``.env``
        from ``.env.example`` when it does not exist). Idempotent: returns
        ``True`` only when it generated it. Always leaves the ``.env`` at
        ``0600``: boot calls it on every start and is what guarantees that mode."""
        generated = not self.get(key)
        if generated:
            self._write_secret(key)
        self.env_path.chmod(0o600)
        return generated

    def rotate_secret(self, key: str) -> None:
        if key not in RotatableSecret:
            raise ValueError(f"{key} no es rotable (solo {', '.join(RotatableSecret)})")
        self._write_secret(key)

    def _write_secret(self, key: str) -> None:
        update_env_file(self.env_path, {key: secrets.token_hex(32)}, seed_from=self.env_example_path)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the boot scripts: ``root``, ``get KEY``,
    ``ensure-secret KEY``, ``rotate KEY``. ``get`` of a missing key prints
    nothing: the caller sets the default."""
    parser = argparse.ArgumentParser(prog="python -m rinthel_tui.instance")
    parser.add_argument("--root", type=Path, help="raíz explícita (default: Instance.discover())")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("root")
    for name in ("get", "ensure-secret", "rotate"):
        sub.add_parser(name).add_argument("key")
    args = parser.parse_args(argv)

    instance = Instance(args.root) if args.root else Instance.discover()
    if args.command == "root":
        print(instance.root)
    elif args.command == "get":
        value = instance.get(args.key)
        if value is not None:
            print(value)
    elif args.command == "ensure-secret":
        if instance.ensure_secret(args.key):
            print(f"{args.key} generado en {instance.env_path}", file=sys.stderr)
    elif args.command == "rotate":
        try:
            instance.rotate_secret(args.key)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"{args.key} rotado en {instance.env_path}", file=sys.stderr)
        # Offline tool: a running daemon keeps the old secret in memory. Hot
        # rotation is POST /secrets/rotate.
        print("aviso: si el daemon está corriendo, usá la TUI o reiniciá", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
