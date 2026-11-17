"""``_llama_argv`` — el armado del comando de ``llama-server`` con el Local
model activo: MTP y ``--mmproj`` los decide su entrada del catálogo. El argv
completo del Validated profile está fijado en
``tests/models/test_validated_profile.py``.

Puro: sin subprocess/red, solo un ``RinthelConfig`` (fixture ``cfg`` de
``conftest.py``) y el argv que se le pasaría a ``Popen``."""

import dataclasses
from pathlib import Path

from rinthel_tui.lifecycle import services
from rinthel_tui.lifecycle.services import _llama_argv


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
