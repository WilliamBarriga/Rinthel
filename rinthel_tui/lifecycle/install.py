"""Fases de INSTALL — bootstrap de infra en una máquina nueva: build CUDA de
llama.cpp, descarga del modelo GGUF, scaffolding de Pithagoras/Understory.

Mismo protocolo que el resto de lifecycle/ (``async def phase_*(cfg, report)
-> None``, ``PhaseError``); reusa ``_run`` (subprocess) de
``managed_service.py`` y ``phase_check_docker`` de ``phases.py`` por import,
no duplica lógica. INSTALL **configura**, no bootea — nunca hace ``docker
compose up``; para eso está ``[1] BOOT`` (``specs.boot_phases``). Cada fase
es idempotente: reruns seguros, nunca pisa algo que ya funciona.
"""

import importlib.resources
import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Coroutine

from rinthel_tui.config import RinthelConfig
from rinthel_tui.env_file import update_env_file
from rinthel_tui.lifecycle.managed_service import _run
from rinthel_tui.lifecycle.phases import phase_check_docker
from rinthel_tui.lifecycle.types import PhaseError, PhaseReport

PhaseFn = Callable[[RinthelConfig, PhaseReport], Coroutine[Any, Any, None]]

# Hardcodeados igual que otros detalles de infra que no tiene sentido
# overridear vía config (mismo criterio que el puerto de llama-server no
# siendo la branch de git que se clona): la branch es parte de "qué versión
# de la fuente de verdad clonamos", no un parámetro de usuario.
_LLAMACPP_BRANCH = "perf"
_PITHAGORAS_BRANCH = "rinthel-pithagoras"

_UNDERSTORY_BUNDLE_DIRS = ("agents", "extensions", "projects", "reference", "users")


def _require_tool(name: str, report: PhaseReport, hint: str) -> None:
    if shutil.which(name) is None:
        report.error(f"falta '{name}' — {hint}")
        raise PhaseError(f"{name} not found")
    report.success(f"{name} encontrado")


def _find_nvcc() -> bool:
    if shutil.which("nvcc") is not None:
        return True
    return any(Path("/usr/local").glob("cuda*/bin/nvcc"))


async def phase_install_preflight(cfg: RinthelConfig, report: PhaseReport) -> None:
    """Detecta lo que hace falta para compilar/correr todo — no instala
    drivers ni el CUDA toolkit, solo avisa qué falta con un mensaje
    accionable."""
    _require_tool("git", report, "sudo apt-get install -y git")
    _require_tool("curl", report, "sudo apt-get install -y curl")
    _require_tool("cmake", report, "sudo apt-get install -y cmake")
    _require_tool("nvidia-smi", report, "instalá el driver NVIDIA antes de continuar")

    if not _find_nvcc():
        report.error("falta nvcc — instalá el CUDA toolkit antes de continuar")
        raise PhaseError("nvcc not found")
    report.success("nvcc encontrado")

    await phase_check_docker(cfg, report)


async def phase_install_clone_llamacpp(cfg: RinthelConfig, report: PhaseReport) -> None:
    if (cfg.install.llamacpp_repo_dir / ".git").exists():
        report.warn(f"{cfg.install.llamacpp_repo_dir} ya existe — omito clone")
        return
    cfg.install.llamacpp_repo_dir.parent.mkdir(parents=True, exist_ok=True)
    rc = await _run(
        ["git", "clone", "--branch", _LLAMACPP_BRANCH, cfg.install.llamacpp_repo_url, str(cfg.install.llamacpp_repo_dir)],
        report,
    )
    if rc != 0:
        report.error(f"git clone falló (rc {rc})")
        raise PhaseError(f"llama.cpp clone failed (rc {rc})")
    report.success(f"llama.cpp clonado en {cfg.install.llamacpp_repo_dir}")


async def phase_install_build_llamacpp(cfg: RinthelConfig, report: PhaseReport) -> None:
    build_dir = cfg.install.llamacpp_repo_dir / "build-cuda"
    if (build_dir / "bin" / "llama-server").exists():
        report.warn(f"{build_dir}/bin/llama-server ya existe — omito build")
        return

    report.warn("Compilando llama.cpp con CUDA — puede tardar 10-30 minutos")
    rc = await _run(
        [
            "cmake", "-B", str(build_dir),
            "-DGGML_CUDA=ON",
            "-DCMAKE_BUILD_TYPE=Release",
            # native, no el 89 hardcodeado de la máquina original — compila
            # para la arquitectura real de la GPU de cada máquina.
            "-DCMAKE_CUDA_ARCHITECTURES=native",
        ],
        report,
        cwd=cfg.install.llamacpp_repo_dir,
    )
    if rc != 0:
        report.error(f"cmake configure falló (rc {rc})")
        raise PhaseError(f"llama.cpp cmake configure failed (rc {rc})")

    rc = await _run(
        [
            "cmake", "--build", str(build_dir),
            "-j", str(os.cpu_count() or 4),
            "--target", "llama-server", "llama-moe-trace",
        ],
        report,
        cwd=cfg.install.llamacpp_repo_dir,
    )
    if rc != 0:
        report.error(f"cmake build falló (rc {rc})")
        raise PhaseError(f"llama.cpp build failed (rc {rc})")
    report.success(f"llama.cpp compilado en {build_dir}")


async def phase_install_download_model(cfg: RinthelConfig, report: PhaseReport) -> None:
    if cfg.llama.model.exists() and cfg.llama.model.stat().st_size > 0:
        report.warn(f"{cfg.llama.model} ya existe — omito descarga")
        return
    cfg.llama.model.parent.mkdir(parents=True, exist_ok=True)
    report.warn(f"Descargando modelo (~22GB) a {cfg.llama.model} — puede tardar bastante")
    rc = await _run(
        ["curl", "-L", "-C", "-", "-o", str(cfg.llama.model), cfg.install.model_download_url],
        report,
    )
    if rc != 0:
        report.error(f"descarga falló (rc {rc})")
        raise PhaseError(f"model download failed (rc {rc})")
    report.success(f"Modelo descargado en {cfg.llama.model}")


async def phase_install_setup_pithagoras(cfg: RinthelConfig, report: PhaseReport) -> None:
    if (cfg.pithagoras.dir / ".git").exists():
        report.warn(f"{cfg.pithagoras.dir} ya existe — omito clone")
    else:
        cfg.pithagoras.dir.parent.mkdir(parents=True, exist_ok=True)
        rc = await _run(
            ["git", "clone", "--branch", _PITHAGORAS_BRANCH, cfg.install.pithagoras_repo_url, str(cfg.pithagoras.dir)],
            report,
        )
        if rc != 0:
            report.error(f"git clone falló (rc {rc})")
            raise PhaseError(f"pithagoras clone failed (rc {rc})")
        report.success(f"Pithagoras clonado en {cfg.pithagoras.dir}")

    env_path = cfg.pithagoras.dir / ".env"
    if env_path.exists():
        report.warn(f"{env_path} ya existe — no lo piso")
        return

    example_path = cfg.pithagoras.dir / ".env.example"
    if not example_path.exists():
        report.error(f"{example_path} no existe — no puedo generar .env")
        raise PhaseError("pithagoras .env.example missing")

    overrides = {
        "PORTAL_PASSWORD": secrets.token_urlsafe(16),
        "PORTAL_SECRET": secrets.token_hex(32),
        "UNDERSTORY_TOKEN": secrets.token_hex(24),
        # No es un secreto — es la carpeta real que Pithagoras monta en
        # /workspaces (ver RinthelConfig.workspaces_dir).
        "WORKSPACES_DIR": str(cfg.install.workspaces_dir),
        # Sin esto, Compose monta en silencio un directorio vacío
        # (dueño root) donde va node_modules de pi-web-access/pi-mcp-adapter
        # — la primera conversación falla con "npm install ... failed with
        # code 254" porque ese mount queda de solo lectura. Ver .env.example
        # de pithagoras.
        "PI_AGENT_DIR": str(cfg.install.pi_agent_dir),
    }
    update_env_file(env_path, overrides, seed_from=example_path)
    report.success(f"{env_path} generado")


def _read_understory_token(pithagoras_env: Path) -> str | None:
    if not pithagoras_env.exists():
        return None
    for line in pithagoras_env.read_text().splitlines():
        if line.startswith("UNDERSTORY_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


async def phase_install_setup_understory(cfg: RinthelConfig, report: PhaseReport) -> None:
    """Sin clone — Understory corre desde la imagen publicada
    ``ghcr.io/thecodacus/understory:latest``, no desde fuente."""
    cfg.understory.dir.mkdir(parents=True, exist_ok=True)

    compose_path = cfg.understory.dir / "docker-compose.yml"
    if compose_path.exists():
        report.warn(f"{compose_path} ya existe — omito")
    else:
        template = (
            importlib.resources.files("rinthel_tui.install")
            / "templates" / "understory-docker-compose.yml"
        )
        compose_path.write_text(template.read_text())
        report.success(f"{compose_path} escrito")

    env_path = cfg.understory.dir / ".env"
    if env_path.exists():
        report.warn(f"{env_path} ya existe — omito")
    else:
        token = _read_understory_token(cfg.pithagoras.dir / ".env")
        if not token:
            report.error(
                f"no encontré UNDERSTORY_TOKEN en {cfg.pithagoras.dir / '.env'} "
                "— corré [5/6] PITHAGORAS antes que esta fase"
            )
            raise PhaseError("understory: UNDERSTORY_TOKEN not found")
        env_path.write_text(f"AUTH_TOKEN={token}\n")
        report.success(f"{env_path} generado")

    bundle_dir = cfg.understory.dir / "bundle"
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


# ── unidades instalables — un servicio con enabled=False no aparece en
# [0] INSTALL (ver specs.install_phases), aunque su INSTALL_PHASES original
# seguía siendo relevante para BOOT/DOWN/RELOAD vía enabled_of ────────────


@dataclass(frozen=True, kw_only=True)
class InstallUnit:
    label: str
    enabled_of: Callable[[RinthelConfig], bool]
    steps: tuple[tuple[str, PhaseFn], ...]


LLAMA_INSTALL = InstallUnit(
    label="LLAMA.CPP + modelo",
    enabled_of=lambda cfg: cfg.llama.enabled,
    steps=(
        ("LLAMA.CPP — clone", phase_install_clone_llamacpp),
        ("LLAMA.CPP — build CUDA (native)", phase_install_build_llamacpp),
        ("MODELO GGUF — descarga", phase_install_download_model),
    ),
)

PITHAGORAS_INSTALL = InstallUnit(
    label="PITHAGORAS",
    enabled_of=lambda cfg: cfg.pithagoras.enabled,
    steps=(("PITHAGORAS — clone + configurar", phase_install_setup_pithagoras),),
)

UNDERSTORY_INSTALL = InstallUnit(
    label="UNDERSTORY",
    enabled_of=lambda cfg: cfg.understory.enabled,
    steps=(("UNDERSTORY — scaffold + configurar", phase_install_setup_understory),),
)

INSTALL_UNITS: list[InstallUnit] = [
    LLAMA_INSTALL, PITHAGORAS_INSTALL, UNDERSTORY_INSTALL,
]
