"""``update_env_file`` — helper genérico para parchear un .env preservando
comentarios y valores no tocados (Fase 5 del plan de servicios
configurables). Migrado de los tests de ``install._write_env_from_example``,
que generalizó."""

from rinthel_tui.env_file import update_env_file


def test_update_env_file_overrides_keys_and_keeps_rest(tmp_path):
    target = tmp_path / ".env"
    target.write_text("# comentario\nPORTAL_PASSWORD=changeme\nWORKSPACES_DIR=/tmp\nUNTOUCHED=stays\n")

    update_env_file(
        target,
        overrides={"PORTAL_PASSWORD": "s3cr3t", "PI_AGENT_DIR": "/home/x/.pi/agent"},
    )

    lines = target.read_text().splitlines()
    assert "# comentario" in lines
    assert "PORTAL_PASSWORD=s3cr3t" in lines
    assert "WORKSPACES_DIR=/tmp" in lines
    assert "UNTOUCHED=stays" in lines
    assert "PI_AGENT_DIR=/home/x/.pi/agent" in lines


def test_update_env_file_does_not_touch_comment_lines_with_equals(tmp_path):
    target = tmp_path / ".env"
    target.write_text("# PORTAL_PASSWORD=example-in-a-comment\n")

    update_env_file(target, overrides={"PORTAL_PASSWORD": "real-value"})

    lines = target.read_text().splitlines()
    assert "# PORTAL_PASSWORD=example-in-a-comment" in lines
    assert "PORTAL_PASSWORD=real-value" in lines


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
