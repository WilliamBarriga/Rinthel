"""El argv exacto de ``docker compose`` se prueba solo acá, contra un
``FakeRunner`` que graba comandos (ADR 0005, regla 5). El resto de las pruebas
afirma la intención (``compose.up(service)``)."""

from pathlib import Path

import pytest

from rinthel_tui.lifecycle.adapters.docker_compose import DockerCompose
from rinthel_tui.lifecycle.domain.types import ComposeService
from tests.lifecycle.fakes import FakeRunner

DIR = Path("/srv/stack")
PLAIN = ComposeService(DIR, "web")
PROFILED = ComposeService(DIR, "qdrant", profile="qdrant", env={"QDRANT_PORT": "6333"})


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def compose(runner):
    return DockerCompose(runner)


async def _argvs(runner):
    return [list(call.cmd) for call in runner.calls]


async def test_up_names_the_service_and_removes_orphans(compose, runner):
    runner.script(["docker", "compose", "up", "-d", "--remove-orphans", "web"])

    result = await compose.up(PLAIN)

    assert result.rc == 0
    assert await _argvs(runner) == [["docker", "compose", "up", "-d", "--remove-orphans", "web"]]
    assert runner.calls[0].cwd == DIR


async def test_a_profile_goes_before_the_subcommand_and_the_env_travels_as_a_delta(compose, runner):
    await compose.up(PROFILED)

    assert await _argvs(runner) == [
        ["docker", "compose", "--profile", "qdrant", "up", "-d", "--remove-orphans", "qdrant"]
    ]
    assert dict(runner.calls[0].env) == {"QDRANT_PORT": "6333"}


async def test_up_with_wait_waits_for_healthy(compose, runner):
    await compose.up(PLAIN, wait=True)

    assert await _argvs(runner) == [["docker", "compose", "up", "-d", "--remove-orphans", "--wait", "web"]]


async def test_up_with_build_builds_first_with_each_build_arg_and_stops_if_the_build_fails(compose, runner):
    runner.script(["docker", "compose", "build", "--build-arg", "PI_VERSION=1.2.3", "web"], rc=2, output="boom")

    result = await compose.up(PLAIN, build={"PI_VERSION": "1.2.3"})

    assert (result.rc, result.output) == (2, "boom")
    assert await _argvs(runner) == [["docker", "compose", "build", "--build-arg", "PI_VERSION=1.2.3", "web"]]


async def test_up_with_build_then_ups_when_the_build_works(compose, runner):
    runner.script(["docker", "compose", "build", "web"])

    await compose.up(PLAIN, build={})

    assert await _argvs(runner) == [
        ["docker", "compose", "build", "web"],
        ["docker", "compose", "up", "-d", "--remove-orphans", "web"],
    ]


async def test_recreate_leaves_the_dependencies_alone(compose, runner):
    await compose.recreate(PLAIN)

    assert await _argvs(runner) == [["docker", "compose", "up", "-d", "--no-deps", "web"]]


async def test_down_names_the_service_so_the_rest_of_the_project_stays_up(compose, runner):
    await compose.down(PROFILED)

    assert await _argvs(runner) == [["docker", "compose", "--profile", "qdrant", "down", "qdrant"]]


async def test_exec_runs_without_a_tty(compose, runner):
    await compose.exec(PLAIN, ["pg_isready", "-U", "postgres"])

    assert await _argvs(runner) == [["docker", "compose", "exec", "-T", "web", "pg_isready", "-U", "postgres"]]


async def test_run_passes_env_names_not_values_in_the_argv(compose, runner):
    await compose.run(PROFILED, ["node", "migrate.js"], env={"OWNER_DSN": "postgres://secret"}, build=True)

    assert await _argvs(runner) == [
        [
            "docker", "compose", "--profile", "qdrant", "run", "--rm", "-T", "--no-deps", "--build",
            "-e", "OWNER_DSN", "qdrant", "node", "migrate.js",
        ]
    ]
    assert dict(runner.calls[0].env) == {"QDRANT_PORT": "6333", "OWNER_DSN": "postgres://secret"}
    assert "secret" not in " ".join(runner.calls[0].cmd)


async def test_logs_tails_the_service(compose, runner):
    await compose.logs(PLAIN, tail=5)

    assert await _argvs(runner) == [["docker", "compose", "logs", "--tail", "5", "web"]]
