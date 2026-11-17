"""Fases de INSTALL — bootstrap de infra en una máquina nueva: build CUDA de
llama.cpp, descarga del modelo GGUF, scaffolding del portal y Understory,
secretos de la Instance, ``rinthel.db`` y el primer admin.

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

from dotenv import dotenv_values

from rinthel_tui import database
from rinthel_tui.config import RinthelConfig
from rinthel_tui.atomic_write import atomic_write
from rinthel_tui.env_file import update_env_file
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.identity.admin import FIRST_ADMIN, ensure_first_admin
from rinthel_tui.install.host_exec import prepare_host_exec
from rinthel_tui.install.portal_model import PORTAL_MODEL_ID, PORTAL_PROVIDER
from rinthel_tui.instance import RotatableSecret
from rinthel_tui.lifecycle import install_tasks
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.host import Host
from rinthel_tui.lifecycle.domain.outcome import PhaseReport, require_ok
from rinthel_tui.lifecycle.domain.phases.docker import phase_check_docker
from rinthel_tui.lifecycle.install_tasks import (
    IdentitySetup,
    InstanceSoulSeed,
    InstanceSecrets,
    LlamaCppInstall,
    ModelCatalogInstall,
    ModelDownload,
    PortalInstall,
    UnderstoryInstall,
)
from rinthel_tui.models.adapters.json_catalog import write_catalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels

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


# ── el portal heredado: sale entero cuando Deck lo reemplace ────────────────


def prepare_portal_for_windows(portal_dir: Path, report: PhaseReport) -> None:
    """Adapta el compose Linux del portal a Docker Desktop de forma idempotente."""
    compose_path = portal_dir / "docker-compose.yml"
    if compose_path.exists():
        compose = compose_path.read_text()
        updated = compose.replace(
            "    network_mode: host\n",
            '    ports:\n      - "127.0.0.1:${PORT:-4100}:${PORT:-4100}"\n',
        ).replace(
            "TS_AUTHKEY: ${TS_AUTHKEY:?set TS_AUTHKEY in .env}",
            "TS_AUTHKEY: ${TS_AUTHKEY:-}",
        )
        models_mount = (
            "      - ${PI_AGENT_DIR}/models.json:"
            "/data/home/.pi/agent/models.json:ro\n"
        )
        mount_anchor = (
            "      - ${PI_AGENT_DIR}/git/github.com/harms-haus/pi-processes:"
            "/data/home/.pi/agent/git/github.com/harms-haus/pi-processes:ro\n"
        )
        if models_mount not in updated and mount_anchor in updated:
            updated = updated.replace(mount_anchor, mount_anchor + models_mount)
        if updated != compose:
            compose_path.write_text(updated)
            report.success("Portal adaptado a la red local de Docker Desktop")

    dockerfile_path = portal_dir / "Dockerfile"
    if dockerfile_path.exists():
        dockerfile = dockerfile_path.read_text()
        updated = dockerfile
        if "chown -R node:node /data" not in dockerfile:
            updated = dockerfile.replace(
                "RUN mkdir -p /data/home /data/bin\n",
                "RUN mkdir -p /data/home /data/bin /data/sessions /data/channels /data/agent-home \\\n"
                "    && chown -R node:node /data\n",
            )
        if updated != dockerfile:
            dockerfile_path.write_text(updated)
            report.success("Permisos persistentes del portal preparados para Windows")


async def phase_install_setup_portal(host: Host, report: PhaseReport, *, task: PortalInstall) -> None:
    # ``.git`` propio (checkout standalone) o directorio no vacío (subtree del
    # monorepo, sin ``.git`` propio pero con contenido): no hay nada que clonar.
    if (task.dir / ".git").exists() or (task.dir.is_dir() and any(task.dir.iterdir())):
        report.warn(f"{task.dir} ya existe — omito clone")
    else:
        await _git_clone(host, report, task.repo_url, task.dir, "portal clone", branch=task.branch)
        report.success(f"Portal clonado en {task.dir}")

    if host.host_info.platform() == "windows":
        prepare_portal_for_windows(task.dir, report)

    # El portal chatea contra el Local model activo: su pi usa el proveedor
    # que el daemon mantiene (``install/portal_model.py``), en cada rerun.
    local_model = {"LLAMA_BASE_URL": task.llama_url, "PI_PROVIDER": PORTAL_PROVIDER, "PI_MODEL": PORTAL_MODEL_ID}
    env_path = task.dir / ".env"
    if env_path.exists():
        update_env_file(env_path, local_model)
        report.success("Portal apuntado al Local model activo")
        report.warn(f"{env_path} ya existe — conservo sus secretos")
    else:
        example_path = task.dir / ".env.example"
        if not example_path.exists():
            report.error(f"{example_path} no existe — no puedo generar .env")
            raise PhaseError("portal .env.example missing")
        overrides = {
            "PORTAL_PASSWORD": secrets.token_urlsafe(16),
            "PORTAL_SECRET": secrets.token_hex(32),
            "UNDERSTORY_TOKEN": secrets.token_hex(24),
            # No es un secreto — es la carpeta real que el portal monta en
            # /workspaces (ver RinthelConfig.install.workspaces_dir).
            "WORKSPACES_DIR": str(task.workspaces_dir),
            # Sin esto, Compose monta un directorio vacío donde Pi espera sus
            # paquetes y luego intenta instalar sobre un mount de solo lectura.
            "PI_AGENT_DIR": str(task.pi_agent_dir),
            **local_model,
        }
        update_env_file(env_path, overrides, seed_from=example_path)
        report.success(f"{env_path} generado")

    try:
        prepare_host_exec(task.instance.root, task.dir)
    except ValueError as exc:
        report.error(str(exc))
        raise PhaseError("host exec token conflict") from exc
    report.success("Token compartido de host exec preparado")


def _read_understory_token(portal_env: Path) -> str | None:
    if not portal_env.exists():
        return None
    return dotenv_values(portal_env).get("UNDERSTORY_TOKEN") or None


async def phase_install_setup_understory(host: Host, report: PhaseReport, *, task: UnderstoryInstall) -> None:
    """Prepara el despliegue de Understory. Sin clone: corre desde su imagen
    publicada, no desde fuente."""
    task.dir.mkdir(parents=True, exist_ok=True)

    compose_path = task.dir / "docker-compose.yml"
    if compose_path.exists():
        report.warn(f"{compose_path} ya existe — omito")
    else:
        template = importlib.resources.files("rinthel_tui.install") / "templates" / "understory-docker-compose.yml"
        compose_path.write_text(template.read_text())
        report.success(f"{compose_path} escrito")

    env_path = task.dir / ".env"
    if env_path.exists():
        report.warn(f"{env_path} ya existe — omito")
    else:
        token = _read_understory_token(task.portal_env)
        if not token:
            report.error(f"no encontré UNDERSTORY_TOKEN en {task.portal_env} — corré la fase del portal antes que esta")
            raise PhaseError("understory: UNDERSTORY_TOKEN not found")
        env_path.write_text(f"AUTH_TOKEN={token}\n")
        report.success(f"{env_path} generado")

    bundle_dir = task.dir / "bundle"
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
        report.success(f"bundle/ listo ({created} archivo(s) nuevo(s))")
    else:
        report.warn("bundle/ ya estaba completo — omito")


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

# Los secretos que la TUI y el daemon leen del ``.env`` raíz.
SECRETS_INSTALL = InstallUnit(
    label="INSTANCE",
    steps=(
        InstallStep("INSTANCE — secretos del .env", phase_install_instance_secrets, install_tasks.instance_secrets),
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

PITHAGORAS_INSTALL = InstallUnit(
    label="PITHAGORAS",
    enabled_of=lambda cfg: cfg.pithagoras.enabled,
    steps=(InstallStep("PITHAGORAS — clone + configurar", phase_install_setup_portal, install_tasks.portal_install),),
)

UNDERSTORY_INSTALL = InstallUnit(
    label="UNDERSTORY",
    enabled_of=lambda cfg: cfg.understory.enabled,
    steps=(
        InstallStep("UNDERSTORY — scaffold + configurar", phase_install_setup_understory, install_tasks.understory_install),
    ),
)

INSTALL_UNITS: list[InstallUnit] = [
    LLAMA_INSTALL, SECRETS_INSTALL, IDENTITY_INSTALL, DECK_INSTALL, PITHAGORAS_INSTALL, UNDERSTORY_INSTALL,
]
