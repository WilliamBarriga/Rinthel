"""Contratos estáticos mínimos de los entrypoints de Windows."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_writes_validated_profile():
    script = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")
    expected = {
        "RINTHEL_CONTEXT_WINDOW=65536",
        "RINTHEL_N_CPU_MOE=34",
        "RINTHEL_UBATCH_SIZE=2048",
        "RINTHEL_BATCH_SIZE=2048",
        "RINTHEL_SPEC_TYPE=none",
        "RINTHEL_SCHED_ASYNC_CPU=false",
        "RINTHEL_CACHE_TYPE_K=q8_0",
        "RINTHEL_CACHE_TYPE_V=q8_0",
        "RINTHEL_MOE_CACHE_SLOTS=0",
    }
    assert expected <= set(script.split("'"))


def test_windows_boot_hides_the_persistent_daemon_window():
    script = (ROOT / "rinthel-boot.ps1").read_text(encoding="utf-8-sig")
    assert "-WindowStyle Hidden" in script
    assert "-RedirectStandardError" in script
    assert "-RedirectStandardOutput" in script
