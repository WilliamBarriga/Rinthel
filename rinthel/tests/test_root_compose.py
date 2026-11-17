"""Validate the real root Compose seam without starting Docker or exposing env values."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rinthel_tui.config import default_config
from rinthel_tui.instance import Instance

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def config() -> dict:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is unavailable")
    result = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yaml"), "config", "--no-interpolate", "--format", "json"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_the_instance_runs_understory_and_deck_only(config):
    assert set(config["services"]) == {"understory", "deck"}


def test_deck_listens_on_the_port_the_daemon_expects_as_the_host_user(config, tmp_path):
    deck = config["services"]["deck"]

    assert Path(deck["build"]["context"]) == ROOT / "deck"
    assert deck["network_mode"] == "host"
    assert deck["environment"]["PORT"] == "${RINTHEL_DECK_PORT:-4100}"
    assert default_config(Instance(tmp_path), platform="linux").deck.port == 4100
    # INSTALL writes PUID/PGID in the root .env (phase_install_container_user).
    assert deck["user"] == "${PUID:-1000}:${PGID:-1000}"


def test_deck_reaches_hostexecd_by_what_the_daemon_passes_with_no_extension_mounts(config, tmp_path):
    deck = config["services"]["deck"]
    port = default_config(Instance(tmp_path), platform="linux").hostexecd.port

    assert deck["environment"]["RINTHEL_HOSTEXECD_TOKEN"] == "${RINTHEL_HOSTEXECD_TOKEN:-}"
    assert deck["environment"]["RINTHEL_HOSTEXECD_URL"] == (
        "${RINTHEL_HOSTEXECD_URL:-http://127.0.0.1:${RINTHEL_HOSTEXECD_PORT:-%d}}" % port
    )
    assert not any("extension" in str(volume) for volume in deck.get("volumes", []))


def test_understory_keeps_its_fixed_network_and_bundle(config):
    understory = config["services"]["understory"]
    mounts = {volume["target"]: volume for volume in understory["volumes"]}

    assert Path(mounts["/bundle"]["source"]) == ROOT / "data" / "understory"
    assert understory["environment"]["AUTH_TOKEN"] == "${AUTH_TOKEN:-}"
    network = config["networks"]["understory-net"]
    assert network["name"] == "rinthel-general_understory_net"
    assert network["ipam"]["config"][0]["subnet"] == "172.30.99.0/24"
