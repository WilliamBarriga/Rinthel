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


def test_windows_boot_hides_the_persistent_daemon_window():
    script = (RINTHEL_DIR / "rinthel-boot.ps1").read_text(encoding="utf-8-sig")
    assert "-WindowStyle Hidden" in script
    assert "-RedirectStandardError" in script
    assert "-RedirectStandardOutput" in script
