"""La composición de INSTALL: lee ``RinthelConfig`` y arma el dataclass de
cada tarea que recibe su phase. Acá viven los pins (qué rama se clona): son
parte de *qué versión instalamos*, no un parámetro del admin, y las phases
solo ven el resultado."""

from dataclasses import dataclass
from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.instance import Instance

# ── tareas de INSTALL: lo que cada phase necesita, armado acá a partir de
# ``RinthelConfig`` y los pins ───────────────────────────────────────────────


@dataclass(frozen=True)
class LlamaCppInstall:
    repo_dir: Path
    repo_url: str
    branch: str


@dataclass(frozen=True)
class ModelDownload:
    """Un archivo que se baja con ``curl``. Con ``sha256`` se verifica y, si no
    coincide, se borra; sin él (el GGUF principal, que el admin elige) no."""

    what: str
    url: str
    dest: Path
    sha256: str | None = None
    size_hint: str = ""


@dataclass(frozen=True)
class PortalInstall:
    """El portal heredado: dónde vive su código (subtree del monorepo), de
    dónde se clona si falta, y lo que su ``.env`` toma de la Instance. Sale
    con el portal, cuando Deck lo reemplace."""

    instance: Instance
    dir: Path
    repo_url: str
    branch: str
    workspaces_dir: Path
    pi_agent_dir: Path
    llama_port: int
    llama_model: Path


@dataclass(frozen=True)
class UnderstoryInstall:
    instance: Instance
    dir: Path
    # El ``.env`` del portal: de ahí sale el token de Understory.
    portal_env: Path


@dataclass(frozen=True)
class InstanceSecrets:
    """Los secretos del ``.env`` raíz de la Instance."""

    instance: Instance


@dataclass(frozen=True)
class IdentitySetup:
    """Where the daemon's ``rinthel.db`` lives (users and Panel tokens)."""

    database_path: Path


LLAMACPP_BRANCH = "master"
PORTAL_BRANCH = "rinthel-pithagoras"


def llamacpp_install(cfg: RinthelConfig) -> LlamaCppInstall:
    return LlamaCppInstall(cfg.install.llamacpp_repo_dir, cfg.install.llamacpp_repo_url, LLAMACPP_BRANCH)


def llama_model(cfg: RinthelConfig) -> ModelDownload:
    return ModelDownload("Modelo GGUF", cfg.install.model_download_url, cfg.llama.model, size_hint="~22GB")


def portal_install(cfg: RinthelConfig) -> PortalInstall:
    return PortalInstall(
        instance=cfg.instance,
        dir=cfg.pithagoras.dir,
        repo_url=cfg.install.pithagoras_repo_url,
        branch=PORTAL_BRANCH,
        workspaces_dir=cfg.install.workspaces_dir,
        pi_agent_dir=cfg.install.pi_agent_dir,
        llama_port=cfg.llama.port,
        llama_model=cfg.llama.model,
    )


def understory_install(cfg: RinthelConfig) -> UnderstoryInstall:
    return UnderstoryInstall(cfg.instance, cfg.understory.dir, cfg.pithagoras.dir / ".env")


def instance_secrets(cfg: RinthelConfig) -> InstanceSecrets:
    return InstanceSecrets(cfg.instance)


def identity_setup(cfg: RinthelConfig) -> IdentitySetup:
    return IdentitySetup(cfg.instance.database_path)
