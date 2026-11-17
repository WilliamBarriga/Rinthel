"""``update_env_file`` — helper genérico para parchear un .env preservando
comentarios y valores no tocados."""

import os
import stat

import pytest

from rinthel_tui.env_file import update_env_file


def test_update_env_file_overrides_keys_and_keeps_rest(tmp_path):
    target = tmp_path / ".env"
    target.write_text("# comentario\nRINTHEL_PANEL_SECRET=changeme\nRINTHEL_MODELS_DIR=/tmp\nUNTOUCHED=stays\n")

    update_env_file(
        target,
        overrides={"RINTHEL_PANEL_SECRET": "s3cr3t", "UNDERSTORY_TOKEN": "tok"},
    )

    lines = target.read_text().splitlines()
    assert "# comentario" in lines
    assert "RINTHEL_PANEL_SECRET=s3cr3t" in lines
    assert "RINTHEL_MODELS_DIR=/tmp" in lines
    assert "UNTOUCHED=stays" in lines
    assert "UNDERSTORY_TOKEN=tok" in lines


def test_update_env_file_does_not_touch_comment_lines_with_equals(tmp_path):
    target = tmp_path / ".env"
    target.write_text("# RINTHEL_PANEL_SECRET=example-in-a-comment\n")

    update_env_file(target, overrides={"RINTHEL_PANEL_SECRET": "real-value"})

    lines = target.read_text().splitlines()
    assert "# RINTHEL_PANEL_SECRET=example-in-a-comment" in lines
    assert "RINTHEL_PANEL_SECRET=real-value" in lines


def test_update_env_file_seeds_from_example_when_path_does_not_exist(tmp_path):
    seed_from = tmp_path / ".env.example"
    seed_from.write_text("# RINTHEL_LLAMA_PORT=8080\n# RINTHEL_TTS_ENABLED=true\n")
    target = tmp_path / ".env"

    update_env_file(target, overrides={"RINTHEL_TTS_ENABLED": "false"}, seed_from=seed_from)

    assert target.exists()
    lines = target.read_text().splitlines()
    assert "# RINTHEL_LLAMA_PORT=8080" in lines
    # La línea comentada del template no cuenta como "clave existente" (no
    # se toca), así que el override real se agrega al final.
    assert "# RINTHEL_TTS_ENABLED=true" in lines
    assert "RINTHEL_TTS_ENABLED=false" in lines


def test_update_env_file_starts_empty_without_seed_when_path_missing(tmp_path):
    target = tmp_path / "nested" / ".env"

    update_env_file(target, overrides={"RINTHEL_TTS_ENABLED": "false"})

    assert target.read_text() == "RINTHEL_TTS_ENABLED=false\n"


# ── escritura atómica ─────────────────


def test_update_env_file_preserves_the_original_file_mode(tmp_path):
    target = tmp_path / ".env"
    target.write_text("UNDERSTORY_TOKEN=abc123\n")
    target.chmod(0o600)

    update_env_file(target, overrides={"UNDERSTORY_TOKEN": "def456"})

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert "UNDERSTORY_TOKEN=def456" in target.read_text()


@pytest.mark.skipif(os.geteuid() == 0, reason="root escribe en un directorio de solo lectura")
def test_update_env_file_leaves_original_untouched_and_cleans_up_tmp_on_write_failure(tmp_path):
    target = tmp_path / ".env"
    original_content = "RINTHEL_PANEL_SECRET=changeme\n"
    target.write_text(original_content)

    tmp_path.chmod(0o500)  # el directorio no deja crear el temporal: un fallo real del filesystem
    try:
        with pytest.raises(OSError):
            update_env_file(target, overrides={"RINTHEL_PANEL_SECRET": "s3cr3t"})
    finally:
        tmp_path.chmod(0o700)

    assert target.read_text() == original_content
    leftover = [p for p in tmp_path.iterdir() if p.name.startswith(".env.") and p.name.endswith(".tmp")]
    assert leftover == []
