"""Lo compartido que ``create_app`` entrega a la composición de cada área
(``<area>/compose.py``): lo que más de un área necesita y no es de ninguna.
Una área que necesita algo más lo suma aquí, ya construido por ``create_app``,
que sigue siendo el único que elige adaptadores (ADR 0004)."""

from __future__ import annotations

from dataclasses import dataclass

from rinthel_tui.clock import Clock
from rinthel_tui.config import RinthelConfig


@dataclass(frozen=True)
class Shared:
    cfg: RinthelConfig
    clock: Clock
