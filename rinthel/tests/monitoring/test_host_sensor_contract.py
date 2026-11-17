"""Suite de contrato de ``HostSensor``: corre igual contra psutil (el host
real) y el en memoria. Lo que no se puede fijar del host se verifica como
invariante."""

import pytest

from rinthel_tui.monitoring.adapters.memory import InMemoryHost
from rinthel_tui.monitoring.adapters.psutil_host import PsutilHost
from rinthel_tui.monitoring.domain.types import CpuRamSample


@pytest.fixture(params=[PsutilHost, InMemoryHost], ids=["psutil", "memory"])
def sensor(request):
    return request.param()


async def test_a_reading_is_a_consistent_cpu_ram_sample(sensor):
    sample = await sensor.read()

    assert isinstance(sample, CpuRamSample)
    assert 0.0 <= sample.cpu_percent <= 100.0
    assert 0.0 <= sample.ram_percent <= 100.0
    assert 0.0 < sample.ram_used_gb <= sample.ram_total_gb


async def test_every_field_is_a_float(sensor):
    sample = await sensor.read()

    assert all(isinstance(v, float) for v in vars(sample).values())


async def test_the_in_memory_host_reports_what_it_is_given():
    sample = CpuRamSample(17.3, 12.4, 64.0, 19.4)

    assert await InMemoryHost(sample).read() == sample
