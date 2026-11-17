"""The token ``hostexecd`` shares with whoever asks it to run a command, in the
root ``.env``, never replacing one that is already there."""

import json
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

from rinthel_tui.env_file import update_env_file

_TOKEN = "RINTHEL_HOSTEXECD_TOKEN"


def prepare_host_exec(repo_root: Path) -> bool:
    """Ensure the root ``.env`` holds the token; reject a conflicting one.

    An existing non-empty value wins over generation, and so does one
    exported in the shell. No token is returned or logged. Both INSTALL and
    the host launcher cross this same interface. Returns ``True`` only when
    it wrote the token."""
    env_path = repo_root / ".env"
    configured = (dotenv_values(env_path, interpolate=False).get(_TOKEN) or "").strip() if env_path.exists() else ""
    inherited = os.getenv(_TOKEN, "").strip()
    if configured and inherited and configured != inherited:
        raise ValueError("Host exec tiene tokens distintos en el .env y en el entorno; unifícalos antes de arrancar")
    if configured:
        return False
    token = inherited or secrets.token_hex(32)
    update_env_file(env_path, {_TOKEN: json.dumps(token, ensure_ascii=False)}, seed_from=repo_root / ".env.example")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    args = parser.parse_args()
    try:
        prepare_host_exec(args.repo_root)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
