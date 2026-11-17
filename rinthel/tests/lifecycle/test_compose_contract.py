"""Suite de contrato del puerto ``Compose``: ``FakeCompose`` siempre, y
``DockerCompose`` contra un stack de un servicio en ``tmp_path`` cuando hay
docker (se saltea sin él, salvo con ``RINTHEL_REQUIRE_DOCKER_TESTS=1``)."""

import uuid
from dataclasses import dataclass

import pytest

from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner
from rinthel_tui.lifecycle.adapters.docker_compose import DockerCompose
from rinthel_tui.lifecycle.domain.types import ComposeService
from tests.lifecycle.fakes import FakeCompose
from tests.docker_env import IMAGE, docker, docker_available, skip_or_fail

COMPOSE_FILE = """\
name: {project}
services:
  app:
    image: {image}
    command: ["sleep", "300"]
    stop_grace_period: 1s
"""


@dataclass
class World:
    compose: object
    service: ComposeService
    unknown: ComposeService


@pytest.fixture(params=["docker", "fake"])
async def world(request, tmp_path):
    if request.param == "fake":
        yield World(
            FakeCompose(known=["app"]), ComposeService(tmp_path, "app"), ComposeService(tmp_path, "ghost")
        )
        return
    if not docker_available():
        skip_or_fail(f"hace falta docker con la imagen {IMAGE}")
    project = f"rinthel_contract_{uuid.uuid4().hex[:8]}"
    (tmp_path / "docker-compose.yaml").write_text(COMPOSE_FILE.format(project=project, image=IMAGE))
    yield World(
        DockerCompose(AsyncioRunner()), ComposeService(tmp_path, "app"), ComposeService(tmp_path, "ghost")
    )
    docker("compose", "-p", project, "down", "--remove-orphans", "-t", "1")


async def test_a_service_that_is_up_runs_commands_and_one_that_is_down_does_not(world):
    assert (await world.compose.up(world.service)).rc == 0
    assert (await world.compose.exec(world.service, ["true"])).rc == 0

    assert (await world.compose.down(world.service)).rc == 0
    assert (await world.compose.exec(world.service, ["true"])).rc != 0


async def test_recreate_leaves_the_service_up(world):
    await world.compose.up(world.service)

    assert (await world.compose.recreate(world.service)).rc == 0
    assert (await world.compose.exec(world.service, ["true"])).rc == 0


async def test_a_service_missing_from_the_compose_file_does_not_come_up(world):
    assert (await world.compose.up(world.unknown)).rc != 0


async def test_a_one_shot_run_finishes_without_leaving_the_service_up(world):
    assert (await world.compose.run(world.service, ["true"])).rc == 0
    assert (await world.compose.exec(world.service, ["true"])).rc != 0


async def test_logs_of_a_running_service_succeed(world):
    await world.compose.up(world.service)

    assert (await world.compose.logs(world.service, tail=5)).rc == 0
