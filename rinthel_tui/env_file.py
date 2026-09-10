"""Escribe/actualiza un ``.env`` preservando todo lo que no se toca
(comentarios incluidos) — generalización de lo que ``install.py`` ya hacía
para el ``.env`` de Pithagoras/Understory, reusado también por la pantalla
de configuración (``[N] CONFIGURAR``) para guardar cambios de ``enabled``/
parámetros en el ``.env`` de la raíz del repo.
"""

from pathlib import Path


def update_env_file(path: Path, overrides: dict[str, str], *, seed_from: Path | None = None) -> None:
    """Si ``path`` no existe todavía, lo siembra desde ``seed_from`` (ej.
    ``.env.example``) — sin ``seed_from``, o si tampoco existe, arranca de
    un archivo vacío. Después aplica ``overrides`` clave por clave,
    preservando el resto del archivo (comentarios y valores no tocados)
    tal cual estaban."""
    if path.exists():
        source_lines = path.read_text().splitlines()
    elif seed_from is not None and seed_from.exists():
        source_lines = seed_from.read_text().splitlines()
    else:
        source_lines = []

    out: list[str] = []
    seen: set[str] = set()
    for line in source_lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0] if "=" in stripped and not stripped.startswith("#") else None
        if key in overrides:
            out.append(f"{key}={overrides[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in overrides.items():
        if key not in seen:
            out.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")
