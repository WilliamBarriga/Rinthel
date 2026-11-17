"""``_llama_argv`` — el armado del comando de ``llama-server``, con foco en
el interruptor único de MTP (``RINTHEL_MTP_ENABLED``) y su interacción con
``--mmproj``.

Puro: sin subprocess/red, solo un ``RinthelConfig`` (fixture ``cfg`` de
``conftest.py``) y el argv que se le pasaría a ``Popen``."""

import dataclasses

from rinthel_tui.config import default_config
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle import services
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


# ── el argv completo del Validated profile ─────────────────────────────
# Cambiar un flag, un valor o el orden pide un benchmark nuevo: estos dos
# fijan el argv que arranca hoy cada Platform con un ``.env`` vacío.

_PROFILE_ENV = (
    "RINTHEL_CONTEXT_WINDOW", "RINTHEL_N_CPU_MOE", "RINTHEL_UBATCH_SIZE", "RINTHEL_BATCH_SIZE",
    "RINTHEL_SPEC_TYPE", "RINTHEL_CACHE_TYPE_K", "RINTHEL_CACHE_TYPE_V", "RINTHEL_MTP_ENABLED",
    "RINTHEL_LLAMA_MODEL_PATH", "RINTHEL_LLAMA_PORT", "RINTHEL_MOE_CACHE_MIB", "RINTHEL_LLAMA_MMPROJ_PATH",
)


def _argv_tail(platform, tmp_path, monkeypatch):
    for name in _PROFILE_ENV:
        monkeypatch.delenv(name, raising=False)
    argv = _llama_argv(default_config(Instance(tmp_path), platform=platform))
    assert argv[1] == "-m"
    return argv[3:]


def test_the_linux_argv_is_the_validated_one(tmp_path, monkeypatch):
    assert _argv_tail("posix", tmp_path, monkeypatch) == [
        "-ngl", "all", "-c", "112000", "-fa", "on", "-fit", "off",
        "--host", "0.0.0.0", "--port", "8080",
        "--n-cpu-moe", "60", "--threads-batch", "7", "--threads", "8",
        "--ubatch-size", "512", "--batch-size", "512", "--parallel", "1",
        "--temp", "0.7", "--top-p", "0.8", "--top-k", "20", "--min-p", "0.1", "--repeat-penalty", "1.05",
        "--cache-reuse", "256", "--cache-ram", "-1", "--load-mode", "mlock",
        "--spec-type", "none", "--spec-draft-n-max", "2",
        "--cache-type-k", "f16", "--cache-type-v", "f16",
    ]


def test_the_windows_argv_is_the_validated_one(tmp_path, monkeypatch):
    assert _argv_tail("nt", tmp_path, monkeypatch) == [
        "-ngl", "all", "-c", "65536", "-fa", "on", "-fit", "off",
        "--host", "0.0.0.0", "--port", "8080",
        "--n-cpu-moe", "34", "--threads-batch", "7", "--threads", "8",
        "--ubatch-size", "2048", "--batch-size", "2048", "--parallel", "1",
        "--temp", "0.7", "--top-p", "0.8", "--top-k", "20", "--min-p", "0.1", "--repeat-penalty", "1.05",
        "--cache-reuse", "256", "--cache-ram", "-1", "--load-mode", "mlock",
        "--spec-type", "none", "--spec-draft-n-max", "2",
        "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
    ]


def test_compose_services_run_from_the_instance_root(cfg):
    for service in services.DOCKER_SERVICES:
        assert service.spec(cfg).stack.directory == cfg.instance.root
