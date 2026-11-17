"""Suite de contrato de ``ContainerStatus``: corre igual contra ``docker
compose ps`` (un ``docker`` falso en ``tmp_path``, pasado por constructor,
sobre la Instance del test) y el en memoria."""

import json

import pytest

from rinthel_tui.monitoring.adapters.docker_compose import DockerComposeContainers
from rinthel_tui.monitoring.adapters.memory import InMemoryContainers
from rinthel_tui.monitoring.domain.types import DockerContainer

UNDERSTORY = DockerContainer(name="understory-1", state="running", ports="3800->3800", status="Up 1m")
DECK = DockerContainer(name="rinthel-general-deck-1", state="exited", ports="-", status="Exited (0) 5 minutes ago")


class ComposeHarness:
    def __init__(self, cfg, tmp_path, fake_executable) -> None:
        self.fake_executable = fake_executable
        self.docker = tmp_path / "docker"
        self.status = DockerComposeContainers(lambda: cfg, docker=str(self.docker))

    def runs(self, *containers: DockerContainer) -> None:
        rows = [{"Name": c.name, "State": c.state, "Status": c.status, "Ports": c.ports} for c in containers]
        self.fake_executable(self.docker, f"print({json.dumps(rows)!r})\n")

    def has_no_docker(self) -> None:
        pass  # el ejecutable no existe


class MemoryHarness:
    def __init__(self, cfg, tmp_path, fake_executable) -> None:
        self.status = InMemoryContainers()

    def runs(self, *containers: DockerContainer) -> None:
        self.status.running = list(containers)

    def has_no_docker(self) -> None:
        self.status.running = []


@pytest.fixture(params=[ComposeHarness, MemoryHarness], ids=["docker-compose", "memory"])
def harness(request, cfg, tmp_path, fake_executable):
    return request.param(cfg, tmp_path, fake_executable)


async def test_lists_the_containers_up_or_not(harness):
    harness.runs(UNDERSTORY, DECK)

    assert await harness.status.containers() == [UNDERSTORY, DECK]


async def test_no_containers_is_an_empty_list(harness):
    harness.runs()

    assert await harness.status.containers() == []


async def test_without_docker_it_is_an_empty_list(harness):
    harness.has_no_docker()

    assert await harness.status.containers() == []
