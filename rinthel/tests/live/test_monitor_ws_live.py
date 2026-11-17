"""The Monitor over the real WS: the Telemetry streams arrive. The ``llm``
line of ``models_status`` reports a real llama-server (that test needs
``--start-llm``)."""

import json
import time

import pytest
from websockets.sync.client import connect

STREAMS = {"docker_status", "gpu_sample", "cpu_ram_sample", "log_line", "models_status"}
WINDOW_S = 15


def _envelopes(ws, seconds: float):
    """Envelopes ``(type, data)`` during ``seconds``."""
    deadline = time.monotonic() + seconds
    while (left := deadline - time.monotonic()) > 0:
        try:
            raw = ws.recv(timeout=left)
        except TimeoutError:
            return
        message = json.loads(raw)
        yield message["type"], message["data"]


@pytest.fixture
def monitor(daemon):
    with connect(daemon.ws_monitor_url) as ws:
        yield ws


def test_every_telemetry_stream_arrives_and_a_llama_log_line_comes_back(daemon, monitor):
    line = f"echo {time.time_ns()}"
    with daemon.llama_log.open("a") as log:
        log.write(line + "\n")
    seen: set[str] = set()
    lines: set[str] = set()
    for kind, data in _envelopes(monitor, WINDOW_S):
        seen.add(kind)
        if kind == "log_line":
            lines.add(data["line"])
        if STREAMS <= seen and line in lines:
            break

    assert STREAMS <= seen, f"missing: {STREAMS - seen}"
    assert line in lines


def _llm_state(data: dict) -> str:
    return next(c for c in data["capabilities"] if c["capability"] == "llm")["state"]


def test_the_llm_line_turns_ready_with_a_real_llama_server(spawn_daemon, real_llama, base_model):
    daemon = spawn_daemon(models=(base_model,))
    with connect(daemon.ws_monitor_url) as ws:
        assert _llm_state(next(d for k, d in _envelopes(ws, WINDOW_S) if k == "models_status")) == "down"
        real_llama(daemon)

        states = [_llm_state(d) for k, d in _envelopes(ws, WINDOW_S) if k == "models_status"]

    assert states[-1] == "ready", states
