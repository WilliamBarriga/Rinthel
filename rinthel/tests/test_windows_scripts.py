"""Contratos estáticos mínimos de los entrypoints de Windows."""

from pathlib import Path


RINTHEL_DIR = Path(__file__).resolve().parents[1]


def test_windows_installer_leaves_the_validated_profile_to_the_daemon_config():
    # El perfil vive en un solo lugar (config.VALIDATED_PROFILES, fijado en
    # tests/models/test_validated_profile.py); el instalador solo escribe rutas.
    script = (RINTHEL_DIR / "install.ps1").read_text(encoding="utf-8-sig")
    for name in (
        "RINTHEL_CONTEXT_WINDOW", "RINTHEL_N_CPU_MOE", "RINTHEL_UBATCH_SIZE", "RINTHEL_BATCH_SIZE",
        "RINTHEL_SPEC_TYPE", "RINTHEL_CACHE_TYPE_K", "RINTHEL_CACHE_TYPE_V", "RINTHEL_LLAMA_MODEL_PATH",
    ):
        assert f"{name}=" not in script
    assert "RINTHEL_MODELS_DIR=" in script


def _script(name: str) -> str:
    return (RINTHEL_DIR / name).read_text(encoding="utf-8-sig")


def test_windows_scripts_leave_the_compose_choice_to_install():
    # INSTALL writes COMPOSE_FILE (phase_install_platform_compose); the
    # wrappers never patch or pick compose files themselves.
    for name in ("install.ps1", "rinthel-boot.ps1", "install-status.ps1"):
        script = _script(name)
        assert "COMPOSE_FILE=" not in script
        assert "network_mode" not in script


def test_windows_scripts_never_start_what_windows_omits():
    # Voice and host exec are Linux only: no wrapper builds or starts them.
    for name in ("install.ps1", "rinthel-boot.ps1", "install-status.ps1"):
        script = _script(name).lower()
        for omitted in ("hostexecd", "whisper", "audiocpp", "--voice"):
            assert omitted not in script, (name, omitted)


def test_install_status_waits_for_the_windows_compose_override():
    script = _script("install-status.ps1")
    assert "Test-EnvKey 'COMPOSE_FILE'" in script


def test_windows_boot_hides_the_persistent_daemon_window():
    script = (RINTHEL_DIR / "rinthel-boot.ps1").read_text(encoding="utf-8-sig")
    assert "-WindowStyle Hidden" in script
    assert "-RedirectStandardError" in script
    assert "-RedirectStandardOutput" in script
