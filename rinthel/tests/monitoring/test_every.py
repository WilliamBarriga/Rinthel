"""``every(interval, sample)``: una source periódica. Primera muestra
inmediata; un ``sample`` que levanta se saltea y se reintenta en el tick
siguiente."""

from rinthel_tui.clock import ManualClock
from rinthel_tui.monitoring.domain.monitor import every


async def test_a_failing_sample_is_skipped_and_retried_next_tick():
    calls = 0

    async def sample():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("nvidia-smi colgado")
        return {"tick": calls}

    source = every(0, sample, clock=ManualClock())()
    got = [await anext(source) for _ in range(3)]

    assert got == [{"tick": 1}, {"tick": 3}, {"tick": 4}]
