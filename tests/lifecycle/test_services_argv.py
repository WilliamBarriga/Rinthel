"""``_llama_argv`` — el armado del comando de ``llama-server``, con foco en
el interruptor único de MTP (``RINTHEL_MTP_ENABLED``) y su interacción con
``--mmproj``.

Puro: sin subprocess/red, solo un ``RinthelConfig`` (fixture ``cfg`` de
``conftest.py``) y el argv que se le pasaría a ``Popen``."""

import dataclasses

from rinthel_tui.lifecycle.services import _llama_argv


def _with_llama(cfg, **changes):
    return dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, **changes))


def _flag_value(argv, flag):
    """Valor de ``--flag`` en el argv, o ``None`` si el flag no está."""
    return argv[argv.index(flag) + 1] if flag in argv else None


def test_mtp_off_forces_spec_type_none_regardless_of_spec_type(cfg):
    # El interruptor manda: con MTP apagado, --spec-type queda en "none"
    # aunque .env todavía traiga RINTHEL_SPEC_TYPE=draft-mtp.
    argv = _llama_argv(_with_llama(cfg, mtp_enabled=False, spec_type="draft-mtp"))
    assert _flag_value(argv, "--spec-type") == "none"


def test_mtp_on_uses_configured_spec_type(cfg):
    argv = _llama_argv(_with_llama(cfg, mtp_enabled=True, spec_type="draft-mtp"))
    assert _flag_value(argv, "--spec-type") == "draft-mtp"
    assert _flag_value(argv, "--spec-draft-n-max") == str(cfg.llama.spec_draft_n_max)


def test_mtp_on_omits_mmproj_that_llama_cpp_does_not_support(cfg):
    # llama.cpp no soporta --mmproj junto a spec decoding (test-tarkAIrk/
    # handoff/03) — el flag se saltea, la config guardada no se toca.
    vision = dict(mmproj="~/llama.cpp/models/mmproj-F16.gguf", mmproj_enabled=True)

    assert _flag_value(_llama_argv(_with_llama(cfg, mtp_enabled=False, **vision)), "--mmproj")
    assert _flag_value(_llama_argv(_with_llama(cfg, mtp_enabled=True, **vision)), "--mmproj") is None


def test_mmproj_stays_out_of_the_argv_while_its_toggle_is_off(cfg):
    argv = _llama_argv(_with_llama(cfg, mtp_enabled=False, mmproj="/x/model-mmproj.gguf", mmproj_enabled=False))
    assert "--mmproj" not in argv
