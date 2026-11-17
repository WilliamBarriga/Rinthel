"""POST /exec y GET /history de hostexecd, a través de los handlers de ruta
de `daemon.py` (mismo criterio que tests/daemon/: sin TestClient). El token y
el audit log se aíslan por test — nunca el `.env` ni `logs/` reales."""

import json

import pytest
from fastapi import HTTPException

from hostexecd import audit, daemon

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RINTHEL_HOSTEXECD_TOKEN", TOKEN)
    monkeypatch.setattr(audit, "LOG_PATH", tmp_path / "hostexecd.log")


def run(payload: dict) -> dict:
    return json.loads(daemon.exec_command(payload, x_rinthel_token=TOKEN).body)


def test_missing_cwd_is_a_400_not_a_crash(tmp_path):
    with pytest.raises(HTTPException) as err:
        run({"command": "ls", "cwd": str(tmp_path / "nope")})
    assert err.value.status_code == 400


@pytest.mark.parametrize("timeout", [0, -5, 601, True])
def test_timeout_outside_1_to_600_seconds_is_a_400(timeout):
    with pytest.raises(HTTPException) as err:
        run({"command": "true", "timeout": timeout})
    assert err.value.status_code == 400


def test_timeout_at_the_cap_is_accepted():
    assert run({"command": "true", "timeout": 600})["exit_code"] == 0


def test_large_output_is_truncated_to_50kb_with_a_notice():
    out = run({"command": "head -c 60000 /dev/zero | tr '\\0' x"})
    assert out["stdout"].startswith("x" * 50_000)
    assert "x" * 50_001 not in out["stdout"]
    assert "60000" in out["stdout"]  # dice cuánto había en total


def test_small_output_is_untouched():
    assert run({"command": "echo hola"})["stdout"] == "hola\n"


def history(limit: int) -> list[dict]:
    return json.loads(daemon.history(limit=limit, x_rinthel_token=TOKEN).body)["entries"]


@pytest.mark.parametrize("limit", [0, -1, 201])
def test_history_limit_outside_1_to_200_is_a_400(limit):
    run({"command": "true"})
    with pytest.raises(HTTPException) as err:
        history(limit)
    assert err.value.status_code == 400


def test_history_returns_the_most_recent_first():
    for word in ("uno", "dos", "tres"):
        run({"command": f"echo {word}"})
    assert [e["command"] for e in history(2)] == ["echo tres", "echo dos"]
