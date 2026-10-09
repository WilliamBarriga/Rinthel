from dotenv import dotenv_values

from rinthel_tui.install.host_exec import prepare_host_exec


def test_boot_does_not_create_a_token_only_portal_env(tmp_path):
    portal = tmp_path / "pithagoras"
    prepare_host_exec(tmp_path, portal)
    assert dotenv_values(tmp_path / ".env")["RINTHEL_HOSTEXECD_TOKEN"]
    assert not (portal / ".env").exists()


def test_boot_adopts_an_exported_token_without_rotating_it(tmp_path, monkeypatch):
    monkeypatch.setenv("RINTHEL_HOSTEXECD_TOKEN", "exported-token")
    prepare_host_exec(tmp_path, tmp_path / "pithagoras")
    assert dotenv_values(tmp_path / ".env")["RINTHEL_HOSTEXECD_TOKEN"] == "exported-token"


def test_copying_a_quoted_token_preserves_its_value(tmp_path, monkeypatch):
    monkeypatch.delenv("RINTHEL_HOSTEXECD_TOKEN", raising=False)
    portal = tmp_path / "pithagoras"
    portal.mkdir()
    (portal / ".env").write_text('RINTHEL_HOSTEXECD_TOKEN="existing # token"\n')
    prepare_host_exec(tmp_path, portal)
    assert dotenv_values(tmp_path / ".env")["RINTHEL_HOSTEXECD_TOKEN"] == "existing # token"
