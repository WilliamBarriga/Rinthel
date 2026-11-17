"""Suite de contrato del puerto ``Clock`` (ADR 0005, regla 3): el reloj real y el
``ManualClock`` pasan lo mismo, así el doble no miente. ``sleep`` deja el
tiempo, visto por ``now``, al menos esos segundos más adelante."""

import asyncio
from datetime import timedelta

import pytest

from rinthel_tui.clock import ManualClock, SystemClock


@pytest.fixture(params=["system", "manual"])
def clock(request):
    return SystemClock() if request.param == "system" else ManualClock()


async def test_now_is_timezone_aware(clock):
    assert clock.now().tzinfo is not None


async def test_sleeping_moves_now_forward_by_at_least_that_much(clock):
    before = clock.now()

    await clock.sleep(0.05)

    assert clock.now() - before >= timedelta(seconds=0.04)


async def test_sleeping_zero_never_moves_time_backwards(clock):
    before = clock.now()

    await clock.sleep(0)

    assert clock.now() >= before


async def test_a_manual_clock_sleeps_without_waiting():
    clock = ManualClock()
    start = clock.now()

    await clock.sleep(3600)

    assert clock.now() - start == timedelta(hours=1)


async def test_a_manual_clock_records_each_sleep_and_yields_to_the_loop():
    clock = ManualClock()
    ran = []

    async def other() -> None:
        ran.append(True)

    task = asyncio.ensure_future(other())
    await clock.sleep(2)
    await clock.sleep(0.5)

    assert clock.sleeps == [2, 0.5]
    assert ran == [True]  # un bucle de polling no deja sin correr al resto
    await task


async def test_a_manual_clock_can_be_advanced_by_the_test():
    clock = ManualClock()
    start = clock.now()

    clock.advance(90)

    assert clock.now() - start == timedelta(seconds=90)
