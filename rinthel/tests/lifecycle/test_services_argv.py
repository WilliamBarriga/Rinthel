"""``_llama_argv`` — el armado del comando de ``llama-server`` con el Local
model activo: MTP y ``--mmproj`` los decide su entrada del catálogo. El argv
completo del Validated profile está fijado en
``tests/models/test_validated_profile.py``.

Puro: sin subprocess/red, solo un ``RinthelConfig`` (fixture ``cfg`` de
``conftest.py``) y el argv que se le pasaría a ``Popen``."""

import dataclasses
import json
from pathlib import Path

import pytest

from rinthel_tui.config import with_local_model
from rinthel_tui.lifecycle import services
from rinthel_tui.lifecycle.services import _llama_argv
from rinthel_tui.models.domain.types import LocalModel


def _with_model(cfg, **changes):
    return dataclasses.replace(cfg, local_model=dataclasses.replace(cfg.local_model, **changes))


def _flag_value(argv, flag):
    """Valor de ``--flag`` en el argv, o ``None`` si el flag no está."""
    return argv[argv.index(flag) + 1] if flag in argv else None


def test_the_model_file_and_window_come_from_the_active_local_model(cfg):
    argv = _llama_argv(_with_model(cfg, gguf=Path("/m/otro.gguf"), context_window=4096))
    assert _flag_value(argv, "-m") == "/m/otro.gguf"
    assert _flag_value(argv, "-c") == "4096"


def test_mtp_off_forces_spec_type_none_regardless_of_spec_type(cfg):
    cfg = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, spec_type="draft-mtp"))
    assert _flag_value(_llama_argv(_with_model(cfg, mtp=False)), "--spec-type") == "none"


def test_mtp_on_uses_configured_spec_type(cfg):
    cfg = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, spec_type="draft-mtp"))
    argv = _llama_argv(_with_model(cfg, mtp=True))
    assert _flag_value(argv, "--spec-type") == "draft-mtp"
    assert _flag_value(argv, "--spec-draft-n-max") == str(cfg.llama.spec_draft_n_max)


def test_mtp_on_omits_mmproj_that_llama_cpp_does_not_support(cfg):
    # llama.cpp no soporta --mmproj junto a spec decoding (test-tarkAIrk/
    # handoff/03) — el flag se saltea, el catálogo no se toca.
    vision = {"mmproj": Path("/m/mmproj-F16.gguf")}
    assert _flag_value(_llama_argv(_with_model(cfg, mtp=False, **vision)), "--mmproj") == "/m/mmproj-F16.gguf"
    assert _flag_value(_llama_argv(_with_model(cfg, mtp=True, **vision)), "--mmproj") is None


def test_a_model_without_mmproj_has_no_vision_flag(cfg):
    assert "--mmproj" not in _llama_argv(_with_model(cfg, mmproj=None))


def test_model_overrides_reach_the_argv(cfg):
    argv = _llama_argv(_with_model(cfg, overrides={"temperature": 0.6}))
    assert _flag_value(argv, "--temp") == "0.6"


def test_without_an_active_local_model_there_is_nothing_to_spawn(cfg):
    assert _llama_argv(dataclasses.replace(cfg, local_model=None)) == []


def test_moe_cache_mib_flag_only_when_positive(cfg):
    off = _llama_argv(dataclasses.replace(cfg, moe=dataclasses.replace(cfg.moe, cache_mib=0)))
    on = _llama_argv(dataclasses.replace(cfg, moe=dataclasses.replace(cfg.moe, cache_mib=512)))
    assert "--moe-cache-mib" not in off
    assert _flag_value(on, "--moe-cache-mib") == "512"


def test_argv_has_no_fork_only_flags(cfg):
    # Flags de thecodacus/llama.cpp (rama perf) que llama.cpp upstream rechaza.
    cfg = dataclasses.replace(cfg, moe=dataclasses.replace(cfg.moe, cache_mib=512))
    argv = _llama_argv(cfg)
    for flag in ("--moe-cache-profile", "--moe-cache-slots", "--no-sched-async-cpu"):
        assert flag not in argv


def test_llama_saves_slots_where_deck_keeps_them(cfg):
    # Deck restores and saves each Session's slot (``/slots/0?action=``) and
    # trims the directory by bytes: it lives in Deck's volume.
    slots = cfg.instance.deck_data_dir / "llama-slots"
    assert _flag_value(_llama_argv(cfg), "--slot-save-path") == str(slots)
    assert slots in services.LLAMA_SERVICE.spec(cfg).dirs


def test_compose_services_run_from_the_instance_root(cfg):
    for service in services.DOCKER_SERVICES:
        assert service.spec(cfg).stack.directory == cfg.instance.root


# ── voice: whisper-server (stt) and audiocpp_server (tts) ────────────────

STT = LocalModel("whisper-base", "Whisper base", "stt", Path("/m/ggml-base.bin"), 0)
TTS = LocalModel("pocket", "Pocket-TTS", "tts", Path("/m/pocket.gguf"), 0, voice=Path("/v/fija.wav"))


def test_whisper_serves_the_active_stt_model_on_loopback(cfg):
    spec = services.WHISPER_SERVICE.spec(with_local_model(cfg, STT))

    assert _flag_value(list(spec.argv), "--model") == "/m/ggml-base.bin"
    assert _flag_value(list(spec.argv), "--host") == "127.0.0.1"
    assert _flag_value(list(spec.argv), "--port") == str(cfg.whisper.port) == str(spec.port)
    assert spec.argv[0] == str(cfg.whisper.bin)


def _audiocpp_server(spec) -> dict:
    (path,) = spec.files
    assert list(spec.argv) == [str(spec.argv[0]), "--config", str(path)]
    return json.loads(spec.files[path])


def test_audiocpp_serves_the_active_tts_model_with_its_fixed_voice_on_loopback(cfg):
    spec = services.AUDIOCPP_SERVICE.spec(with_local_model(cfg, TTS))

    server = _audiocpp_server(spec)
    assert (server["host"], server["port"]) == ("127.0.0.1", cfg.audiocpp.port)
    (model,) = server["models"]
    assert (model["id"], model["path"], model["task"]) == ("pocket", "/m/pocket.gguf", "tts")
    assert model["default_voice_preset"] == {"voice_ref": "/v/fija.wav"}


def test_a_tts_model_without_a_voice_has_no_default_preset(cfg):
    spec = services.AUDIOCPP_SERVICE.spec(with_local_model(cfg, dataclasses.replace(TTS, voice=None)))

    (model,) = _audiocpp_server(spec)["models"]
    assert "default_voice_preset" not in model


@pytest.mark.parametrize("service,model", [("WHISPER_SERVICE", STT), ("AUDIOCPP_SERVICE", TTS)])
def test_a_voice_service_runs_only_with_its_active_key_on_linux(cfg, service, model):
    definition = getattr(services, service)

    assert not definition.enabled_of(cfg)
    assert definition.enabled_of(with_local_model(cfg, model))
    assert not definition.enabled_of(dataclasses.replace(with_local_model(cfg, model), platform="windows"))
    assert definition in services.LOCAL_SERVICES
    assert services.MODEL_SERVICES[model.capability] is definition
