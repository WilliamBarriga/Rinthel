"""Fases de INSTALL — bootstrap de infra en una máquina nueva: build CUDA de
llama.cpp, descarga del modelo GGUF, scaffolding de Pithagoras/Understory.

Mismo protocolo que ``phases.py`` (``async def phase_*(cfg, report) -> None``,
``PhaseError``); reusa ``_run``/``_docker_compose``/``phase_check_docker`` de
ahí por import, no duplica lógica de subprocess. INSTALL **configura**, no
bootea — nunca hace ``docker compose up``; para eso está ``[1] BOOT``
(``specs.BOOT_PHASES``). Cada fase es idempotente: reruns seguros, nunca pisa
algo que ya funciona.
"""

import importlib.resources
import os
import secrets
import shutil
from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.phases import (
    PhaseError,
    PhaseReport,
    _run,
    phase_check_docker,
)

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
    if (cfg.llamacpp_repo_dir / ".git").exists():
        report.warn(f"{cfg.llamacpp_repo_dir} ya existe — omito clone")
        return
    cfg.llamacpp_repo_dir.parent.mkdir(parents=True, exist_ok=True)
    rc = await _run(
        ["git", "clone", "--branch", _LLAMACPP_BRANCH, cfg.llamacpp_repo_url, str(cfg.llamacpp_repo_dir)],
        report,
    )
    if rc != 0:
        report.error(f"git clone falló (rc {rc})")
        raise PhaseError(f"llama.cpp clone failed (rc {rc})")
    report.success(f"llama.cpp clonado en {cfg.llamacpp_repo_dir}")


async def phase_install_build_llamacpp(cfg: RinthelConfig, report: PhaseReport) -> None:
    build_dir = cfg.llamacpp_repo_dir / "build-cuda"
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
        cwd=cfg.llamacpp_repo_dir,
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
        cwd=cfg.llamacpp_repo_dir,
    )
    if rc != 0:
        report.error(f"cmake build falló (rc {rc})")
        raise PhaseError(f"llama.cpp build failed (rc {rc})")
    report.success(f"llama.cpp compilado en {build_dir}")


async def phase_install_download_model(cfg: RinthelConfig, report: PhaseReport) -> None:
    if cfg.model.exists() and cfg.model.stat().st_size > 0:
        report.warn(f"{cfg.model} ya existe — omito descarga")
        return
    cfg.model.parent.mkdir(parents=True, exist_ok=True)
    report.warn(f"Descargando modelo (~22GB) a {cfg.model} — puede tardar bastante")
    rc = await _run(
        ["curl", "-L", "-C", "-", "-o", str(cfg.model), cfg.model_download_url],
        report,
    )
    if rc != 0:
        report.error(f"descarga falló (rc {rc})")
        raise PhaseError(f"model download failed (rc {rc})")
    report.success(f"Modelo descargado en {cfg.model}")


def _write_env_from_example(example: Path, target: Path, overrides: dict[str, str]) -> None:
    """Copia ``example`` a ``target`` reemplazando solo las claves en
    ``overrides`` — el resto del archivo (comentarios incluidos) queda
    intacto."""
    out: list[str] = []
    seen: set[str] = set()
    for line in example.read_text().splitlines():
        stripped = line.strip()
        key = stripped.split("=", 1)[0] if "=" in stripped and not stripped.startswith("#") else None
        if key in overrides:
            out.append(f"{key}={overrides[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in overrides.items():
        if key not in seen:
            out.append(f"{key}={value}")
    target.write_text("\n".join(out) + "\n")


async def phase_install_setup_pithagoras(cfg: RinthelConfig, report: PhaseReport) -> None:
    if (cfg.pithagoras_dir / ".git").exists():
        report.warn(f"{cfg.pithagoras_dir} ya existe — omito clone")
    else:
        cfg.pithagoras_dir.parent.mkdir(parents=True, exist_ok=True)
        rc = await _run(
            ["git", "clone", "--branch", _PITHAGORAS_BRANCH, cfg.pithagoras_repo_url, str(cfg.pithagoras_dir)],
            report,
        )
        if rc != 0:
            report.error(f"git clone falló (rc {rc})")
            raise PhaseError(f"pithagoras clone failed (rc {rc})")
        report.success(f"Pithagoras clonado en {cfg.pithagoras_dir}")

    env_path = cfg.pithagoras_dir / ".env"
    if env_path.exists():
        report.warn(f"{env_path} ya existe — no lo piso")
        return

    example_path = cfg.pithagoras_dir / ".env.example"
    if not example_path.exists():
        report.error(f"{example_path} no existe — no puedo generar .env")
        raise PhaseError("pithagoras .env.example missing")

    overrides = {
        "PORTAL_PASSWORD": secrets.token_urlsafe(16),
        "PORTAL_SECRET": secrets.token_hex(32),
        "UNDERSTORY_TOKEN": secrets.token_hex(24),
        # No es un secreto — es la carpeta real que Pithagoras monta en
        # /workspaces (ver RinthelConfig.workspaces_dir).
        "WORKSPACES_DIR": str(cfg.workspaces_dir),
        # Sin esto, Compose monta en silencio un directorio vacío
        # (dueño root) donde va node_modules de pi-web-access/pi-mcp-adapter
        # — la primera conversación falla con "npm install ... failed with
        # code 254" porque ese mount queda de solo lectura. Ver .env.example
        # de pithagoras.
        "PI_AGENT_DIR": str(cfg.pi_agent_dir),
    }
    _write_env_from_example(example_path, env_path, overrides)
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
    cfg.understory_dir.mkdir(parents=True, exist_ok=True)

    compose_path = cfg.understory_dir / "docker-compose.yml"
    if compose_path.exists():
        report.warn(f"{compose_path} ya existe — omito")
    else:
        template = (
            importlib.resources.files("rinthel_tui.install")
            / "templates" / "understory-docker-compose.yml"
        )
        compose_path.write_text(template.read_text())
        report.success(f"{compose_path} escrito")

    env_path = cfg.understory_dir / ".env"
    if env_path.exists():
        report.warn(f"{env_path} ya existe — omito")
    else:
        token = _read_understory_token(cfg.pithagoras_dir / ".env")
        if not token:
            report.error(
                f"no encontré UNDERSTORY_TOKEN en {cfg.pithagoras_dir / '.env'} "
                "— corré [5/6] PITHAGORAS antes que esta fase"
            )
            raise PhaseError("understory: UNDERSTORY_TOKEN not found")
        env_path.write_text(f"AUTH_TOKEN={token}\n")
        report.success(f"{env_path} generado")

    bundle_dir = cfg.understory_dir / "bundle"
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
