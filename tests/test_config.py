"""Ejemplo de la categoría 'config' — parseo de env vars y defaults.

Estilo de mocking: acá no hay subprocess/red, solo os.environ, así que
usamos monkeypatch.setenv/delenv de pytest directamente, sin mocks de objetos.
"""

import dataclasses

import pytest

from rinthel_tui.config import ConfigError, _bool_env, _int_env, default_config


def test_int_env_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("RINTHEL_TEST_INT", raising=False)
    assert _int_env("RINTHEL_TEST_INT", 42) == 42


def test_int_env_reads_override(monkeypatch):
    monkeypatch.setenv("RINTHEL_TEST_INT", "7")
    assert _int_env("RINTHEL_TEST_INT", 42) == 7


def test_bool_env_accepts_common_truthy_spellings(monkeypatch):
    for value in ("1", "on", "true", "yes", "TRUE"):
        monkeypatch.setenv("RINTHEL_TEST_BOOL", value)
        assert _bool_env("RINTHEL_TEST_BOOL", False) is True


def test_bool_env_default_when_unset(monkeypatch):
    monkeypatch.delenv("RINTHEL_TEST_BOOL", raising=False)
    assert _bool_env("RINTHEL_TEST_BOOL", True) is True
    assert _bool_env("RINTHEL_TEST_BOOL", False) is False


def test_default_config_respects_port_override(monkeypatch):
    monkeypatch.setenv("RINTHEL_LLAMA_PORT", "9999")
    cfg = default_config()
    assert cfg.llama.port == 9999


# ── RinthelConfig.validate() ──────────────────────────────────────────────


def test_validate_raises_on_duplicate_ports():
    base = default_config()
    cfg = dataclasses.replace(base, whisper=dataclasses.replace(base.whisper, port=base.llama.port))
    with pytest.raises(ConfigError, match="choca con"):
        cfg.validate()


def test_validate_raises_on_port_out_of_range():
    base = default_config()
    cfg = dataclasses.replace(base, tts=dataclasses.replace(base.tts, port=70000))
    with pytest.raises(ConfigError, match="fuera de rango"):
        cfg.validate()


def test_validate_raises_on_non_positive_numeric_field():
    base = default_config()
    cfg = dataclasses.replace(base, llama=dataclasses.replace(base.llama, threads=0))
    with pytest.raises(ConfigError, match="llama.threads"):
        cfg.validate()


def test_validate_warns_on_missing_paths_but_does_not_raise():
    base = default_config()
    cfg = dataclasses.replace(
        base, llama=dataclasses.replace(base.llama, bin=base.llama.bin.parent / "no-existe-seguro")
    )
    warnings = cfg.validate()
    assert any("no existe todavía" in w for w in warnings)


# ── enabled ────────────────────────────────────────────────────────────────


def test_default_config_enables_all_services_by_default():
    cfg = default_config()
    assert cfg.llama.enabled is True
    assert cfg.whisper.enabled is True
    assert cfg.tts.enabled is True
    assert cfg.understory.enabled is True
    assert cfg.pithagoras.enabled is True


@pytest.mark.parametrize(
    "env_var, attr",
    [
        ("RINTHEL_LLAMA_ENABLED", "llama"),
        ("RINTHEL_WHISPER_ENABLED", "whisper"),
        ("RINTHEL_TTS_ENABLED", "tts"),
        ("RINTHEL_UNDERSTORY_ENABLED", "understory"),
        ("RINTHEL_PITHAGORAS_ENABLED", "pithagoras"),
    ],
)
def test_enabled_can_be_disabled_per_service(monkeypatch, env_var, attr):
    monkeypatch.setenv(env_var, "false")
    cfg = default_config()
    assert getattr(cfg, attr).enabled is False


def test_validate_no_warnings_when_all_paths_exist(tmp_path):
    base = default_config()
    existing = tmp_path / "bin"
    existing.write_text("")
    cfg = dataclasses.replace(
        base,
        llama=dataclasses.replace(base.llama, bin=existing, model=existing),
        whisper=dataclasses.replace(base.whisper, dir=tmp_path),
        tts=dataclasses.replace(base.tts, dir=tmp_path),
    )
    assert cfg.validate() == []
