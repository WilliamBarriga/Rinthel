"""El Validated profile de cada Platform y el argv de ``llama-server`` que
arranca con el Local model por defecto. Fijados a mano: cambiar un flag, un
valor o el orden pide un benchmark nuevo (``docs/05-windows-validation.md``)."""

import json

import pytest

from rinthel_tui.config import VALIDATED_PROFILES, default_config
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.services import _llama_argv
from rinthel_tui.models.adapters.toml_active import TomlActiveModels

QWEN = "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"


def test_the_windows_profile_is_the_measured_one():
    windows = VALIDATED_PROFILES["windows"]
    assert windows.llama == {
        "n_cpu_moe": 34, "ubatch_size": 2048, "batch_size": 2048, "spec_type": "none",
        "cache_type_k": "q8_0", "cache_type_v": "q8_0",
    }
    assert windows.model.context_window == 65536


def test_the_linux_profile_keeps_the_field_defaults():
    linux = VALIDATED_PROFILES["linux"]
    assert linux.llama == {}
    assert linux.model.context_window == 112000


@pytest.mark.parametrize("platform", ["linux", "windows"])
def test_both_platforms_default_to_the_same_local_model(platform):
    model = VALIDATED_PROFILES[platform].model
    assert (model.id, model.file, model.reasoning_format) == ("qwen3.6-35b-a3b", QWEN, "qwen-chat-template")
    assert model.url == f"https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/resolve/main/{QWEN}"


def _instance_with_default_model(tmp_path, platform, monkeypatch) -> Instance:
    """La Instance que deja INSTALL: el catálogo con la entrada por defecto
    del Validated profile, activa en ``instance.toml``."""
    for name in ("RINTHEL_LLAMA_PORT", "RINTHEL_MOE_CACHE_MIB", "RINTHEL_N_CPU_MOE", "RINTHEL_UBATCH_SIZE",
                 "RINTHEL_BATCH_SIZE", "RINTHEL_SPEC_TYPE", "RINTHEL_CACHE_TYPE_K", "RINTHEL_CACHE_TYPE_V"):
        monkeypatch.delenv(name, raising=False)
    instance = Instance(tmp_path)
    gguf = tmp_path / "models" / QWEN
    gguf.parent.mkdir()
    gguf.write_bytes(b"GGUF" + b"\0" * 16)
    window = 65536 if platform == "windows" else 112000
    instance.models_catalog_path.write_text(json.dumps({"models": [{
        "id": "qwen3.6-35b-a3b", "name": "Qwen3.6 35B A3B", "capability": "llm", "gguf": str(gguf),
        "context_window": window, "mmproj": None, "mtp": False, "reasoning_format": "qwen-chat-template",
        "overrides": {},
    }]}))
    TomlActiveModels(instance.instance_toml_path).set("llm", "qwen3.6-35b-a3b")
    return instance


def test_the_linux_argv_is_the_validated_one(tmp_path, monkeypatch):
    cfg = default_config(_instance_with_default_model(tmp_path, "linux", monkeypatch), platform="linux")
    assert _llama_argv(cfg) == [
        str(cfg.llama.bin), "-m", str(tmp_path / "models" / QWEN),
        "-ngl", "all", "-c", "112000", "-fa", "on", "-fit", "off",
        "--host", "0.0.0.0", "--port", "8080",
        "--n-cpu-moe", "60", "--threads-batch", "7", "--threads", "8",
        "--ubatch-size", "512", "--batch-size", "512", "--parallel", "1",
        "--temp", "0.7", "--top-p", "0.8", "--top-k", "20", "--min-p", "0.1", "--repeat-penalty", "1.05",
        "--cache-reuse", "256", "--cache-ram", "-1", "--load-mode", "mlock",
        "--spec-type", "none", "--spec-draft-n-max", "2",
        "--cache-type-k", "f16", "--cache-type-v", "f16",
        # Not part of the profile: where Deck keeps the Sessions' slots.
        "--slot-save-path", str(tmp_path / "data" / "deck" / "llama-slots"),
    ]


def test_the_windows_argv_is_the_validated_one(tmp_path, monkeypatch):
    cfg = default_config(_instance_with_default_model(tmp_path, "windows", monkeypatch), platform="windows")
    assert _llama_argv(cfg) == [
        str(cfg.llama.bin), "-m", str(tmp_path / "models" / QWEN),
        "-ngl", "all", "-c", "65536", "-fa", "on", "-fit", "off",
        "--host", "0.0.0.0", "--port", "8080",
        "--n-cpu-moe", "34", "--threads-batch", "7", "--threads", "8",
        "--ubatch-size", "2048", "--batch-size", "2048", "--parallel", "1",
        "--temp", "0.7", "--top-p", "0.8", "--top-k", "20", "--min-p", "0.1", "--repeat-penalty", "1.05",
        "--cache-reuse", "256", "--cache-ram", "-1", "--load-mode", "mlock",
        "--spec-type", "none", "--spec-draft-n-max", "2",
        "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
        "--slot-save-path", str(tmp_path / "data" / "deck" / "llama-slots"),
    ]


def test_an_explicit_env_value_still_wins_over_the_profile(tmp_path, monkeypatch):
    instance = _instance_with_default_model(tmp_path, "windows", monkeypatch)
    monkeypatch.setenv("RINTHEL_N_CPU_MOE", "42")
    assert default_config(instance, platform="windows").llama.n_cpu_moe == 42


# ── el Local model activo al arrancar ────────────────────────────────────


def _spawned(cfg) -> list[str]:
    return [
        phase.label for unit in specs.boot_plan(cfg).batches[0].units for phase in unit.phases
        if phase.fn.__name__ == "phase_spawn"
    ]


def test_with_the_default_model_active_boot_spawns_llama(tmp_path, monkeypatch):
    cfg = default_config(_instance_with_default_model(tmp_path, "linux", monkeypatch), platform="linux")
    assert cfg.local_model is not None and cfg.local_model.id == "qwen3.6-35b-a3b"
    assert _spawned(cfg)


def test_an_unknown_active_id_warns_and_llama_does_not_boot(tmp_path, monkeypatch):
    instance = _instance_with_default_model(tmp_path, "linux", monkeypatch)
    TomlActiveModels(instance.instance_toml_path).set("llm", "borrado")
    cfg = default_config(instance, platform="linux")
    assert cfg.local_model is None
    assert any("borrado" in w for w in cfg.validate())
    assert _spawned(cfg) == []
    (llama,) = [u for u in specs.boot_plan(cfg).batches[0].units if u.service == "llama-server"]
    assert [p.fn.__name__ for p in llama.phases] == ["phase_notice"]


def test_an_active_entry_that_became_invalid_does_not_boot(tmp_path, monkeypatch):
    instance = _instance_with_default_model(tmp_path, "linux", monkeypatch)
    (tmp_path / "models" / QWEN).unlink()
    cfg = default_config(instance, platform="linux")
    assert cfg.local_model is None
    assert any("GGUF no encontrado" in w for w in cfg.validate())


def test_the_old_model_env_vars_are_ignored_with_a_warning(tmp_path, monkeypatch):
    instance = _instance_with_default_model(tmp_path, "linux", monkeypatch)
    monkeypatch.setenv("RINTHEL_LLAMA_MODEL_PATH", "/otro.gguf")
    monkeypatch.setenv("RINTHEL_CONTEXT_WINDOW", "4096")
    cfg = default_config(instance, platform="linux")
    assert cfg.local_model.context_window == 112000
    warnings = cfg.validate()
    assert any("RINTHEL_LLAMA_MODEL_PATH" in w for w in warnings)
    assert any("RINTHEL_CONTEXT_WINDOW" in w for w in warnings)
