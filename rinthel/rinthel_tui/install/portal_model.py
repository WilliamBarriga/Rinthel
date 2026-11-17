"""The legacy portal chats against the active Local model: its pi reads the
``local-llm`` provider from a ``models.json`` that the daemon keeps pointing at
``llama-server``. Leaves with the portal, when Deck replaces it.

The provider holds a single model with a fixed id (``PORTAL_MODEL_ID``):
``llama-server`` serves whatever Local model is active whatever id a request
names, so switching models never leaves a portal session pointing at a model
pi does not know. Only its name and context window follow the active one."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rinthel_tui.atomic_write import atomic_write
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport
from rinthel_tui.lifecycle.domain.types import Platform
from rinthel_tui.models.domain.types import LocalModel

PORTAL_PROVIDER = "local-llm"
PORTAL_MODEL_ID = "active-local-model"


@dataclass(frozen=True)
class PortalModel:
    """Where the portal's pi reads ``models.json`` on each Platform, and what
    goes in it. ``llama_url`` is built with ``deck.host_address``."""

    linux_agent_dir: Path
    windows_agent_dir: Path
    llama_url: str
    model: LocalModel | None

    def models_json(self, platform: Platform) -> Path:
        # On Windows the portal compose mounts the host's pi agent dir file
        # (prepare_portal_for_windows); on Linux it lives in the portal state.
        agent_dir = self.windows_agent_dir if platform == "windows" else self.linux_agent_dir
        return agent_dir / "models.json"


def publish(task: PortalModel, platform: Platform) -> Path:
    """Writes the ``local-llm`` provider for the active model, keeping any
    other provider the file has. Raises ``ValueError`` on an unusable file."""
    path = task.models_json(platform)
    config: dict[str, Any] = {"providers": {}}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} no es JSON válido: {exc}") from exc
        if isinstance(existing, dict):
            config = existing
    providers = config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ValueError(f"{path}: 'providers' debe ser un objeto JSON")
    assert task.model is not None
    providers[PORTAL_PROVIDER] = {
        "baseUrl": f"{task.llama_url}/v1",
        "api": "openai-completions",
        "apiKey": "local",
        "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
        "models": [{"id": PORTAL_MODEL_ID, "name": task.model.name, "contextWindow": task.model.context_window}],
    }
    atomic_write(path, json.dumps(config, indent=2) + "\n")
    return path


async def phase_publish_portal_model(host: Host, report: PhaseReport, *, task: PortalModel) -> None:
    """Before the portal comes up: its pi points at the active Local model."""
    if task.model is None:
        report.warn("sin Local model activo — el portal no tiene modelo local que usar")
        return
    try:
        path = publish(task, host.host_info.platform())
    except (ValueError, OSError) as exc:
        report.error(str(exc))
        raise PhaseError("portal models.json unusable") from exc
    report.success(f"Portal apuntado a {task.model.id} en {path}")
