"""Badge de estado ONLINE/OFFLINE de un servicio HTTP, con poll propio.

Reemplaza ``_menu_refresh_status`` (rinthel-boot.sh): ahí el menú hacía un
curl throttled a mano cada ~3s para dos servicios fijos; acá cada badge es
autónomo y cualquier screen puede montar los que necesite (el footer del
menú hoy, MonitorScreen en Fase 5).
"""

import urllib.request

from textual.reactive import reactive
from textual.widgets import Static

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.managed_service import DockerComposeService, LocalProcessService


async def _check_online(url: str, timeout: float = 0.3) -> bool:
    import asyncio

    def _check() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=timeout):
                return True
        except OSError:
            return False

    return await asyncio.to_thread(_check)


class ServiceBadge(Static):
    """Usage: ServiceBadge("Understory", "http://localhost:3800")"""

    status: reactive[str] = reactive("...", init=False)

    def __init__(self, label: str, url: str, *, poll_interval: float = 3.0, id: str | None = None) -> None:
        super().__init__(f"{label}: ...", id=id, classes="service-badge")
        self.label_text = label
        self.url = url
        self.poll_interval = poll_interval

    @classmethod
    def for_service(
        cls,
        service: LocalProcessService | DockerComposeService,
        cfg: RinthelConfig,
        *,
        label: str | None = None,
        id: str | None = None,
        poll_interval: float = 3.0,
    ) -> "ServiceBadge":
        """Arma el badge a partir del registro de servicios (``services.py``)
        en vez de que cada screen retipee su propia URL — agregar un
        servicio nuevo ya no exige reconstruir ``http://host:puerto`` a mano
        por cada pantalla que quiera mostrarlo, solo pasar la instancia.
        ``label`` pisa ``service.display_name`` para las pantallas que ya
        mostraban un texto distinto (ej. "Whisper STT" vs. "whisper-server")."""
        if service.ready_url_of is None:
            raise ValueError(f"{service.display_name} no define ready_url_of — no se puede armar un badge")
        return cls(label or service.display_name, service.ready_url_of(cfg), id=id, poll_interval=poll_interval)

    def on_mount(self) -> None:
        self.set_interval(self.poll_interval, self._poll)
        self.run_worker(self._poll(), exclusive=True)

    async def _poll(self) -> None:
        online = await _check_online(self.url)
        self.status = "ONLINE" if online else "OFFLINE"

    def watch_status(self, status: str) -> None:
        self.update(f"{self.label_text}: {status}")
        self.set_class(status == "ONLINE", "-online")
        self.set_class(status == "OFFLINE", "-offline")
