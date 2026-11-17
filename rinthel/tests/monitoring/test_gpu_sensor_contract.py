"""Suite de contrato de ``GpuSensor``: corre igual contra ``nvidia-smi`` (un
ejecutable falso en ``tmp_path``, pasado por constructor) y el en memoria.
Un sensor nunca levanta: sin GPU, o sin poder leerla, reporta
``available=False``."""

import pytest

from rinthel_tui.monitoring.adapters.memory import InMemoryGpu
from rinthel_tui.monitoring.adapters.nvidia_smi import NvidiaSmiGpu
from rinthel_tui.monitoring.domain.types import GpuSample

READING = GpuSample(True, utilization=42.0, memory_used=8192.0, memory_total=24576.0, temperature=61.0, power_draw=210.5)


class NvidiaSmiHarness:
    def __init__(self, tmp_path, fake_executable) -> None:
        self.fake_executable = fake_executable
        self.executable = tmp_path / "nvidia-smi"
        self.sensor = NvidiaSmiGpu(str(self.executable))

    def _script(self, body: str) -> None:
        self.fake_executable(self.executable, body)

    def reports(self, sample: GpuSample) -> None:
        fields = (sample.utilization, sample.memory_used, sample.memory_total, sample.temperature, sample.power_draw)
        csv = ", ".join("[N/A]" if f is None else str(f) for f in fields)
        self._script(f"print({csv!r})\n")

    def has_no_gpu(self) -> None:
        self._script("import sys\nsys.exit(9)\n")


class MemoryHarness:
    def __init__(self, tmp_path, fake_executable) -> None:
        self.sensor = InMemoryGpu()

    def reports(self, sample: GpuSample) -> None:
        self.sensor.sample = sample

    def has_no_gpu(self) -> None:
        self.sensor.sample = None


@pytest.fixture(params=[NvidiaSmiHarness, MemoryHarness], ids=["nvidia-smi", "memory"])
def harness(request, tmp_path, fake_executable):
    return request.param(tmp_path, fake_executable)


async def test_reads_what_the_gpu_reports(harness):
    harness.reports(READING)

    assert await harness.sensor.read() == READING


async def test_a_field_the_gpu_cannot_report_is_none(harness):
    harness.reports(GpuSample(True, 10.0, 1.0, 2.0, 50.0, None))

    assert await harness.sensor.read() == GpuSample(True, 10.0, 1.0, 2.0, 50.0, None)


async def test_without_a_gpu_it_reports_unavailable(harness):
    harness.has_no_gpu()

    assert await harness.sensor.read() == GpuSample(available=False)


async def test_nvidia_smi_that_is_not_installed_is_no_gpu(tmp_path):
    assert await NvidiaSmiGpu(str(tmp_path / "no-existe")).read() == GpuSample(available=False)
