"""La huella del código del paquete ``rinthel_tui``.

La lleva la línea de arranque del daemon en ``daemon.log``: dice con qué
código corrió cada boot. Sale de los ``.py`` y no de ``__version__`` (fija)
ni de git (una Instance puede no tener ``.git``).
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def code_version(package_dir: Path = PACKAGE_DIR) -> str:
    """12 hex del SHA-256 de los ``.py`` de ``package_dir`` (rutas relativas y
    contenido, en orden). Los ``__pycache__`` y lo que no es código no cuentan."""
    digest = hashlib.sha256()
    for path in sorted(package_dir.rglob("*.py")):
        relative = path.relative_to(package_dir)
        if "__pycache__" in relative.parts:
            continue
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


@cache
def running_code_version() -> str:
    """La huella del código de este proceso, calculada una vez: lo que corre
    no cambia mientras el proceso vive."""
    return code_version()
