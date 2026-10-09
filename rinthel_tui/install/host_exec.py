"""Prepare the shared host-exec secret without replacing existing secrets."""

import json
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

from rinthel_tui.env_file import update_env_file

_TOKEN = "RINTHEL_HOSTEXECD_TOKEN"


def prepare_host_exec(repo_root: Path, portal_dir: Path) -> None:
    """Ensure host and Compose use one token; reject conflicting local values.

    Existing non-empty values win over generation. No token is returned or
    logged. Both INSTALL and the host launcher cross this same interface.
    """
    paths = (repo_root / ".env", portal_dir / ".env")
    configured = [
        (dotenv_values(path, interpolate=False).get(_TOKEN) or "").strip()
        for path in paths
    ]
    values = {value for value in configured if value}
    inherited = os.getenv(_TOKEN, "").strip()
    if inherited:
        values.add(inherited)
    if len(values) > 1:
        raise ValueError("Host exec tiene tokens distintos en los .env; unifícalos antes de arrancar")
    token = next(iter(values), None) or secrets.token_hex(32)
    for path, existing in zip(paths, configured):
        # BOOT must not create a token-only portal .env: INSTALL needs to seed
        # that file with its other required secrets on a fresh installation.
        if not existing and (path == paths[0] or path.exists()):
            update_env_file(path, {_TOKEN: json.dumps(token, ensure_ascii=False)})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("portal_dir", type=Path)
    args = parser.parse_args()
    try:
        prepare_host_exec(args.repo_root, args.portal_dir)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
