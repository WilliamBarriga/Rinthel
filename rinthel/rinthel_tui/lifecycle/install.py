"""Fases de INSTALL — bootstrap de infra en una máquina nueva: build CUDA de
llama.cpp, descarga del modelo GGUF, secretos y usuario de contenedores en el
``.env`` raíz, Understory, ``rinthel.db`` y el primer admin.

Mismo protocolo que el resto de lifecycle/ (``async def phase_*(host, report,
**kwargs) -> None``, ``PhaseError``): comandos por ``Host.runner``, lo que la
máquina dice por ``Host.host_info`` y la tarea de cada fase (``install_tasks.py``)
por ``kwargs``. INSTALL **configura**, no bootea — nunca hace ``docker
compose up``; para eso está ``[1] BOOT`` (``specs.boot_plan``). Cada fase es
idempotente: reruns seguros, nunca pisa algo que ya funciona.
"""

import importlib.resources
import secrets
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rinthel_tui import database
from rinthel_tui.config import RinthelConfig, with_voice_from_instance
from rinthel_tui.atomic_write import atomic_write
from rinthel_tui.env_file import update_env_file
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.admin import FIRST_ADMIN, ensure_first_admin
from rinthel_tui.install.host_exec import prepare_host_exec
from rinthel_tui.instance import RotatableSecret
from rinthel_tui.lifecycle import install_tasks, services
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport, require_ok
from rinthel_tui.lifecycle.domain.phases import managed_service
from rinthel_tui.lifecycle.domain.phases.docker import phase_check_docker
from rinthel_tui.lifecycle.install_tasks import (
    IdentitySetup,
    InstanceSoulSeed,
    InstanceSecrets,
    LlamaCppInstall,
    ModelCatalogInstall,
    ModelDownload,
    PinnedBuild,
    UnderstoryInstall,
    VoiceCatalogInstall,
    VoiceStart,
)
from rinthel_tui.models.adapters.json_catalog import add_to_catalog, write_catalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from rinthel_tui.models.domain.errors import CatalogUnavailable

PhaseFn = Callable[..., Coroutine[Any, Any, None]]

_UNDERSTORY_BUNDLE_DIRS = ("agents", "extensions", "projects", "reference", "users")

_WINDOWS_TOOL_HINTS = {
    "git": "instala Git for Windows (winget install --id Git.Git -e)",
    "curl": "actualiza Windows o instala curl y agrégalo a PATH",
    "cmake": "instala CMake (winget install --id Kitware.CMake -e)",
}


def _tool_hint(host: Host, name: str) -> str:
    if host.host_info.platform() == "windows":
        return _WINDOWS_TOOL_HINTS[name]
    return f"sudo apt-get install -y {name}"


def _require_tool(host: Host, name: str, report: PhaseReport, hint: str) -> str:
    path = host.host_info.which(name)
    if path is None:
        report.error(f"falta '{name}' — {hint}")
        raise PhaseError(f"{name} not found")
    report.success(f"{name} encontrado")
    return path


def _require_nvcc(host: Host, report: PhaseReport) -> str:
    nvcc = host.host_info.find_nvcc()
    if nvcc is None:
        report.error("falta nvcc — instalá el CUDA toolkit antes de continuar")
        raise PhaseError("nvcc not found")
    return nvcc


async def _run_or_fail(
    host: Host,
    report: PhaseReport,
    cmd: list[str],
    what: str,
    *,
    label: str | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """``what`` es para el ``PhaseError``; ``label`` es lo que lee el admin
    (por defecto, el programa que falló)."""
    result = await host.runner.run(cmd, cwd=cwd, env=env)
    require_ok(report, result, failed=f"{label or Path(cmd[0]).name} falló", error=f"{what} failed at {cmd[:3]}")


async def phase_install_preflight(host: Host, report: PhaseReport) -> None:
    """Detecta lo que hace falta para compilar/correr todo — no instala
    drivers ni el CUDA toolkit, solo avisa qué falta con un mensaje
    accionable."""
    for tool in ("git", "curl", "cmake"):
        _require_tool(host, tool, report, _tool_hint(host, tool))
    driver = _require_tool(host, "nvidia-smi", report, "instalá el driver NVIDIA antes de continuar")
    result = await host.runner.run([driver])
    require_ok(
        report, result,
        failed="nvidia-smi falló — revisá el driver NVIDIA antes de continuar",
        error="nvidia-smi execution failed — revisá el driver NVIDIA antes de continuar",
    )
    nvcc = _require_nvcc(host, report)
    result = await host.runner.run([nvcc, "--version"])
    require_ok(
        report, result,
        failed="nvcc falló — revisá el CUDA toolkit antes de continuar",
        error="nvcc execution failed — revisá el CUDA toolkit antes de continuar",
    )
    report.success("nvcc operativo")
    await phase_check_docker(host, report)


async def _git_clone(
    host: Host, report: PhaseReport, url: str, dest: Path, what: str, *, branch: str | None = None
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", *(["--branch", branch] if branch else []), url, str(dest)]
    await _run_or_fail(host, report, cmd, what, label="git clone")


async def phase_install_clone_llamacpp(host: Host, report: PhaseReport, *, task: LlamaCppInstall) -> None:
    if (task.repo_dir / ".git").exists():
        report.warn(f"{task.repo_dir} ya existe — omito clone")
        origin = await host.runner.run(["git", "-C", str(task.repo_dir), "remote", "get-url", "origin"])
        if origin.rc == 0 and "thecodacus/llama.cpp" in origin.output:
            report.warn(
                "ese checkout es el fork viejo thecodacus/llama.cpp (rama perf): Rinthel ahora "
                "usa llama.cpp upstream — cloná ggml-org/llama.cpp en otro directorio, "
                "compilalo y apuntá RINTHEL_LLAMACPP_REPO_DIR y RINTHEL_LLAMA_BIN ahí"
            )
        return
    await _git_clone(host, report, task.repo_url, task.repo_dir, "llama.cpp clone", branch=task.branch)
    report.success(f"llama.cpp clonado en {task.repo_dir}")


async def phase_install_build_llamacpp(host: Host, report: PhaseReport, *, task: LlamaCppInstall) -> None:
    build_dir = task.repo_dir / "build-cuda"
    existing = host.host_info.find_llama_server(build_dir)
    if existing is not None:
        report.warn(f"{existing} ya existe — omito build")
        return

    nvcc = _require_nvcc(host, report)
    # Where cmake lives is the host's business (Visual Studio bundles its own).
    cmake = host.host_info.which("cmake") or "cmake"
    report.warn("Compilando llama.cpp con CUDA — puede tardar 10-30 minutos")
    await _run_or_fail(
        host,
        report,
        [
            cmake, "-B", str(build_dir),
            "-DGGML_CUDA=ON",
            f"-DCMAKE_CUDA_COMPILER={nvcc}",
            "-DCMAKE_BUILD_TYPE=Release",
            # native, no el 89 hardcodeado de la máquina original — compila
            # para la arquitectura real de la GPU de cada máquina.
            "-DCMAKE_CUDA_ARCHITECTURES=native",
        ],
        "llama.cpp cmake configure",
        label="cmake configure",
        cwd=task.repo_dir,
    )
    await _run_or_fail(
        host,
        report,
        [
            cmake, "--build", str(build_dir),
            # `--config Release`: los generadores multi-config (Visual Studio)
            # lo necesitan; los de un solo config lo ignoran.
            "--config", "Release",
            "--parallel", str(host.host_info.cpu_count()),
            "--target", "llama-server",
        ],
        "llama.cpp build",
        label="cmake build",
        cwd=task.repo_dir,
    )
    report.success(f"llama.cpp compilado en {build_dir}")


async def phase_install_download(host: Host, report: PhaseReport, *, task: ModelDownload) -> None:
    """Reanuda en un ``.part`` y publica solo tras validar la descarga.

    Por compatibilidad, un final no vacío sin hash conocido se conserva.
    Con hash, solo se omite un final verificado; no se reemplaza hasta validar
    la descarga nueva. Un parcial con hash incorrecto se elimina para reintentar.
    """
    dest = task.dest
    if dest.exists() and dest.stat().st_size > 0:
        if task.sha256 is None or await host.host_info.sha256(dest) == task.sha256:
            report.warn(f"{dest} ya existe — omito descarga")
            return
        report.warn(f"sha256 de {dest.name} no coincide — descargo reemplazo")
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    size = f" ({task.size_hint})" if task.size_hint else ""
    report.warn(f"Descargando {task.what}{size} a {dest} — puede tardar bastante")
    await _run_or_fail(
        host, report, ["curl", "--fail", "-L", "-C", "-", "-o", str(partial), task.url], f"{task.what} download", label="descarga"
    )
    if not partial.exists() or partial.stat().st_size == 0:
        report.error(f"{task.what}: descarga vacía")
        raise PhaseError(f"{task.what} empty download")
    if task.sha256 is not None:
        got = await host.host_info.sha256(partial)
        if got != task.sha256:
            partial.unlink()
            report.error(f"sha256 de {dest.name} no coincide ({got}) — lo borro")
            raise PhaseError(f"{task.what} sha256 mismatch")
    partial.replace(dest)
    report.success(f"{task.what} descargado en {dest}")


async def phase_install_model_catalog(host: Host, report: PhaseReport, *, task: ModelCatalogInstall) -> None:
    """El catálogo inicial (``models.local.json``) con el Local model por
    defecto, su ejemplo documentado al lado y ese modelo activo en
    ``instance.toml``. Nunca pisa lo que ya existe: el catálogo es del admin."""
    instance = task.instance
    if instance.models_catalog_path.exists():
        report.warn(f"{instance.models_catalog_path} ya existe — omito")
    else:
        write_catalog(instance.models_catalog_path, [task.model])
        report.success(f"Catálogo de Local models escrito en {instance.models_catalog_path}")
    if not instance.models_example_path.exists():
        template = importlib.resources.files("rinthel_tui.install") / "templates" / "models.local.example.json"
        instance.models_example_path.write_text(template.read_text())
        report.success(f"Ejemplo del catálogo escrito en {instance.models_example_path}")
    active = TomlActiveModels(instance.instance_toml_path)
    current = active.get("llm")
    if current is None:
        active.set("llm", task.model.id)
        report.success(f"Local model activo: {task.model.id}")
    else:
        report.warn(f"Local model activo ya elegido ({current}) — omito")


# ── Understory: un token en el .env raíz y el bundle en data/understory ──────


async def phase_install_setup_understory(host: Host, report: PhaseReport, *, task: UnderstoryInstall) -> None:
    """Prepara Understory, que corre desde su subtree con el compose raíz: un
    solo token en el ``.env`` raíz, ``UNDERSTORY_TOKEN`` (el compose raíz se
    lo pasa a Understory como ``AUTH_TOKEN`` y Deck lo presenta) y el bundle
    vivo en ``data/understory``. Nunca pisa un token ni un archivo del bundle
    que ya existan."""
    instance = task.instance
    if instance.get("UNDERSTORY_TOKEN"):
        report.warn("token de Understory ya estaba seteado — omito")
    else:
        update_env_file(instance.env_path, {"UNDERSTORY_TOKEN": secrets.token_hex(24)}, seed_from=instance.env_example_path)
        report.success(f"UNDERSTORY_TOKEN en {instance.env_path}")
    instance.env_path.chmod(0o600)

    bundle_dir = task.bundle_dir
    created = 0
    for sub in _UNDERSTORY_BUNDLE_DIRS:
        sub_dir = bundle_dir / sub
        sub_dir.mkdir(parents=True, exist_ok=True)
        index = sub_dir / "index.md"
        if not index.exists():
            index.write_text(f"# {sub}\n")
            created += 1
    for name, heading in (("index.md", "bundle"), ("log.md", "log")):
        f = bundle_dir / name
        if not f.exists():
            f.write_text(f"# {heading}\n")
            created += 1

    if created:
        report.success(f"{bundle_dir} listo ({created} archivo(s) nuevo(s))")
    else:
        report.warn(f"{bundle_dir} ya estaba completo — omito")


async def phase_install_container_user(host: Host, report: PhaseReport, *, task: InstanceSecrets) -> None:
    """En Linux los contenedores que escriben en ``data/`` corren con el
    uid/gid de quien corre la Instance (``PUID``/``PGID``), así lo que dejan
    se puede editar desde afuera; ``DOCKER_GID`` es el grupo que da acceso al
    socket de Docker. Se escriben en el ``.env`` raíz solo si faltan: lo que
    el admin puso gana. Windows no tiene ninguno de los tres."""
    ids = host.host_info.user_ids()
    if ids is None:
        report.warn("esta Platform no corre contenedores con el usuario del host — omito")
        return
    instance = task.instance
    wanted = {"PUID": str(ids[0]), "PGID": str(ids[1])}
    docker_gid = host.host_info.group_id("docker")
    if docker_gid is None:
        report.warn("no hay grupo 'docker' en el host — DOCKER_GID sin setear; reintentá tras instalar Docker")
    else:
        wanted["DOCKER_GID"] = str(docker_gid)
    missing = {key: value for key, value in wanted.items() if not instance.get(key)}
    if not missing:
        report.warn("PUID/PGID/DOCKER_GID ya estaban seteados — omito")
        return
    update_env_file(instance.env_path, missing, seed_from=instance.env_example_path)
    instance.env_path.chmod(0o600)
    report.success(f"{', '.join(f'{k}={v}' for k, v in missing.items())} en {instance.env_path}")


# What compose reads on Windows: the root compose plus the tracked override
# (bridge network, loopback-published ports, `host.docker.internal`). The
# separator is written too, so the same line means the same on every host.
WINDOWS_COMPOSE = {
    "COMPOSE_FILE": "docker-compose.yaml;compose/windows.override.yaml",
    "COMPOSE_PATH_SEPARATOR": ";",
}


async def phase_install_platform_compose(host: Host, report: PhaseReport, *, task: InstanceSecrets) -> None:
    """Picks the compose files of the Platform in the root ``.env``: on
    Windows the root compose plus ``compose/windows.override.yaml``; Linux
    runs the root compose alone and writes nothing. A ``COMPOSE_FILE`` the
    admin set wins."""
    if host.host_info.platform() != "windows":
        report.success("compose raíz, sin override en esta Platform")
        return
    instance = task.instance
    current = instance.get("COMPOSE_FILE")
    if current:
        if current != WINDOWS_COMPOSE["COMPOSE_FILE"]:
            report.warn(f"COMPOSE_FILE ya estaba seteado ({current}) — omito; Deck en Windows necesita el override")
        else:
            report.warn("COMPOSE_FILE ya estaba seteado — omito")
        return
    update_env_file(instance.env_path, WINDOWS_COMPOSE, seed_from=instance.env_example_path)
    report.success(f"COMPOSE_FILE={WINDOWS_COMPOSE['COMPOSE_FILE']} en {instance.env_path}")


async def phase_install_host_exec_token(host: Host, report: PhaseReport, *, task: InstanceSecrets) -> None:
    """El token que comparten ``hostexecd`` y quien le pide comandos, en el
    ``.env`` raíz. El boot lo asegura igual (``rinthel-boot.sh``). En
    Windows ``hostexecd`` no corre: no hay token que escribir."""
    if host.host_info.platform() == "windows":
        report.warn("host exec es solo de Linux — omito el token en esta Platform")
        return
    try:
        generated = prepare_host_exec(task.instance)
    except ValueError as exc:
        report.error(str(exc))
        raise PhaseError("host exec token conflict") from exc
    if generated:
        report.success(f"RINTHEL_HOSTEXECD_TOKEN generado en {task.instance.env_path}")
    else:
        report.warn("RINTHEL_HOSTEXECD_TOKEN ya estaba seteado — omito")


async def phase_install_instance_secrets(host: Host, report: PhaseReport, *, task: InstanceSecrets) -> None:
    """Genera en el ``.env`` raíz los secretos que faltan: el de servicio
    (la TUI ante el daemon) y el del panel (firma los Panel tokens). El
    archivo es la fuente de verdad (``Instance.get``), no ``cfg``, que es una
    foto del arranque."""
    instance = task.instance
    if not instance.env_path.exists() and not instance.env_example_path.exists():
        report.error(f"{instance.env_example_path} no existe — no puedo generar los secretos")
        raise PhaseError("root .env.example missing")
    for key in RotatableSecret:
        if instance.ensure_secret(key):
            report.success(f"{key} generado en {instance.env_path} — reiniciá el daemon para que tome efecto")
        else:
            report.warn(f"{key} ya estaba seteado — omito")


async def phase_install_instance_soul(host: Host, report: PhaseReport, *, task: InstanceSoulSeed) -> None:
    """Seeds the Instance SOUL from the template, once: an empty SOUL leaves a
    member's Agent without an identity. One that is already there (the admin
    edited it) is never touched."""
    if task.path.exists():
        report.warn(f"{task.path} ya existe — omito")
        return
    template = importlib.resources.files("rinthel_tui.install") / "templates" / "instance-soul.md"
    atomic_write(task.path, template.read_text())
    report.success(f"SOUL de la Instance sembrada en {task.path}")


async def phase_install_identity(host: Host, report: PhaseReport, *, task: IdentitySetup) -> None:
    """Migrates ``rinthel.db`` and, with no active admin, makes ``admin`` one
    with a random password reported once. No prompt, like every INSTALL
    phase; ``reset-admin`` is the recovery if the password is lost."""
    try:
        database.migrate(task.database_path)
    except database.DatabaseError as exc:
        report.error(str(exc))
        raise PhaseError("rinthel.db unusable") from exc
    report.success(f"identidad en {task.database_path} lista")
    password = ensure_first_admin(SqliteIdentity(task.database_path))
    if password is None:
        report.warn("ya hay un admin activo — omito el primer admin")
        return
    report.success(
        f"admin creado — usuario: {FIRST_ADMIN}  contraseña: {password}  "
        "(copiala ahora, no se vuelve a mostrar — cambiala después del primer login)"
    )


# ── Voice (``--voice``, Linux only): whisper.cpp in CPU, audio.cpp in CUDA ──


async def _checkout_pinned(host: Host, report: PhaseReport, task: PinnedBuild) -> None:
    """``task.repo`` at ``task.sha``: cloned if missing, fetched and moved to
    the pin if it is already there (INSTALL with voice is repeatable)."""
    repo = str(task.repo)
    if (task.repo / ".git").exists():
        await _run_or_fail(host, report, ["git", "-C", repo, "fetch", "--tags", "origin"], task.what, label="git fetch")
    else:
        await _git_clone(host, report, task.repo_url, task.repo, task.what)
    await _run_or_fail(host, report, ["git", "-C", repo, "checkout", task.sha], task.what, label="git checkout")
    await _run_or_fail(
        host, report, ["git", "-C", repo, "submodule", "update", "--init", "--recursive"], task.what,
        label="git submodule",
    )


async def phase_install_whisper(host: Host, report: PhaseReport, *, task: PinnedBuild) -> None:
    """whisper.cpp at its pin, only ``whisper-server``, for CPU."""
    if task.bin.exists():
        report.warn(f"{task.bin} ya existe — omito build")
        return
    await _checkout_pinned(host, report, task)
    build = task.bin.parents[1]
    cmake = host.host_info.which("cmake") or "cmake"
    await _run_or_fail(
        host, report,
        [cmake, "-S", str(task.repo), "-B", str(build),
         "-DCMAKE_BUILD_TYPE=Release", "-DGGML_CUDA=OFF", "-DWHISPER_BUILD_SERVER=ON"],
        task.what, label="cmake configure",
    )
    await _run_or_fail(
        host, report,
        [cmake, "--build", str(build), "--target", "whisper-server", "-j", str(host.host_info.cpu_count())],
        task.what, label="cmake build",
    )
    report.success(f"whisper-server compilado en {task.bin}")


async def phase_install_audiocpp(host: Host, report: PhaseReport, *, task: PinnedBuild) -> None:
    """audio.cpp at its pin, the CUDA build of ``audiocpp_server`` with only
    Pocket-TTS (``--model-set custom``): no model manager, that is its UI's."""
    if task.bin.exists():
        report.warn(f"{task.bin} ya existe — omito build")
        return
    nvcc = _require_nvcc(host, report)
    await _checkout_pinned(host, report, task)
    report.warn("Compilando audio.cpp con CUDA — puede tardar varios minutos")
    await _run_or_fail(
        host, report,
        [
            "bash", "scripts/build_linux.sh",
            "--cuda", "on", "--vulkan", "off", "--hip", "off",
            "--build-dir", str(task.bin.parents[1]), "--build-type", "Release",
            "--model-set", "custom", "--models", "pocket_tts",
            "--target", "audiocpp_server", "--jobs", str(host.host_info.cpu_count()),
        ],
        task.what, label="build de audio.cpp", cwd=task.repo,
        # With the toolkit outside PATH (``/usr/local/cuda/bin``) CMake does
        # not find the CUDA compiler on its own.
        env={"CUDACXX": nvcc},
    )
    report.success(f"audiocpp_server compilado en {task.bin}")


async def phase_install_voice_catalog(host: Host, report: PhaseReport, *, task: VoiceCatalogInstall) -> None:
    """Adds the default voice entries that are missing and makes each one
    active where its Capability has none. An entry or a choice of the admin
    is never touched."""
    path = task.instance.models_catalog_path
    try:
        added = add_to_catalog(path, task.models)
    except CatalogUnavailable as exc:
        report.error(f"catálogo de Local models ilegible: {exc} — corregilo a mano")
        raise PhaseError("models catalog unreadable") from exc
    if added:
        report.success(f"{', '.join(added)} agregados a {path}")
    else:
        report.warn("las entradas de voz ya estaban en el catálogo — omito")
    active = TomlActiveModels(task.instance.instance_toml_path)
    for model in task.models:
        current = active.get(model.capability)
        if current is None:
            active.set(model.capability, model.id)
            report.success(f"Local model activo de {model.capability}: {model.id}")
        else:
            report.warn(f"{model.capability} ya tiene Local model activo ({current}) — omito")


async def phase_install_voice_start(host: Host, report: PhaseReport, *, task: VoiceStart) -> None:
    """Restarts each voice service with its active Local model (kill, spawn,
    ready; each step required), so an Instance that is already running ends
    with ``stt``/``tts`` up. A Capability without a usable active model is
    left off with a warning."""
    cfg = with_voice_from_instance(task.cfg)
    for warning in cfg.voice_warnings:
        report.warn(warning)
    for service in (services.WHISPER_SERVICE, services.AUDIOCPP_SERVICE):
        if not service.enabled_of(cfg):
            report.warn(f"{service.display_name}: sin Local model activo usable — no arranca")
            continue
        spec = service.spec(cfg)
        await managed_service.phase_kill(host, report, service=spec, required=True)
        await managed_service.phase_spawn(host, report, service=spec)
        await managed_service.phase_wait_ready(host, report, service=spec, required=True)


# ── unidades instalables — un servicio con enabled=False no aparece en
# [0] INSTALL (ver specs.install_plan), aunque sigue siendo relevante para
# BOOT/TERMINATE/RELOAD vía enabled_of ─────────────────────────────────────


@dataclass(frozen=True)
class InstallStep:
    """Una fase de una unidad. ``task`` arma, desde ``cfg``, la tarea que la
    fase recibe: ``fn(host, report, task=task(cfg))``."""

    label: str
    fn: PhaseFn
    task: Callable[[RinthelConfig], Any]


def _always(cfg: RinthelConfig) -> bool:
    return True


@dataclass(frozen=True, kw_only=True)
class InstallUnit:
    label: str
    steps: tuple[InstallStep, ...]
    enabled_of: Callable[[RinthelConfig], bool] = _always


LLAMA_INSTALL = InstallUnit(
    label="LLAMA.CPP + modelo",
    enabled_of=lambda cfg: cfg.llama.enabled,
    steps=(
        InstallStep("LLAMA.CPP — clone", phase_install_clone_llamacpp, install_tasks.llamacpp_install),
        InstallStep("LLAMA.CPP — build CUDA (native)", phase_install_build_llamacpp, install_tasks.llamacpp_install),
        InstallStep("MODELO GGUF — descarga", phase_install_download, install_tasks.llama_model),
        InstallStep("LOCAL MODELS — catálogo inicial", phase_install_model_catalog, install_tasks.model_catalog),
    ),
)

# Lo que el daemon, ``hostexecd`` y compose leen del ``.env`` raíz.
SECRETS_INSTALL = InstallUnit(
    label="INSTANCE",
    steps=(
        InstallStep("INSTANCE — secretos del .env", phase_install_instance_secrets, install_tasks.instance_secrets),
        InstallStep("INSTANCE — token de host exec", phase_install_host_exec_token, install_tasks.instance_secrets),
        InstallStep("INSTANCE — usuario de los contenedores", phase_install_container_user, install_tasks.container_user),
        InstallStep("INSTANCE — compose de la Platform", phase_install_platform_compose, install_tasks.container_user),
    ),
)

# The daemon's ``rinthel.db`` and the first admin.
IDENTITY_INSTALL = InstallUnit(
    label="IDENTITY",
    steps=(InstallStep("IDENTITY — rinthel.db + primer admin", phase_install_identity, install_tasks.identity_setup),),
)

# What Deck reads from its volume before its first boot.
DECK_INSTALL = InstallUnit(
    label="DECK",
    enabled_of=lambda cfg: cfg.deck.enabled,
    steps=(InstallStep("DECK — SOUL de la Instance", phase_install_instance_soul, install_tasks.instance_soul),),
)

UNDERSTORY_INSTALL = InstallUnit(
    label="UNDERSTORY",
    enabled_of=lambda cfg: cfg.understory.enabled,
    steps=(
        InstallStep("UNDERSTORY — token + bundle", phase_install_setup_understory, install_tasks.understory_install),
    ),
)

INSTALL_UNITS: list[InstallUnit] = [
    LLAMA_INSTALL, SECRETS_INSTALL, IDENTITY_INSTALL, DECK_INSTALL, UNDERSTORY_INSTALL,
]

# Opt-in (INSTALL ``--voice``), so outside ``INSTALL_UNITS``: ``specs.install_plan``
# appends it last, on Linux only.
VOICE_INSTALL = InstallUnit(
    label="VOZ",
    steps=(
        InstallStep("WHISPER.CPP — clone + build CPU", phase_install_whisper, install_tasks.whisper_build),
        InstallStep("WHISPER — modelo ggml-base", phase_install_download, install_tasks.whisper_model),
        InstallStep("AUDIO.CPP — clone + build CUDA", phase_install_audiocpp, install_tasks.audiocpp_build),
        InstallStep("POCKET-TTS — GGUF español", phase_install_download, install_tasks.pocket_tts),
        InstallStep("VOZ — catálogo y Local models activos", phase_install_voice_catalog, install_tasks.voice_catalog),
        InstallStep("VOZ — arrancar stt/tts", phase_install_voice_start, install_tasks.voice_start),
    ),
)
