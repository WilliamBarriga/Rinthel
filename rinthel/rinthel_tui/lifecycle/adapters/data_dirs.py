import os
from pathlib import Path

from rinthel_tui.lifecycle.domain.errors import DataDirError


class SystemDataDirs:
    """``DataDirs`` sobre ``os``. Un directorio nuevo se le da a ``uid``:``gid``
    con ``chown``, que sin ser root solo sirve si ya son los del daemon (el
    caso normal: ``PUID``/``PGID`` son los del usuario que corre la Instance)."""

    def ensure(self, path: Path, *, uid: int, gid: int) -> tuple[int, int]:
        try:
            if not path.is_dir():
                path.mkdir(parents=True)
                info = path.stat()
                if (info.st_uid, info.st_gid) != (uid, gid):
                    os.chown(path, uid, gid)
            info = path.stat()
        except OSError as exc:
            raise DataDirError(str(exc)) from exc
        return info.st_uid, info.st_gid
