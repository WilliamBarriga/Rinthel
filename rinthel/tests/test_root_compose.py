"""Validate the real root Compose seam without starting Docker or exposing env values."""

import json
import os
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
    network = config["networks"]["understory-net"]
    assert network["name"] == "rinthel-general_understory_net"
    assert network["ipam"]["config"][0]["subnet"] == "172.30.99.0/24"


def _environment(service: dict) -> dict[str, str]:
    """Compose lists a merged `extends` environment as `KEY=value` lines without interpolating."""
    env = service["environment"]
    return dict(line.split("=", 1) for line in env) if isinstance(env, list) else env


def test_understory_takes_its_token_from_the_one_deck_presents(config):
    understory = _environment(config["services"]["understory"])
    deck = _environment(config["services"]["deck"])

    # `:?` makes compose refuse an unset or empty token: an empty AUTH_TOKEN is Understory without auth.
    assert understory["AUTH_TOKEN"].startswith("${UNDERSTORY_TOKEN:?")
    assert deck["UNDERSTORY_TOKEN"] == "${UNDERSTORY_TOKEN:-}"


def test_understory_is_published_on_the_host_loopback_only(config):
    assert config["services"]["understory"]["ports"] == ["127.0.0.1:${RINTHEL_UNDERSTORY_PORT:-3800}:3800"]


@pytest.mark.parametrize("token, ok", [(None, False), ("", False), ("a-token", True)])
def test_compose_refuses_to_run_without_an_understory_token(config, tmp_path, token, ok):
    env = {k: v for k, v in os.environ.items() if k != "UNDERSTORY_TOKEN"}
    if token is not None:
        env["UNDERSTORY_TOKEN"] = token
    env_file = tmp_path / ".env"
    env_file.write_text("")
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "-f", str(ROOT / "docker-compose.yaml"), "config", "--quiet"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )

    assert (result.returncode == 0) is ok, result.stderr
    if not ok:
        assert "UNDERSTORY_TOKEN" in result.stderr
