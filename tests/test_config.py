"""Ejemplo de la categoría 'config' — parseo de env vars y defaults.

Estilo de mocking: acá no hay subprocess/red, solo os.environ, así que
usamos monkeypatch.setenv/delenv de pytest directamente, sin mocks de objetos.
"""

import dataclasses

import pytest

from rinthel_tui.config import (
    KIND_NAMES,
    ConfigError,
    _bool_env,
    _int_env,
    default_config,
    diff_overrides,
    stringify,
    with_overrides,
)


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
    cfg = dataclasses.replace(base, understory=dataclasses.replace(base.understory, port=base.llama.port))
    with pytest.raises(ConfigError, match="choca con"):
        cfg.validate()


def test_validate_raises_on_port_out_of_range():
    base = default_config()
    cfg = dataclasses.replace(base, pithagoras=dataclasses.replace(base.pithagoras, port=70000))
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


# ── MTP: interruptor único + warnings de los combos inseguros ─────────────


def test_validate_warns_when_mtp_is_on_with_a_batch_that_does_not_fit(cfg):
    # test-tarkAIrk/logs/27: MTP + batch 2048 = 48 MiB libres, CUDA OOM.
    risky = dataclasses.replace(
        cfg, llama=dataclasses.replace(cfg.llama, mtp_enabled=True, batch_size=2048, ubatch_size=2048)
    )
    warnings = risky.validate()
    assert any("MTP + batch/ubatch 2048/2048" in w and "logs/27" in w for w in warnings)


def test_validate_does_not_warn_about_batch_size_with_mtp_off(cfg):
    off = dataclasses.replace(
        cfg, llama=dataclasses.replace(cfg.llama, mtp_enabled=False, batch_size=2048, ubatch_size=2048)
    )
    assert not any("MTP + batch/ubatch" in w for w in off.validate())


def test_validate_warns_on_mtp_with_parallel_gt_1_and_with_vision(cfg):
    # Las dos limitaciones propias de llama.cpp (handoff/03), no de VRAM.
    combo = dataclasses.replace(
        cfg,
        llama=dataclasses.replace(
            cfg.llama,
            mtp_enabled=True,
            batch_size=512,
            ubatch_size=512,
            parallel=2,
            mmproj="~/llama.cpp/models/mmproj-F16.gguf",
            mmproj_enabled=True,
        ),
    )
    warnings = combo.validate()
    assert any("--parallel > 1" in w for w in warnings)
    assert any("--mmproj" in w for w in warnings)


def test_validate_warns_when_the_mtp_switch_contradicts_spec_type(cfg):
    # Interruptor prendido pero modo "none": el argv arrancaría con
    # --spec-type none, MTP apagado pese al checkbox.
    contradictory = dataclasses.replace(
        cfg, llama=dataclasses.replace(cfg.llama, mtp_enabled=True, spec_type="none", batch_size=512, ubatch_size=512)
    )
    assert any("queda apagado" in w for w in contradictory.validate())


# ── enabled ────────────────────────────────────────────────────────────────


def test_default_config_enables_all_services_by_default():
    cfg = default_config()
    assert cfg.llama.enabled is True
    assert cfg.understory.enabled is True
    assert cfg.pithagoras.enabled is True


@pytest.mark.parametrize(
    "env_var, attr",
    [
        ("RINTHEL_LLAMA_ENABLED", "llama"),
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
        # mtp_enabled=False para aislar este chequeo (paths) de los warnings
        # de MTP de `_mtp_warnings` — el .env real de esta máquina tiene MTP
        # prendido con batch 2048, combination que SÍ debe warniar (ver
        # test de más abajo).
        llama=dataclasses.replace(base.llama, bin=existing, model=existing, mtp_enabled=False),
    )
    assert cfg.validate() == []


# ── stringify/diff_overrides/with_overrides ─────────────────────────────
# Esta lógica es compartida entre el daemon (GET/POST /config) y cualquier
# UI, no específica de una sola.


def test_stringify_bool_uses_lowercase_true_false():
    assert stringify(True) == "true"
    assert stringify(False) == "false"


def test_stringify_other_types_use_str():
    assert stringify(8080) == "8080"
    assert stringify("mlock") == "mlock"


def test_diff_overrides_excludes_values_that_match_current_config(cfg):
    edits = {
        "RINTHEL_LLAMA_PORT": str(cfg.llama.port),  # sin cambios reales
        "RINTHEL_PITHAGORAS_ENABLED": "false",  # sí cambió (default es true)
    }
    overrides = diff_overrides(cfg, edits)
    assert overrides == {"RINTHEL_PITHAGORAS_ENABLED": "false"}


def test_diff_overrides_empty_when_nothing_changed(cfg):
    edits = {"RINTHEL_UNDERSTORY_PORT": str(cfg.understory.port)}
    assert diff_overrides(cfg, edits) == {}


def test_diff_overrides_ignores_env_vars_not_in_any_field(cfg):
    edits = {"RINTHEL_NOT_A_REAL_FIELD": "whatever"}
    assert diff_overrides(cfg, edits) == {}


def test_diff_overrides_reflects_a_cfg_already_disabled(cfg):
    disabled = dataclasses.replace(cfg, pithagoras=dataclasses.replace(cfg.pithagoras, enabled=False))
    # Re-habilitar en la UI, contra un cfg que ya está deshabilitado, debe
    # contar como cambio.
    edits = {"RINTHEL_PITHAGORAS_ENABLED": "true"}
    assert diff_overrides(disabled, edits) == {"RINTHEL_PITHAGORAS_ENABLED": "true"}
    # Pero "false" contra ese mismo cfg ya deshabilitado no es un cambio.
    assert diff_overrides(disabled, {"RINTHEL_PITHAGORAS_ENABLED": "false"}) == {}


def test_with_overrides_parses_each_kind_from_a_raw_string(cfg):
    updated = with_overrides(
        cfg,
        {
            "RINTHEL_LLAMA_PORT": "9090",  # int
            "RINTHEL_TEMPERATURE": "0.55",  # float
            "RINTHEL_LLAMA_ENABLED": "false",  # bool
            "RINTHEL_NGL": "42",  # str (se queda como string)
        },
    )
    assert updated.llama.port == 9090
    assert updated.llama.temperature == 0.55
    assert updated.llama.enabled is False
    assert updated.llama.ngl == "42"


def test_with_overrides_does_not_mutate_the_original_cfg(cfg):
    with_overrides(cfg, {"RINTHEL_LLAMA_PORT": "9090"})
    assert cfg.llama.port != 9090


def test_with_overrides_leaves_untouched_sub_configs_alone(cfg):
    updated = with_overrides(cfg, {"RINTHEL_LLAMA_PORT": "9090"})
    assert updated.understory == cfg.understory
    assert updated.pithagoras == cfg.pithagoras


def test_with_overrides_result_can_fail_validate(cfg):
    updated = with_overrides(cfg, {"RINTHEL_LLAMA_PORT": str(cfg.understory.port)})
    with pytest.raises(ConfigError, match="choca con"):
        updated.validate()


def test_kind_names_cover_every_field_kind_in_use():
    from pathlib import Path

    assert KIND_NAMES == {bool: "bool", int: "int", float: "float", str: "str", Path: "path"}
