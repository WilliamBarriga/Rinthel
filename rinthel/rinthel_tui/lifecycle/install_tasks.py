"""La composición de INSTALL: lee ``RinthelConfig`` y arma el dataclass de
cada tarea que recibe su phase. Acá viven los pins (qué rama se clona): son
parte de *qué versión instalamos*, no un parámetro del admin, y las phases
solo ven el resultado."""

from dataclasses import dataclass
from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.install.portal_model import PortalModel
from rinthel_tui.instance import Instance
from rinthel_tui.models.domain.types import LocalModel

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
class ModelCatalogInstall:
    """El catálogo inicial de la Instance: la entrada del Local model por
    defecto (``model``), activa si no hay otro activo."""

    instance: Instance
    model: LocalModel


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
    # Cómo el portal llega a llama-server (armada con ``deck.host_address``).
    llama_url: str


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


@dataclass(frozen=True)
class InstanceSoulSeed:
    """Where Deck reads the Instance SOUL (the ``SOUL.md`` every member's
    Sessions load), on Deck's volume."""

    path: Path


LLAMACPP_BRANCH = "master"
PORTAL_BRANCH = "rinthel-pithagoras"


def llamacpp_install(cfg: RinthelConfig) -> LlamaCppInstall:
    return LlamaCppInstall(cfg.install.llamacpp_repo_dir, cfg.install.llamacpp_repo_url, LLAMACPP_BRANCH)


def default_local_model(cfg: RinthelConfig) -> LocalModel:
    """La entrada del catálogo del Local model por defecto del Validated
    profile, con su GGUF en ``install.models_dir``."""
    default = cfg.profile.model
    return LocalModel(
        id=default.id,
        name=default.name,
        capability="llm",
        gguf=cfg.install.models_dir / default.file,
        context_window=default.context_window,
        reasoning_format=default.reasoning_format,
    )


def llama_model(cfg: RinthelConfig) -> ModelDownload:
    """Solo el GGUF por defecto: otros Local models los agrega el admin a mano."""
    return ModelDownload("Modelo GGUF", cfg.profile.model.url, default_local_model(cfg).gguf, size_hint="~22GB")


def model_catalog(cfg: RinthelConfig) -> ModelCatalogInstall:
    return ModelCatalogInstall(cfg.instance, default_local_model(cfg))


def portal_install(cfg: RinthelConfig) -> PortalInstall:
    return PortalInstall(
        instance=cfg.instance,
        dir=cfg.pithagoras.dir,
        repo_url=cfg.install.pithagoras_repo_url,
        branch=PORTAL_BRANCH,
        workspaces_dir=cfg.install.workspaces_dir,
        pi_agent_dir=cfg.install.pi_agent_dir,
        llama_url=llama_url(cfg),
    )


def llama_url(cfg: RinthelConfig) -> str:
    """La URL de llama-server que el daemon entrega a quien corre en Docker."""
    return f"http://{cfg.deck.host_address}:{cfg.llama.port}"


def portal_model(cfg: RinthelConfig) -> PortalModel:
    return PortalModel(
        linux_agent_dir=cfg.instance.portal_data_dir / "home" / ".pi" / "agent",
        windows_agent_dir=cfg.install.pi_agent_dir,
        llama_url=llama_url(cfg),
        model=cfg.local_model,
    )


def understory_install(cfg: RinthelConfig) -> UnderstoryInstall:
    return UnderstoryInstall(cfg.instance, cfg.understory.dir, cfg.pithagoras.dir / ".env")


def instance_secrets(cfg: RinthelConfig) -> InstanceSecrets:
    return InstanceSecrets(cfg.instance)


def instance_soul(cfg: RinthelConfig) -> InstanceSoulSeed:
    return InstanceSoulSeed(cfg.instance.deck_data_dir / "instance" / "SOUL.md")


def identity_setup(cfg: RinthelConfig) -> IdentitySetup:
    return IdentitySetup(cfg.instance.database_path)
