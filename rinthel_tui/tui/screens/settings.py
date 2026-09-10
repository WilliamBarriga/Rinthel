"""[N] CONFIGURAR — tildar/destildar servicios y editar sus parámetros sin
tocar `.env` a mano.

Genérica a propósito: no hay una fila hecha a mano por servicio ni un input
hecho a mano por campo. La lista de servicios sale del mismo registro que ya
alimenta BOOT/badges (``services.LOCAL_SERVICES``/``DOCKER_SERVICES``); los
campos editables de cada uno salen de la misma tabla que ya usa
``RinthelConfig.validate()`` (``config._ENTRIES``) — agregar un ``Field``
nuevo a un servicio lo hace aparecer acá solo, sin tocar esta pantalla.

Los cambios se escriben en el ``.env`` de la raíz del repo (vía
``env_file.update_env_file``) y aplican recién en el próximo arranque de
Rinthel — ``CONFIG`` es un dataclass congelado cargado una sola vez al
importar ``config.py``, no hay hot-reload acá.
"""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Input, Static

from rinthel_tui.config import CONFIG, RinthelConfig, _ENTRIES
from rinthel_tui.env_file import update_env_file
from rinthel_tui.lifecycle import services
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService
from rinthel_tui.theme import palette

# rinthel_tui/tui/screens/settings.py -> repo root (mismo criterio que
# config.py para ubicar el .env de la raíz, un nivel más profundo).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _REPO_ROOT / ".env"
_ENV_EXAMPLE_PATH = _REPO_ROOT / ".env.example"

# Qué sub-config de RinthelConfig le corresponde a cada instancia de
# servicio — explícito porque _ServiceBase no guarda su propio nombre de
# atributo (port_of/enabled_of son closures, no introspeccionables). Mismo
# criterio que services.LOCAL_SERVICES/DOCKER_SERVICES: una línea más acá
# por cada servicio nuevo.
_SETTINGS_SERVICES: list[tuple[str, LocalProcessService | DockerComposeService]] = [
    ("llama", services.LLAMA_SERVICE),
    ("whisper", services.WHISPER_SERVICE),
    ("tts", services.TTS_SERVICE),
    ("understory", services.UNDERSTORY_SERVICE),
    ("pithagoras", services.PITHAGORAS_SERVICE),
]

_FIELDS_BY_ATTR = dict(_ENTRIES)


def _stringify(value: object) -> str:
    """Misma representación de texto que terminaría en el .env — bool va
    como "true"/"false" (lo que ``_bool_env`` acepta), no "True"/"False"."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _diff_overrides(cfg: RinthelConfig, edits: dict[str, str]) -> dict[str, str]:
    """De todo lo tocado durante la sesión (``edits``: env var -> valor
    nuevo como string), devuelve solo lo que de verdad difiere del valor
    actual en ``cfg`` — lo mínimo que hay que escribir en el .env. Función
    pura (sin Textual) para poder testear la lógica de guardado sin
    levantar la screen."""
    overrides: dict[str, str] = {}
    for attr, fields in _ENTRIES:
        sub = getattr(cfg, attr)
        for f in fields:
            if f.env not in edits:
                continue
            if edits[f.env] != _stringify(getattr(sub, f.attr)):
                overrides[f.env] = edits[f.env]
    return overrides


class SettingsScreen(Screen):
    BINDINGS = [("q", "close", "Volver"), ("escape", "close", "Volver")]

    def __init__(self, cfg: RinthelConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or CONFIG
        # env var -> valor nuevo (string) de todo lo tocado en esta sesión,
        # sin importar si coincide con lo que ya había — _diff_overrides
        # filtra eso recién al guardar. Sobrevive a cambiar de servicio
        # seleccionado (el detail panel se reconstruye desde acá, no al
        # revés), así que no se pierden ediciones al ir y volver.
        self._edits: dict[str, str] = {}
        self._selected_attr = _SETTINGS_SERVICES[0][0]

    def compose(self) -> ComposeResult:
        with Horizontal(id="settings-body"):
            with Vertical(id="settings-list", classes="panel") as list_panel:
                list_panel.border_title = "◈ SERVICIOS"
                for attr, svc in _SETTINGS_SERVICES:
                    with Horizontal(classes="settings-row"):
                        yield Checkbox(
                            svc.display_name,
                            value=getattr(self.cfg, attr).enabled,
                            id=f"svc-enabled-{attr}",
                        )
                        yield Button("parámetros ▸", id=f"svc-detail-{attr}", classes="settings-row-btn")
            yield VerticalScroll(id="settings-detail", classes="panel")
        yield Static("", id="settings-status", classes="nc-dim")
        with Horizontal(id="settings-footer"):
            yield Button("GUARDAR", id="btn-save", variant="success")
            yield Static("q / Esc para volver", classes="nc-dim")

    async def on_mount(self) -> None:
        await self._render_detail()

    async def _render_detail(self) -> None:
        svc_by_attr = dict(_SETTINGS_SERVICES)
        svc = svc_by_attr[self._selected_attr]
        sub = getattr(self.cfg, self._selected_attr)
        detail = self.query_one("#settings-detail", VerticalScroll)
        detail.border_title = f"◈ {svc.display_name} — PARÁMETROS"
        # remove_children() es async (AwaitRemove) — sin este await, mount_all()
        # de abajo corre antes de que el remove termine y revienta con
        # DuplicateIds al re-renderear el mismo servicio dos veces seguidas.
        await detail.remove_children()

        widgets = []
        for f in _FIELDS_BY_ATTR[self._selected_attr]:
            if f.attr == "enabled":
                continue  # ya está arriba, en la lista de servicios
            current = self._edits.get(f.env, _stringify(getattr(sub, f.attr)))
            widgets.append(Static(f.attr, classes="settings-field-label"))
            if f.kind is bool:
                widgets.append(Checkbox(f.env, value=current == "true", id=f"field-{f.env}"))
            else:
                widgets.append(Input(value=current, id=f"field-{f.env}"))
        await detail.mount_all(widgets)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        checkbox_id = event.checkbox.id or ""
        if checkbox_id.startswith("svc-enabled-"):
            attr = checkbox_id.removeprefix("svc-enabled-")
            env = next(f.env for f in _FIELDS_BY_ATTR[attr] if f.attr == "enabled")
            self._edits[env] = "true" if event.value else "false"
        elif checkbox_id.startswith("field-"):
            env = checkbox_id.removeprefix("field-")
            self._edits[env] = "true" if event.value else "false"

    def on_input_changed(self, event: Input.Changed) -> None:
        input_id = event.input.id or ""
        if input_id.startswith("field-"):
            env = input_id.removeprefix("field-")
            self._edits[env] = event.value

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "btn-save":
            self._save()
        elif button_id.startswith("svc-detail-"):
            self._selected_attr = button_id.removeprefix("svc-detail-")
            await self._render_detail()

    def _save(self) -> None:
        overrides = _diff_overrides(self.cfg, self._edits)
        status = self.query_one("#settings-status", Static)
        if not overrides:
            status.update("Nada para guardar — no tocaste ningún valor.")
            return
        update_env_file(_ENV_PATH, overrides, seed_from=_ENV_EXAMPLE_PATH)
        status.update(
            f"[{palette.SUCCESS}]Guardado ({len(overrides)} cambio(s)) — reiniciá Rinthel para aplicarlos.[/]"
        )

    def action_close(self) -> None:
        self.app.pop_screen()
