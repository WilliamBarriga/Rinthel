from collections.abc import Mapping, Sequence

from rinthel_tui.lifecycle.domain.ports import Runner
from rinthel_tui.lifecycle.domain.types import ComposeService, RunResult


class DockerCompose:
    """``Compose`` sobre ``docker compose``, corrido por un ``Runner``: el argv
    vive acá y en ningún otro lugar. Siempre nombra el servicio: los stacks
    comparten un compose project, y un comando sin nombre tocaría a los otros."""

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    async def _compose(
        self, service: ComposeService, args: Sequence[str], *, env: Mapping[str, str] | None = None
    ) -> RunResult:
        profile = ["--profile", service.profile] if service.profile else []
        return await self._runner.run(
            ["docker", "compose", *profile, *args], cwd=service.directory, env={**service.env, **(env or {})}
        )

    async def up(
        self, service: ComposeService, *, build: Mapping[str, str] | None = None, wait: bool = False
    ) -> RunResult:
        if build is not None:
            build_args = [part for arg, value in build.items() for part in ("--build-arg", f"{arg}={value}")]
            built = await self._compose(service, ["build", *build_args, service.name])
            if built.rc != 0:
                return built
        return await self._compose(
            service, ["up", "-d", "--remove-orphans", *(["--wait"] if wait else []), service.name]
        )

    async def recreate(self, service: ComposeService) -> RunResult:
        return await self._compose(service, ["up", "-d", "--no-deps", service.name])

    async def down(self, service: ComposeService) -> RunResult:
        return await self._compose(service, ["down", service.name])

    async def exec(self, service: ComposeService, cmd: Sequence[str]) -> RunResult:
        return await self._compose(service, ["exec", "-T", service.name, *cmd])

    async def run(
        self, service: ComposeService, cmd: Sequence[str], *, env: Mapping[str, str] | None = None, build: bool = False
    ) -> RunResult:
        names = [part for name in (env or {}) for part in ("-e", name)]
        args = ["run", "--rm", "-T", "--no-deps", *(["--build"] if build else []), *names, service.name, *cmd]
        return await self._compose(service, args, env=env)

    async def logs(self, service: ComposeService, *, tail: int) -> RunResult:
        return await self._compose(service, ["logs", "--tail", str(tail), service.name])
