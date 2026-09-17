"""Escribe/actualiza un ``.env`` preservando todo lo que no se toca
(comentarios incluidos) — generalización de lo que ``install.py`` ya hacía
para el ``.env`` de Pithagoras/Understory, reusado también por la pantalla
de configuración (``[N] CONFIGURAR``) para guardar cambios de ``enabled``/
parámetros en el ``.env`` de la raíz del repo.
"""

import os
import stat
import tempfile
from pathlib import Path


def update_env_file(path: Path, overrides: dict[str, str], *, seed_from: Path | None = None) -> None:
    """Si ``path`` no existe todavía, lo siembra desde ``seed_from`` (ej.
    ``.env.example``) — sin ``seed_from``, o si tampoco existe, arranca de
    un archivo vacío. Después aplica ``overrides`` clave por clave,
    preservando el resto del archivo (comentarios y valores no tocados)
    tal cual estaban.

    Escribe a un temporal en el mismo directorio y lo renombra por encima
    del original (``os.replace``, atómico dentro del mismo filesystem) en
    vez de pisar ``path`` directo — si el daemon muere a mitad de un
    ``POST /config``, el ``.env`` (única fuente de verdad de infra) queda
    con el contenido viejo intacto en vez de truncado. Preserva el modo del
    archivo original si existía: ``tempfile`` crea el temporal en 0600 por
    default, más restrictivo que lo que el ``.env`` pudiera tener antes."""
    if path.exists():
        source_lines = path.read_text().splitlines()
    elif seed_from is not None and seed_from.exists():
        source_lines = seed_from.read_text().splitlines()
    else:
        source_lines = []

    out: list[str] = []
    seen_keys: set[str] = set()
    for line in source_lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0] if "=" in stripped and not stripped.startswith("#") else None
        if key in overrides:
            out.append(f"{key}={overrides[key]}")
            seen_keys.add(key)
        else:
            out.append(line)
    for key, value in overrides.items():
        if key not in seen_keys:
            out.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else None
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(out) + "\n")
        if mode is not None:
            os.chmod(tmp_name, stat.S_IMODE(mode))
        os.replace(tmp_name, path)
    except BaseException:
        os.unlink(tmp_name)
        raise
