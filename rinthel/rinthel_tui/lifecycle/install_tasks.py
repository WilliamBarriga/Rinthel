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


# ── voice (INSTALL ``--voice``) ─────────────────────────────────────────


@dataclass(frozen=True)
class PinnedBuild:
    """A checkout at a fixed commit (``sha``) in ``repo`` that leaves ``bin``."""

    what: str
    repo_url: str
    sha: str
    repo: Path
    bin: Path


@dataclass(frozen=True)
class VoiceCatalogInstall:
    """The default voice entries, added to the catalog if missing and made
    active where their Capability has none."""

    instance: Instance
    models: tuple[LocalModel, ...]


@dataclass(frozen=True)
class VoiceStart:
    """The ``cfg`` the voice services start from, once the catalog and
    ``instance.toml`` are re-read."""

    cfg: RinthelConfig


# whisper.cpp and audio.cpp at fixed commits; each model at a Hugging Face
# revision with its sha256 (HF's ``X-Linked-ETag``).
WHISPER_REPO = "https://github.com/ggml-org/whisper.cpp.git"
WHISPER_SHA = "a2b36eb677918d4f9ab1db7b8a7ff968563ed163"
WHISPER_MODEL_FILE = "ggml-base.bin"
WHISPER_MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp"
    f"/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/{WHISPER_MODEL_FILE}"
)
WHISPER_MODEL_SHA256 = "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"
AUDIOCPP_REPO = "https://github.com/0xShug0/audio.cpp.git"
AUDIOCPP_SHA = "5ba81ac54fb071b835680973f8868546b4db372b"
POCKET_TTS_FILE = "pocket-tts-spanish-q8_0.gguf"
POCKET_TTS_URL = (
    "https://huggingface.co/audio-cpp/audio.cpp-gguf"
    f"/resolve/6d5436fc85f7a20c2e9f4e472b7f3a532f686444/PocketTTS-GGUF/spanish/{POCKET_TTS_FILE}"
)
POCKET_TTS_SHA256 = "73f0e8fd85472057289b0ae6098be473a5d112cc01b0ecb17f423198bcf445e1"


def whisper_build(cfg: RinthelConfig) -> PinnedBuild:
    return PinnedBuild("whisper.cpp", WHISPER_REPO, WHISPER_SHA, cfg.whisper.repo, cfg.whisper.bin)


def audiocpp_build(cfg: RinthelConfig) -> PinnedBuild:
    return PinnedBuild("audio.cpp", AUDIOCPP_REPO, AUDIOCPP_SHA, cfg.audiocpp.repo, cfg.audiocpp.bin)


def whisper_model(cfg: RinthelConfig) -> ModelDownload:
    return ModelDownload("Whisper ggml-base", WHISPER_MODEL_URL, cfg.install.models_dir / WHISPER_MODEL_FILE,
                         WHISPER_MODEL_SHA256)


def pocket_tts(cfg: RinthelConfig) -> ModelDownload:
    return ModelDownload("Pocket-TTS", POCKET_TTS_URL, cfg.install.models_dir / POCKET_TTS_FILE, POCKET_TTS_SHA256)


def default_voice_models(cfg: RinthelConfig) -> tuple[LocalModel, LocalModel]:
    """The ``stt`` and ``tts`` entries INSTALL adds. Pocket-TTS does not speak
    without a voice, and its built-in ones are not in the GGUF: the fixed
    voice is a reference WAV of the audio.cpp checkout itself (Apache-2.0)."""
    stt = LocalModel("whisper-base", "Whisper base", "stt", whisper_model(cfg).dest, 0)
    tts = LocalModel(
        "pocket-tts-es", "Pocket-TTS español", "tts", pocket_tts(cfg).dest, 0,
        voice=cfg.audiocpp.repo / "assets" / "resources" / "b.wav",
    )
    return stt, tts


def voice_catalog(cfg: RinthelConfig) -> VoiceCatalogInstall:
    return VoiceCatalogInstall(cfg.instance, default_voice_models(cfg))


def voice_start(cfg: RinthelConfig) -> VoiceStart:
    return VoiceStart(cfg)
