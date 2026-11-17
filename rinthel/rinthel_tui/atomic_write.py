"""Escritura atómica de archivos: un único lugar para la secuencia
tempfile + ``os.replace``."""

import os
import tempfile
from collections.abc import Callable
from pathlib import Path


def atomic_write(
    path: Path,
    data: str | bytes,
    *,
    new_mode: int = 0o644,
    replace: Callable[[str, Path], None] = os.replace,
) -> None:
    """Deja ``path`` con ``data`` entero o sin cambios: un lector de otro
    proceso, o un crash a mitad, ve el archivo viejo completo o el nuevo
    completo, nunca uno truncado. Crea el directorio padre si falta.

    Política única:

    - Temporal en el mismo directorio (mismo filesystem), para que
      ``os.replace`` sea atómico.
    - Modo: un archivo existente conserva el suyo; uno nuevo usa
      ``new_mode`` (``mkstemp`` crea en 0600, que puede ser más
      restrictivo de lo que otro proceso lector necesita). Sin
      ``os.umask``: es global al proceso y no es seguro con hilos.
    - Ante cualquier ``BaseException`` borra el temporal y relanza.
    - Sin ``fsync``: protege de lecturas a medias, no de un corte de luz.

    ``replace`` es el intercambio atómico (``os.replace``): un parámetro para
    que un test inyecte el fallo del intercambio."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data.encode() if isinstance(data, str) else data)
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = new_mode
        os.chmod(tmp, mode)
        replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
