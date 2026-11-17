"""The Windows compose, as INSTALL selects it: the root compose plus
``compose/windows.override.yaml`` through the ``COMPOSE_FILE`` that INSTALL
writes in the root ``.env``. Rendered by ``docker compose config`` on this
host, without starting Docker or reading the real ``.env``."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from rinthel_tui.config import default_config
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle.install import WINDOWS_COMPOSE
from rinthel_tui.lifecycle.services import understory_url

ROOT = Path(__file__).resolve().parents[2]


def _compose(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is unavailable")
    env_file = tmp_path / ".env"
    env_file.write_text("UNDERSTORY_TOKEN=a-token\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("COMPOSE_")}
    env.update(WINDOWS_COMPOSE)
    return subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "config", *args],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )


@pytest.fixture(scope="module")
def config(tmp_path_factory) -> dict:
    result = _compose(tmp_path_factory.mktemp("windows-compose"), "--format", "json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_override_is_valid_compose(tmp_path):
    result = _compose(tmp_path, "--quiet")

    assert result.returncode == 0, result.stderr


def test_the_instance_still_runs_understory_and_deck_only(config):
    assert set(config["services"]) == {"understory", "deck"}


def test_deck_runs_in_a_bridge_published_on_the_loopback_only(config):
    deck = config["services"]["deck"]

    assert "network_mode" not in deck
    assert [(p["host_ip"], p["published"], p["target"]) for p in deck["ports"]] == [("127.0.0.1", "4100", 4100)]


def test_deck_reaches_the_host_by_host_docker_internal(config):
    deck = config["services"]["deck"]

    assert deck["extra_hosts"] == ["host.docker.internal=host-gateway"]
    assert deck["environment"]["RINTHEL_DAEMON_URL"] == "http://host.docker.internal:8765"


def test_deck_has_no_linux_host_user_or_docker_group(config):
    deck = config["services"]["deck"]

    assert "user" not in deck
    assert not deck.get("group_add")


def test_deck_db_runs_in_delete_journal_mode(config):
    assert config["services"]["deck"]["environment"]["DECK_DB_JOURNAL_MODE"] == "delete"


def test_deck_shares_a_network_with_understory_by_the_url_the_daemon_hands_it(config, tmp_path):
    windows = default_config(Instance(tmp_path), platform="windows")

    assert understory_url(windows) == "http://understory:3800"
    assert "understory-net" in config["services"]["deck"]["networks"]
    assert "understory-net" in config["services"]["understory"]["networks"]


def test_deck_browser_joins_deck_on_a_network_of_its_own_by_container_name(config):
    deck = config["services"]["deck"]
    network = config["networks"]["deck-browser-net"]["name"]

    assert "deck-browser-net" in deck["networks"]
    assert deck["environment"]["BROWSER_NETWORK"] == network
    assert deck["environment"]["BROWSER_CDP_URL"] == "http://deck-browser:9222"
    assert deck["environment"]["BROWSER_HOST"] == "deck-browser"
    # Understory is not on the browser's network.
    assert "deck-browser-net" not in config["services"]["understory"]["networks"]


def test_deck_keeps_the_docker_socket_for_the_browser_in_docker_mode(config):
    targets = [volume["target"] for volume in config["services"]["deck"]["volumes"]]

    assert "/var/run/docker.sock" in targets


def test_understory_reaches_the_host_by_host_gateway_not_the_linux_bridge_ip(config):
    understory = config["services"]["understory"]

    assert understory["extra_hosts"] == ["host.docker.internal=host-gateway"]
    assert [(p["host_ip"], p["target"]) for p in understory["ports"]] == [("127.0.0.1", 3800)]
