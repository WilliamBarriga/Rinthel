"""The token ``hostexecd`` shares with Deck, in the root ``.env``, never
replacing one that is already there."""

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
    exported in the shell. No token is returned or logged. INSTALL
    (``phase_install_host_exec_token``) is its only caller; the daemon reads
    the token from the ``.env`` and hands it to hostexecd and Deck. Returns
    ``True`` only when it wrote the token."""
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
