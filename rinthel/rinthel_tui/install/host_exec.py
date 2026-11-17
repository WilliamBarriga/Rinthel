"""The token ``hostexecd`` shares with Deck, in the root ``.env``, never
replacing one that is already there."""

import os

from rinthel_tui.instance import Instance

_TOKEN = "RINTHEL_HOSTEXECD_TOKEN"


def prepare_host_exec(instance: Instance) -> bool:
    """Ensure the root ``.env`` holds the token; reject a conflicting one.

    An existing non-empty value wins over generation, and so does one
    exported in the shell. No token is returned or logged. INSTALL
    (``phase_install_host_exec_token``) is its only caller; the daemon reads
    the token from the ``.env`` and hands it to hostexecd and Deck. Returns
    ``True`` only when it wrote the token."""
    configured = (instance.get(_TOKEN) or "").strip()
    inherited = os.getenv(_TOKEN, "").strip()
    if configured and inherited and configured != inherited:
        raise ValueError("Host exec tiene tokens distintos en el .env y en el entorno; unifícalos antes de arrancar")
    return instance.ensure_secret(_TOKEN, adopt=inherited or None)
