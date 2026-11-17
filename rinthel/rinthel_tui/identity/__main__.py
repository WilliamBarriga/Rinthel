"""Operator commands on identity:
``python -m rinthel_tui.identity reset-admin [--username admin]``. Local
access to the host, without HTTP: it opens the Instance's ``rinthel.db``
(migrating it first, as the daemon's startup does) and works with the daemon
running or stopped."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rinthel_tui import database
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.admin import FIRST_ADMIN, reset_admin
from rinthel_tui.instance import Instance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rinthel_tui.identity")
    parser.add_argument("--root", type=Path, help="explicit Instance root (default: Instance.discover())")
    sub = parser.add_subparsers(dest="command", required=True)
    reset = sub.add_parser("reset-admin", help="sets a new password for an admin (creates it if missing)")
    reset.add_argument("--username", default=FIRST_ADMIN)
    args = parser.parse_args(argv)

    instance = Instance(args.root) if args.root else Instance.discover()
    path = instance.database_path
    try:
        database.migrate(path)
    except database.DatabaseError as exc:
        print(f"reset-admin: {exc}", file=sys.stderr)
        return 1
    password = reset_admin(SqliteIdentity(path), args.username)
    print(f"admin: {args.username}  contraseña: {password}")
    print("copiala ahora, no se vuelve a mostrar; cambiala después del primer login", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
