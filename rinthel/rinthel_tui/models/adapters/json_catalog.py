"""``Catalog`` over ``models.local.json`` at the Instance root, edited by hand.

Validates on every read: the shape of each entry, that the GGUF exists and
starts with the ``GGUF`` magic, and that ``mmproj`` exists when declared. An
invalid entry is listed with its problem and is not activable; the catalog
never fails because of one entry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rinthel_tui.atomic_write import atomic_write
from rinthel_tui.models.domain.errors import CatalogUnavailable
from rinthel_tui.models.domain.types import (
    CAPABILITIES,
    DEFAULT_REASONING_FORMAT,
    OVERRIDABLE,
    REASONING_FORMATS,
    CatalogEntry,
    LocalModel,
)

_MAGIC = b"GGUF"


class JsonCatalog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def entries(self) -> list[CatalogEntry]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogUnavailable(f"{self._path}: {exc}") from exc
        raw = data.get("models") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            raise CatalogUnavailable(f"{self._path}: se espera un objeto con la lista \"models\"")
        entries: list[CatalogEntry] = []
        seen: set[str] = set()
        for position, item in enumerate(raw, start=1):
            read = _entry(item, position)
            if read.id in seen:
                read = CatalogEntry(read.id, read.model, f"id repetido: {read.id}")
            seen.add(read.id)
            entries.append(read)
        return entries


def write_catalog(path: Path, models: list[LocalModel]) -> None:
    """A new catalog with ``models``: what INSTALL leaves for the admin to
    edit by hand. The daemon never rewrites an existing catalog."""
    _dump(path, [_raw(m) for m in models])


def add_to_catalog(path: Path, models: tuple[LocalModel, ...] | list[LocalModel]) -> list[str]:
    """Appends the ``models`` whose id is not in the catalog yet (INSTALL with
    voice over an existing Instance) and returns their ids. Every entry and
    key the admin wrote is kept (the file is re-serialized); a catalog that
    cannot be read is ``CatalogUnavailable``, never overwritten."""
    if not path.exists():
        write_catalog(path, list(models))
        return [m.id for m in models]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogUnavailable(f"{path}: {exc}") from exc
    raw = data.get("models") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise CatalogUnavailable(f"{path}: se espera un objeto con la lista \"models\"")
    present = {item.get("id") for item in raw if isinstance(item, dict)}
    added = [m for m in models if m.id not in present]
    if added:
        _dump(path, [*raw, *(_raw(m) for m in added)], rest=data)
    return [m.id for m in added]


def _raw(m: LocalModel) -> dict[str, Any]:
    if m.capability != "llm":
        # A voice entry: only what its service reads.
        return {"id": m.id, "name": m.name, "capability": m.capability, "gguf": str(m.gguf),
                **({"voice": str(m.voice)} if m.voice else {})}
    return {
        "id": m.id,
        "name": m.name,
        "capability": m.capability,
        "gguf": str(m.gguf),
        "mmproj": str(m.mmproj) if m.mmproj else None,
        "mtp": m.mtp,
        "context_window": m.context_window,
        "reasoning_format": m.reasoning_format,
        "overrides": dict(m.overrides),
    }


def _dump(path: Path, entries: list[Any], *, rest: dict[str, Any] | None = None) -> None:
    data = {**(rest or {}), "models": entries}
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _entry(item: Any, position: int) -> CatalogEntry:
    raw_id = item.get("id") if isinstance(item, dict) else None
    model_id = raw_id if isinstance(raw_id, str) and raw_id else f"entrada-{position}"
    if not isinstance(item, dict):
        return CatalogEntry(model_id, None, "la entrada no es un objeto")
    try:
        model = _model(model_id, item)
    except ValueError as exc:
        return CatalogEntry(model_id, None, str(exc))
    if raw_id != model_id:
        return CatalogEntry(model_id, model, "falta \"id\"")
    return CatalogEntry(model_id, model, _file_problem(model))


def _model(model_id: str, item: dict[str, Any]) -> LocalModel:
    name = item.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("falta \"name\"")
    capability = item.get("capability")
    if capability not in CAPABILITIES:
        raise ValueError(f"capability {capability!r} no es una de {', '.join(CAPABILITIES)}")
    gguf = item.get("gguf")
    if not isinstance(gguf, str) or not gguf:
        raise ValueError("falta \"gguf\"")
    # A voice model has no context window: only ``llm`` requires one.
    window = item.get("context_window", None if capability == "llm" else 0)
    if not isinstance(window, int) or isinstance(window, bool) or window < 0 or (capability == "llm" and window == 0):
        raise ValueError("context_window debe ser un entero > 0")
    voice = item.get("voice")
    if voice is not None and capability != "tts":
        raise ValueError("voice es solo de una entrada tts")
    if voice is not None and (not isinstance(voice, str) or not voice):
        raise ValueError("voice debe ser la ruta de un WAV o null")
    mmproj = item.get("mmproj")
    if mmproj is not None and (not isinstance(mmproj, str) or not mmproj):
        raise ValueError("mmproj debe ser una ruta o null")
    mtp = item.get("mtp", False)
    if not isinstance(mtp, bool):
        raise ValueError("mtp debe ser true o false")
    reasoning = item.get("reasoning_format", DEFAULT_REASONING_FORMAT)
    if reasoning not in REASONING_FORMATS:
        raise ValueError(f"reasoning_format {reasoning!r} no es uno de {', '.join(REASONING_FORMATS)}")
    overrides = item.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("overrides debe ser un objeto")
    foreign = sorted(set(overrides) - OVERRIDABLE)
    if foreign:
        raise ValueError(f"overrides fuera de la lista blanca: {', '.join(foreign)}")
    if any(isinstance(v, bool) or not isinstance(v, (str, int, float)) for v in overrides.values()):
        raise ValueError("los valores de overrides son números o texto")
    return LocalModel(
        id=model_id,
        name=name,
        capability=capability,
        gguf=Path(gguf).expanduser(),
        context_window=window,
        mmproj=Path(mmproj).expanduser() if mmproj else None,
        mtp=mtp,
        reasoning_format=reasoning,
        overrides=dict(overrides),
        voice=Path(voice).expanduser() if voice else None,
    )


def _file_problem(model: LocalModel) -> str | None:
    if model.capability == "stt":
        # whisper.cpp reads its own ``ggml`` format, not GGUF.
        return None if model.gguf.is_file() else f"modelo no encontrado: {model.gguf}"
    if not model.gguf.is_file():
        return f"GGUF no encontrado: {model.gguf}"
    try:
        with model.gguf.open("rb") as f:
            magic = f.read(len(_MAGIC))
    except OSError as exc:
        return f"GGUF ilegible: {exc}"
    if magic != _MAGIC:
        return f"cabecera GGUF inválida: {model.gguf}"
    if model.mmproj is not None and not model.mmproj.is_file():
        return f"mmproj no encontrado: {model.mmproj}"
    if model.voice is not None and not model.voice.is_file():
        return f"voz no encontrada: {model.voice}"
    return None
