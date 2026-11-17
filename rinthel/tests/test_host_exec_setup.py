from dotenv import dotenv_values

from rinthel_tui.install.host_exec import prepare_host_exec
from rinthel_tui.instance import Instance


def test_the_token_is_generated_in_the_root_env(tmp_path, monkeypatch):
    monkeypatch.delenv("RINTHEL_HOSTEXECD_TOKEN", raising=False)

    assert prepare_host_exec(Instance(tmp_path)) is True

    assert len(dotenv_values(tmp_path / ".env")["RINTHEL_HOSTEXECD_TOKEN"]) == 64


def test_boot_adopts_an_exported_token_without_rotating_it(tmp_path, monkeypatch):
    monkeypatch.setenv("RINTHEL_HOSTEXECD_TOKEN", "exported-token")
    prepare_host_exec(Instance(tmp_path))
    assert dotenv_values(tmp_path / ".env")["RINTHEL_HOSTEXECD_TOKEN"] == "exported-token"


def test_an_existing_quoted_token_is_kept(tmp_path, monkeypatch):
    monkeypatch.delenv("RINTHEL_HOSTEXECD_TOKEN", raising=False)
    (tmp_path / ".env").write_text('RINTHEL_HOSTEXECD_TOKEN="existing # token"\n')

    assert prepare_host_exec(Instance(tmp_path)) is False

    assert dotenv_values(tmp_path / ".env")["RINTHEL_HOSTEXECD_TOKEN"] == "existing # token"


def test_the_env_holding_the_token_is_private(tmp_path, monkeypatch):
    monkeypatch.delenv("RINTHEL_HOSTEXECD_TOKEN", raising=False)

    prepare_host_exec(Instance(tmp_path))

    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
