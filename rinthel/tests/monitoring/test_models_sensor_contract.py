"""Contract suite of the ``ModelsSensor`` port: ``ManagedServicesSensor`` (the
test's ``cfg`` with only Understory enabled, a fixed resolution and the
``Probe`` double) and ``InMemoryModels`` pass the same checks."""

import dataclasses

import pytest

from rinthel_tui.monitoring.adapters.managed_services import ManagedServicesSensor
from rinthel_tui.monitoring.adapters.memory import InMemoryModels
from rinthel_tui.monitoring.domain.types import CapabilityStatus, ModelsStatus, ServiceStatus
from tests.lifecycle.fakes import FakeProbe


class ManagedHarness:
    def __init__(self, cfg) -> None:
        self.cfg = dataclasses.replace(cfg, deck=dataclasses.replace(cfg.deck, enabled=False))
        self.probe = FakeProbe()
        self.sensor = ManagedServicesSensor(lambda: self.cfg, lambda c: ("qwen", None) if c == "llm" else (None, None),
                                            self.probe.http_ok)

    def everything_answers(self, answers: bool) -> None:
        self.probe.script_http(f"http://127.0.0.1:{self.cfg.llama.port}/v1/models", answers)
        self.probe.script_http(f"http://127.0.0.1:{self.cfg.understory.port}/", answers)


class MemoryHarness:
    def __init__(self, cfg) -> None:
        self.sensor = InMemoryModels()

    def everything_answers(self, answers: bool) -> None:
        state = "ready" if answers else "down"
        self.sensor.status = ModelsStatus(
            capabilities=[CapabilityStatus("llm", "qwen", state)], services=[ServiceStatus("Understory", state)]
        )


@pytest.fixture(params=[ManagedHarness, MemoryHarness], ids=["managed-services", "memory"])
def harness(request, cfg):
    return request.param(cfg)


@pytest.mark.parametrize(("answers", "state"), [(True, "ready"), (False, "down")])
async def test_llm_and_each_service_carry_whether_they_answer(harness, answers, state):
    harness.everything_answers(answers)

    status = await harness.sensor.read()

    assert status == ModelsStatus(
        capabilities=[CapabilityStatus("llm", "qwen", state)], services=[ServiceStatus("Understory", state)]
    )
