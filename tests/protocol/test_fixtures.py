"""Fixture dorada (sesión 00 del porteo): un JSON por forma de mensaje del
protocolo daemon<->cliente, fuente única compartida con los tests Rust
(``rinthel-client-spike/tests/protocol_fixtures.rs``) — ver
``../protocol_fixtures/``. Cierra el riesgo de drift que ADR 0001 aceptó al
descartar codegen: si el daemon cambia una forma sin tocar el fixture, este
test y su espejo en Rust divergen visiblemente en vez de en silencio.
"""

import json
from pathlib import Path

from rinthel_tui.monitoring.resources import CpuRamSample, GpuSample
from rinthel_tui.monitoring.services import DockerContainer

FIXTURES = Path(__file__).parent.parent / "protocol_fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_theme_shape():
    theme = _load("theme.json")
    assert set(theme["canonical"]) == {
        "fg", "accent", "electric", "warn", "success", "hot",
        "caution", "glow", "dim", "bg",
    }
    assert isinstance(theme["extended"], dict)
    assert isinstance(theme["frame_chars"], list)
    assert all(isinstance(c, str) for c in theme["frame_chars"])


def test_docker_status_shape():
    envelope = _load("docker_status.json")
    assert envelope["type"] == "docker_status"
    containers = envelope["data"]["containers"]
    assert containers
    for c in containers:
        DockerContainer(**c)


def test_gpu_sample_shape():
    envelope = _load("gpu_sample.json")
    assert envelope["type"] == "gpu_sample"
    GpuSample(**envelope["data"])


def test_cpu_ram_sample_shape():
    envelope = _load("cpu_ram_sample.json")
    assert envelope["type"] == "cpu_ram_sample"
    CpuRamSample(**envelope["data"])


def test_log_line_shape():
    envelope = _load("log_line.json")
    assert envelope["type"] == "log_line"
    assert isinstance(envelope["data"]["line"], str)


def _assert_command_result_shape(result: dict) -> None:
    assert result["results"]
    for outcome in result["results"]:
        assert outcome.keys() == {"service", "ok", "message"}
        assert isinstance(outcome["service"], str)
        assert isinstance(outcome["ok"], bool)
        assert isinstance(outcome["message"], str)


def test_boot_result_shape():
    _assert_command_result_shape(_load("boot_result.json"))


def test_terminate_result_shape():
    _assert_command_result_shape(_load("terminate_result.json"))
