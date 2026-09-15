"""Lógica de guardado de [N] CONFIGURAR — separada de la Screen a propósito
(ver ``rinthel_tui/tui/screens/settings.py``) para poder testearla sin
levantar Textual: ``_diff_overrides`` recibe un ``cfg`` y el dict de
ediciones en memoria, y devuelve solo lo que de verdad cambió."""

import dataclasses

from rinthel_tui.tui.screens.settings import _diff_overrides, _stringify


def test_stringify_bool_uses_lowercase_true_false():
    assert _stringify(True) == "true"
    assert _stringify(False) == "false"


def test_stringify_other_types_use_str():
    assert _stringify(8080) == "8080"
    assert _stringify("mlock") == "mlock"


def test_diff_overrides_excludes_values_that_match_current_config(cfg):
    edits = {
        "RINTHEL_LLAMA_PORT": str(cfg.llama.port),  # sin cambios reales
        "RINTHEL_PITHAGORAS_ENABLED": "false",  # sí cambió (default es true)
    }
    overrides = _diff_overrides(cfg, edits)
    assert overrides == {"RINTHEL_PITHAGORAS_ENABLED": "false"}


def test_diff_overrides_empty_when_nothing_changed(cfg):
    edits = {"RINTHEL_UNDERSTORY_PORT": str(cfg.understory.port)}
    assert _diff_overrides(cfg, edits) == {}


def test_diff_overrides_ignores_env_vars_not_in_any_field(cfg):
    edits = {"RINTHEL_NOT_A_REAL_FIELD": "whatever"}
    assert _diff_overrides(cfg, edits) == {}


def test_diff_overrides_reflects_a_cfg_already_disabled(cfg):
    disabled = dataclasses.replace(cfg, pithagoras=dataclasses.replace(cfg.pithagoras, enabled=False))
    # Re-habilitar en la UI, contra un cfg que ya está deshabilitado, debe
    # contar como cambio.
    edits = {"RINTHEL_PITHAGORAS_ENABLED": "true"}
    assert _diff_overrides(disabled, edits) == {"RINTHEL_PITHAGORAS_ENABLED": "true"}
    # Pero "false" contra ese mismo cfg ya deshabilitado no es un cambio.
    assert _diff_overrides(disabled, {"RINTHEL_PITHAGORAS_ENABLED": "false"}) == {}
