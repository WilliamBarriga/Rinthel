"""``fake_host()`` arma un ``Host`` de dobles que comparten un solo ``log``:
es lo que permite afirmar el orden entre puertos (ADR 0005, regla 6)."""

import dataclasses

import pytest

from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.types import ComposeService
from tests.lifecycle.fakes import fake_host


async def test_every_port_logs_into_the_same_ordered_list(tmp_path):
    host, log = fake_host()
    host.compose.running.add("web")

    await host.probe.port_open(80)
    await host.compose.down(ComposeService(tmp_path, "web"))
    await host.clock.sleep(1)
    await host.runner.run(["true"])

    assert [event[0] for event in log] == ["port_open", "down", "run"]


def test_a_host_is_frozen():
    host, _ = fake_host()

    assert isinstance(host, Host)
    with pytest.raises(dataclasses.FrozenInstanceError):
        host.runner = None
