"""``ActiveModels`` over ``instance.toml``: one key per Capability in the
``[models]`` table (``llm = "<id>"``), next to whatever else lives there."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from rinthel_tui import instance_toml
from rinthel_tui.models.domain.types import Capability

_TABLE = "models"


class TomlActiveModels:
    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, capability: Capability) -> str | None:
        try:
            table = instance_toml.read(self._path).get(_TABLE)
        except (OSError, tomllib.TOMLDecodeError):
            return None
        value = table.get(capability) if isinstance(table, dict) else None
        return value if isinstance(value, str) and value else None

    def set(self, capability: Capability, model_id: str) -> None:
        def change(data: dict[str, Any]) -> dict[str, Any]:
            table = data.get(_TABLE)
            return {**data, _TABLE: {**(table if isinstance(table, dict) else {}), capability: model_id}}

        instance_toml.update(self._path, change)
