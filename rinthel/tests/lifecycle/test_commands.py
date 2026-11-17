"""``Lifecycle`` — cada comando corre su Lifecycle plan. Se inyecta un
``execute`` que registra el plan en vez de correrlo (los planes reales
tocan docker y procesos); qué hace el executor con el plan se prueba en
test_executor.py, y la forma de cada plan en test_specs.py."""

import pytest

from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.commands import Lifecycle
from rinthel_tui.lifecycle.domain.types import UnitOutcome


async def _broadcast(type_: str, data: dict) -> None:
    pass


@pytest.mark.parametrize(
    "command,plan_of",
    [
        ("boot", specs.boot_plan),
        ("terminate", specs.terminate_plan),
        ("reload", specs.reload_plan),
        ("install", specs.install_plan),
    ],
)
async def test_each_command_runs_its_plan_and_returns_its_outcomes(cfg, command, plan_of):
    ran = []

    async def execute(plan, broadcast):
        assert broadcast is _broadcast
        ran.append(plan)
        return [UnitOutcome(service="x", ok=True, message="hecho")]

    outcomes = await getattr(Lifecycle(cfg, _broadcast, execute=execute), command)()

    assert ran == [plan_of(cfg)]
    assert outcomes == [UnitOutcome(service="x", ok=True, message="hecho")]
