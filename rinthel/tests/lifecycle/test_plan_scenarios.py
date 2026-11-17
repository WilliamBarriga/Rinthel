"""Boot y Terminate con la infra rota, corridos como los corre el daemon:
``Lifecycle`` con los planes reales de ``specs.py`` y el ``executor`` real.
Solo los bordes están falsos (procesos, puertos, ``docker``), así que el
stack de la máquina no se toca."""

import pytest

from rinthel_tui.lifecycle import executor, services
from rinthel_tui.lifecycle.commands import Lifecycle
from tests.lifecycle.fakes import fake_host

INFO = ["docker", "info"]


async def _no_broadcast(type_: str, data: dict) -> None:
    pass


@pytest.fixture
def host():
    return fake_host()[0]


@pytest.fixture
def lifecycle(cfg, host) -> Lifecycle:
    return Lifecycle(cfg, _no_broadcast, execute=executor.bound_to(host))


async def test_boot_with_docker_down_stops_at_the_first_failure_and_starts_nothing(host, lifecycle):
    host.runner.script(INFO, rc=1)  # y `sudo -n` tampoco lo levanta

    outcomes = await lifecycle.boot()

    assert [(o.service, o.ok) for o in outcomes] == [("docker", False)]
    assert "DOCKER DAEMON INACTIVO" in outcomes[0].message
    assert host.processes.spawns == []
    assert host.compose.calls == []


async def test_boot_spawns_llama_server_with_its_argv_and_brings_up_the_docker_services(cfg, host, lifecycle):
    host.runner.script(INFO, rc=0)
    host.probe.script_http(services.LLAMA_SERVICE.ready_url_of(cfg), True)
    for svc in services.DOCKER_SERVICES:
        host.probe.script_http(svc.ready_url_of(cfg), True)
    cfg.instance.root.mkdir(exist_ok=True)

    outcomes = await lifecycle.boot()

    assert all(o.ok for o in outcomes), outcomes
    (spawn,) = host.processes.spawns
    assert list(spawn.argv) == services.LLAMA_SERVICE.build_argv(cfg)
    assert {call[1] for call in host.compose.calls if call[0] == "up"} == {"understory", "deck"}


async def test_terminate_with_llama_already_dead_warns_and_shuts_down_the_rest(cfg, host, lifecycle):
    outcomes = await lifecycle.terminate()

    by_service = {o.service: o for o in outcomes}
    llama = services.LLAMA_SERVICE
    assert by_service["llama-server"].ok
    assert f"No había {llama.display_name} corriendo en :{llama.port_of(cfg)}" in by_service["llama-server"].message
    assert all(o.ok for o in outcomes)
    downed = {call[1] for call in host.compose.calls if call[0] == "down"}
    assert downed == {s.compose_service_name for s in services.DOCKER_SERVICES}


async def test_terminate_keeps_going_when_a_docker_service_does_not_go_down(cfg, host, lifecycle):
    host.compose.fail_rc("down", 1, "boom")  # la primera que se baje

    outcomes = await lifecycle.terminate()

    failed = [o for o in outcomes if not o.ok]
    assert [o.service for o in failed] == [services.DOCKER_SERVICES[0].display_name.lower()]
    assert "docker compose down falló" in failed[0].message
    assert [call[1] for call in host.compose.calls if call[0] == "down"] == ["understory", "deck"]
