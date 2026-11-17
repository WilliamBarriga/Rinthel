"""La phase que deja listo un directorio de datos antes del ``docker compose
up``: si no existe, Docker autocrea el bind mount como ``root`` y un
contenedor que corre como ``PUID:PGID`` muere en bucle con ``EACCES``."""

from pathlib import Path

from rinthel_tui.lifecycle.domain.errors import DataDirError, PhaseError
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport


async def phase_ensure_data_dir(host: Host, report: PhaseReport, *, path: Path, uid: int, gid: int) -> None:
    """Lo crea para ``uid``:``gid`` si falta. Uno que ya existe con otro dueño
    no se toca: falla antes del ``up`` con el ``chown`` que lo arregla."""
    try:
        owner = host.data_dirs.ensure(path, uid=uid, gid=gid)
    except DataDirError as exc:
        report.error(f"No pude crear {path}: {exc}")
        raise PhaseError(f"cannot create {path}: {exc}") from exc
    if owner != (uid, gid):
        report.error(
            f"{path} es de {owner[0]}:{owner[1]} y el contenedor corre como {uid}:{gid} (no podría escribir "
            f"y se reiniciaría en bucle) — corré: sudo chown -R {uid}:{gid} {path}"
        )
        raise PhaseError(f"{path} owned by {owner[0]}:{owner[1]}, container runs as {uid}:{gid}")
    report.success(f"{path} listo para {uid}:{gid}")
