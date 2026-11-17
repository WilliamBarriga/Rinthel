"""Instance — el layout de una instalación (ver GLOSSARY.md) y sus secretos.
Se construye desde una raíz explícita (``tmp_path`` acá), sin globals."""

import pytest

from rinthel_tui.config import default_config
from rinthel_tui.instance import Instance, RotatableSecret, main


def test_discover_finds_closest_ancestor_with_git(tmp_path):
    (tmp_path / ".git").mkdir()
    start = tmp_path / "rinthel" / "rinthel_tui"
    start.mkdir(parents=True)

    assert Instance.discover(start).root == tmp_path


def test_discover_without_git_falls_back_to_parent_of_rinthel(tmp_path):
    package_dir = tmp_path / "rinthel" / "rinthel_tui"
    package_dir.mkdir(parents=True)

    assert Instance.discover(package_dir).root == tmp_path


def test_instance_root_env_var_overrides_discovery(tmp_path, monkeypatch):
    monkeypatch.setenv("RINTHEL_INSTANCE_ROOT", str(tmp_path))

    assert Instance.discover().root == tmp_path


def test_without_instance_root_env_var_discovery_finds_the_repo(monkeypatch):
    monkeypatch.delenv("RINTHEL_INSTANCE_ROOT", raising=False)

    assert (Instance.discover().root / "rinthel" / "rinthel_tui").is_dir()


def test_layout_paths_hang_from_root(tmp_path):
    instance = Instance(tmp_path)

    assert instance.env_path == tmp_path / ".env"
    assert instance.env_example_path == tmp_path / ".env.example"
    assert instance.app_dir == tmp_path / "rinthel"
    assert instance.data_dir == tmp_path / "data"
    assert instance.logs_dir == tmp_path / "logs"
    assert instance.understory_dir == tmp_path / "understory"
    assert instance.understory_data_dir == tmp_path / "data" / "understory"
    assert instance.deck_dir == tmp_path / "deck"
    assert instance.deck_data_dir == tmp_path / "data" / "deck"


def test_config_reads_the_instance_env(tmp_path, monkeypatch):
    monkeypatch.delenv("RINTHEL_LLAMA_PORT", raising=False)
    (tmp_path / ".env").write_text("RINTHEL_LLAMA_PORT=18099\n")
    instance = Instance(tmp_path)

    cfg = default_config(instance, platform="linux")

    assert cfg.llama.port == 18099
    assert cfg.instance is instance


def test_shell_env_wins_over_the_instance_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("RINTHEL_LLAMA_PORT=18099\n")
    monkeypatch.setenv("RINTHEL_LLAMA_PORT", "18100")

    assert default_config(Instance(tmp_path), platform="linux").llama.port == 18100


def test_config_layout_defaults_come_from_the_instance(tmp_path, monkeypatch):
    for var in ("RINTHEL_UNDERSTORY_DIR", "RINTHEL_DECK_DIR", "RINTHEL_LLAMA_LOG_PATH"):
        monkeypatch.delenv(var, raising=False)

    cfg = default_config(Instance(tmp_path), platform="linux")

    assert cfg.understory.dir == tmp_path / "understory"
    assert cfg.deck.dir == tmp_path / "deck"
    assert cfg.llama.log == tmp_path / "logs" / "llama-server.log"


def test_docker_services_run_from_the_instance_root(cfg):
    from rinthel_tui.lifecycle.services import DOCKER_SERVICES

    assert {service.dir_of(cfg) for service in DOCKER_SERVICES} == {cfg.instance.root}


def test_get_reads_the_env_file_fresh_each_time(tmp_path):
    instance = Instance(tmp_path)
    assert instance.get("RINTHEL_SERVICE_SECRET") is None

    (tmp_path / ".env").write_text("RINTHEL_SERVICE_SECRET=abc\nEMPTY=\n")

    assert instance.get("RINTHEL_SERVICE_SECRET") == "abc"
    assert instance.get("EMPTY") is None


def test_ensure_secret_generates_once_and_then_leaves_it_alone(tmp_path):
    (tmp_path / ".env.example").write_text("# comentario del example\nRINTHEL_SERVICE_SECRET=\n")
    instance = Instance(tmp_path)

    assert instance.ensure_secret("RINTHEL_SERVICE_SECRET") is True
    first = instance.get("RINTHEL_SERVICE_SECRET")
    assert first and len(first) == 64

    assert instance.ensure_secret("RINTHEL_SERVICE_SECRET") is False
    assert instance.get("RINTHEL_SERVICE_SECRET") == first
    assert "# comentario del example" in (tmp_path / ".env").read_text()


def test_rotate_secret_replaces_service_and_panel(tmp_path):
    (tmp_path / ".env").write_text("RINTHEL_SERVICE_SECRET=old\nRINTHEL_PANEL_SECRET=old\n")
    instance = Instance(tmp_path)

    instance.rotate_secret("RINTHEL_SERVICE_SECRET")
    instance.rotate_secret("RINTHEL_PANEL_SECRET")

    assert instance.get("RINTHEL_SERVICE_SECRET") not in (None, "old")
    assert instance.get("RINTHEL_PANEL_SECRET") not in (None, "old")


def test_only_the_service_and_panel_secrets_are_rotatable():
    assert RotatableSecret.SERVICE == "RINTHEL_SERVICE_SECRET"
    assert RotatableSecret.PANEL == "RINTHEL_PANEL_SECRET"
    assert list(RotatableSecret) == [RotatableSecret.SERVICE, RotatableSecret.PANEL]


def test_rotate_secret_refuses_a_non_rotatable_key(tmp_path):
    (tmp_path / ".env").write_text("UNDERSTORY_TOKEN=keep\n")
    instance = Instance(tmp_path)

    with pytest.raises(ValueError):
        instance.rotate_secret("UNDERSTORY_TOKEN")
    assert instance.get("UNDERSTORY_TOKEN") == "keep"


# ── CLI (`python -m rinthel_tui.instance`) — lo que usa rinthel-boot.sh ──


def test_cli_prints_the_root(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "root"]) == 0
    assert capsys.readouterr().out == f"{tmp_path}\n"


def test_cli_get_prints_value_or_nothing(tmp_path, capsys):
    (tmp_path / ".env").write_text("RINTHEL_DAEMON_PORT=9001\n")

    assert main(["--root", str(tmp_path), "get", "RINTHEL_DAEMON_PORT"]) == 0
    assert capsys.readouterr().out == "9001\n"
    assert main(["--root", str(tmp_path), "get", "MISSING"]) == 0
    assert capsys.readouterr().out == ""


def test_ensure_secret_leaves_the_env_readable_only_by_its_owner(tmp_path):
    """El boot corre ``ensure-secret`` en cada arranque: es lo que garantiza
    el 600 del ``.env`` (con secretos) en una instalación nueva o si alguien
    le abrió el modo, se genere el secreto o no."""
    env = tmp_path / ".env"
    env.write_text("RINTHEL_SERVICE_SECRET=ya-estaba\n")
    env.chmod(0o644)

    Instance(tmp_path).ensure_secret("RINTHEL_SERVICE_SECRET")
    assert env.stat().st_mode & 0o777 == 0o600

    env.unlink()
    Instance(tmp_path).ensure_secret("RINTHEL_SERVICE_SECRET")
    assert env.stat().st_mode & 0o777 == 0o600


def test_cli_ensure_secret_writes_the_env(tmp_path):
    assert main(["--root", str(tmp_path), "ensure-secret", "RINTHEL_SERVICE_SECRET"]) == 0
    assert Instance(tmp_path).get("RINTHEL_SERVICE_SECRET")


def test_cli_rotate_rejects_non_rotatable_keys(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "rotate", "UNDERSTORY_TOKEN"]) != 0
    assert "no es rotable" in capsys.readouterr().err


def test_cli_runs_as_a_module_from_the_real_repo():
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "rinthel_tui.instance", "root"], capture_output=True, text=True, check=True
    ).stdout
    assert out.strip() == str(Instance.discover().root)


def test_cli_rotate_warns_that_a_running_daemon_keeps_the_old_secret(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "rotate", "RINTHEL_PANEL_SECRET"]) == 0

    assert "si el daemon está corriendo, usá la TUI o reiniciá" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("shell", "env_file", "expected"),
    [
        ({"K": "shell"}, "K=file\n", "shell"),
        ({"K": "shell"}, "", "shell"),
        ({}, "K=file\n", "file"),
        ({"K": ""}, "K=file\n", "file"),
        ({}, "", None),
    ],
)
def test_variable_is_shell_then_env_file(tmp_path, shell, env_file, expected):
    (tmp_path / ".env").write_text(env_file)

    assert Instance(tmp_path).variable("K", shell) == expected


def test_variable_without_env_file_reads_only_the_shell(tmp_path):
    assert Instance(tmp_path).variable("K", {"K": "x"}) == "x"
    assert Instance(tmp_path).variable("K", {}) is None
