"""``Broadcaster`` — el fan-out genérico de ``/ws/monitor``. La emisión de
``phase_status``/``phase_log`` en sí (quién llama a ``broadcast`` y con qué
payload) vive en ``lifecycle/executor.py`` y se prueba en
``tests/lifecycle/test_executor.py``, inyectando una función de prueba."""

from rinthel_tui.api.ws import Broadcaster
from rinthel_tui.monitoring.domain.envelope import MessageType


async def test_broadcast_is_noop_with_no_connected_clients():
    await Broadcaster().broadcast(MessageType.PHASE_STATUS, {"label": "x", "status": "running"})  # no debe levantar


class _FakeWs:
    def __init__(self, on_send=None) -> None:
        self.sent: list[str] = []
        self.on_send = on_send

    async def send_text(self, text: str) -> None:
        self.sent.append(text)
        if self.on_send:
            self.on_send()


async def test_a_client_connecting_mid_broadcast_does_not_break_it():
    broadcaster = Broadcaster()
    late = _FakeWs()
    broadcaster.clients.add(_FakeWs(on_send=lambda: broadcaster.clients.add(late)))

    await broadcaster.broadcast(MessageType.PHASE_STATUS, {"label": "x", "status": "running"})
    await broadcaster.broadcast(MessageType.PHASE_STATUS, {"label": "x", "status": "done"})

    assert len(late.sent) == 1
