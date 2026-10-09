"""Validate the real Compose seam without starting Docker or exposing env values."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose CLI is unavailable")
def test_compose_merges_subtrees_and_mounts_the_host_exec_extension():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["docker", "compose", "-f", str(root / "docker-compose.yaml"), "config", "--no-interpolate", "--format", "json"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    config = json.loads(result.stdout)
    portal = config["services"]["portal"]
    assert Path(portal["build"]["context"]) == root / "pithagoras"
    mounts = {volume["target"]: volume for volume in portal["volumes"]}
    extension = mounts["/app/rinthel-extensions/rinthel-host-exec"]
    assert Path(extension["source"]) == root / "extensions" / "rinthel-host-exec"
    assert extension["read_only"] is True
    assert extension["bind"]["create_host_path"] is False
    environment = portal["environment"]
    if isinstance(environment, list):
        environment = dict(item.split("=", 1) for item in environment)
    assert environment["RINTHEL_HOSTEXECD_TOKEN"] == "${RINTHEL_HOSTEXECD_TOKEN:-}"
    assert environment["RINTHEL_HOST_EXEC_EXTENSION"].endswith("rinthel-host-exec/index.ts")
    network = config["networks"]["understory-net"]
    assert network["name"] == "rinthel-general_understory_net"
    assert network["ipam"]["config"][0]["subnet"] == "172.30.99.0/24"
