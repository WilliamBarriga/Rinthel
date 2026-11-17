"""El reloj de la Instance, neutral: lo comparten los módulos que esperan o
miden tiempo (ADR 0004, ADR 0005). El dominio recibe un ``Clock`` en vez de
llamar a ``asyncio.sleep`` o ``datetime.now``, y las pruebas inyectan el
``ManualClock``, que no espera nunca."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual, con zona horaria."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Después de esto ``now()`` avanzó al menos ``seconds``."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ManualClock:
    """El tiempo lo mueve el test: ``sleep`` avanza ``now`` sin esperar, cede
    el turno al loop (un bucle de polling no lo deja sin correr) y anota el
    retraso en ``sleeps``."""

    def __init__(self, start: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> None:
        self._now = start
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)
        await asyncio.sleep(0)

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
