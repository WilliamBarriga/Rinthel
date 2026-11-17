"""The vocabulary of Local models (see **Local model**, **Capability** and
**Validated profile** in GLOSSARY.md): what an entry of the catalog says, whether
it can be activated, and the route the daemon hands out for the active one."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Capability = Literal["llm", "stt", "tts"]
CAPABILITIES: tuple[Capability, ...] = ("llm", "stt", "tts")
# Opt-in and Linux only: without an active key the service does not start.
VOICE: tuple[Capability, ...] = ("stt", "tts")

# The closed list of reasoning formats Deck knows how to drive against a local
# llama-server (pi's ``thinkingFormat`` values that apply to a chat template).
REASONING_FORMATS: tuple[str, ...] = ("qwen-chat-template", "chat-template", "qwen", "deepseek")
DEFAULT_REASONING_FORMAT = "qwen-chat-template"

# What a Local model may tune for itself: sampling and speculative decoding.
# Hardware (GPU layers, batch, threads, MoE cache, KV cache) belongs to the
# Validated profile of the Platform, never to a catalog entry.
OVERRIDABLE: frozenset[str] = frozenset({
    "temperature", "top_p", "top_k", "min_p", "repeat_penalty", "spec_type", "spec_draft_n_max",
})


@dataclass(frozen=True)
class LocalModel:
    """``gguf`` is the model file: a GGUF for ``llm`` and ``tts``, the
    whisper.cpp ``ggml`` file for ``stt``. A voice entry has no context
    window (``0``)."""

    id: str
    name: str
    capability: Capability
    gguf: Path
    context_window: int
    mmproj: Path | None = None
    mtp: bool = False
    reasoning_format: str = DEFAULT_REASONING_FORMAT
    # LlamaConfig attribute -> value, only keys of ``OVERRIDABLE``.
    overrides: dict[str, str | int | float] = field(default_factory=dict)
    # ``tts`` only: the reference WAV of the fixed voice it speaks with.
    voice: Path | None = None


@dataclass(frozen=True)
class CatalogEntry:
    """One entry of the catalog as read. ``problem`` says why it cannot be
    activated (missing GGUF, bad header, missing ``mmproj``, malformed entry);
    an invalid entry is still listed, it never makes the catalog fail."""

    id: str
    model: LocalModel | None
    problem: str | None = None

    @property
    def activable(self) -> bool:
        return self.problem is None and self.model is not None


@dataclass(frozen=True)
class Active:
    """The Local model the Instance serves for a Capability, as resolved from
    the active id and the catalog. ``model`` is ``None`` when nothing usable
    is active; ``warning`` then says why (unknown id, invalid entry)."""

    id: str | None
    model: LocalModel | None
    warning: str | None = None


@dataclass(frozen=True)
class Route:
    """Where Deck sends the calls of a Capability: straight to the managed
    service at ``url`` (built with ``deck.host_address``), asking for ``model``."""

    url: str
    model: str
    context_window: int
    reasoning_format: str


@dataclass(frozen=True)
class ServiceRun:
    """What restarting the managed service of a Capability with a model gave."""

    ok: bool
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class Switched:
    """The result of a switch. ``ok`` with the new id active, or not ``ok``
    with the previous one kept; ``rolled_back`` says whether the previous
    model came back up (``None`` when there was nothing to restore). Turning
    a Capability off is ``ok`` with ``active`` ``None``."""

    ok: bool
    active: str | None
    rolled_back: bool | None
    runs: tuple[ServiceRun, ...]
    model: LocalModel | None = None
    # The Capability the switch (or ``off``) was about.
    capability: Capability = "llm"
