"""La composición de INSTALL: lee ``RinthelConfig`` y arma el dataclass de
cada tarea que recibe su phase. Acá viven los pins (qué rama se clona): son
parte de *qué versión instalamos*, no un parámetro del admin, y las phases
solo ven el resultado."""

from dataclasses import dataclass
from pathlib import Path

from rinthel_tui.config import RinthelConfig
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
class UnderstoryInstall:
    """Its token goes in the root ``.env``; its live bundle in ``bundle_dir``."""

    instance: Instance
    bundle_dir: Path


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


def llama_url(cfg: RinthelConfig) -> str:
    """La URL de llama-server que el daemon entrega a quien corre en Docker."""
    return f"http://{cfg.deck.host_address}:{cfg.llama.port}"


def understory_install(cfg: RinthelConfig) -> UnderstoryInstall:
    return UnderstoryInstall(cfg.instance, cfg.instance.understory_data_dir)


def instance_secrets(cfg: RinthelConfig) -> InstanceSecrets:
    return InstanceSecrets(cfg.instance)


def container_user(cfg: RinthelConfig) -> InstanceSecrets:
    """``PUID``/``PGID``/``DOCKER_GID`` live in the same root ``.env``."""
    return InstanceSecrets(cfg.instance)


def instance_soul(cfg: RinthelConfig) -> InstanceSoulSeed:
    return InstanceSoulSeed(cfg.instance.deck_data_dir / "instance" / "SOUL.md")


def identity_setup(cfg: RinthelConfig) -> IdentitySetup:
    return IdentitySetup(cfg.instance.database_path)
