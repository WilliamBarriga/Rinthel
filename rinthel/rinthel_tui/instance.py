"""Instance layout: where the root, state and config of an install live.

The application lives in ``<root>/rinthel/``; state (``data/``), logs
(``logs/``) and the single ``.env`` live at the Instance root.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Instance:
    root: Path

    @classmethod
    def discover(cls, start: Path | None = None) -> "Instance":
        """Nearest ancestor of ``start`` with ``.git``.

        Falls back to the parent of ``rinthel/`` when run outside a git
        checkout (``start`` is a package directory directly under ``rinthel/``).
        """
        start = (start or Path(__file__).resolve().parent).resolve()
        for candidate in (start, *start.parents):
            if (candidate / ".git").exists():
                return cls(candidate)
        return cls(start.parent.parent)

    @property
    def app_dir(self) -> Path:
        return self.root / "rinthel"

    @property
    def env_path(self) -> Path:
        return self.root / ".env"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"
