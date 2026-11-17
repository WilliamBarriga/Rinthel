"""Fixture dorada de los envelopes del WebSocket: un JSON por forma de
mensaje del protocolo daemon<->cliente, fuente única compartida con los tests Rust
(``rinthel-client/tests/protocol_fixtures.rs``) — ver
``../protocol_fixtures/``. Cierra el riesgo de drift que ADR 0001 aceptó al
descartar codegen: si el daemon cambia una forma sin tocar el fixture, este
test y su espejo en Rust divergen visiblemente en vez de en silencio. Las fixtures de rutas HTTP se
validan contra la respuesta real en
``tests/daemon/test_protocol_fixtures_http.py``.
"""

import json
from pathlib import Path

from rinthel_tui.monitoring.domain.envelope import MessageType
from rinthel_tui.monitoring.domain.types import CpuRamSample, DockerContainer, GpuSample

FIXTURES = Path(__file__).parent.parent / "protocol_fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


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


def test_llama_status_shape():
    envelope = _load("llama_status.json")
    assert envelope["type"] == "llama_status"
    assert envelope["data"].keys() == {"ready"}
    assert isinstance(envelope["data"]["ready"], bool)


def test_phase_status_shape():
    envelope = _load("phase_status.json")
    assert envelope["type"] == MessageType.PHASE_STATUS
    assert envelope["data"].keys() == {"label", "status"}
    assert envelope["data"]["status"] in {"running", "done", "error"}


def test_phase_log_shape():
    envelope = _load("phase_log.json")
    assert envelope["type"] == MessageType.PHASE_LOG
    assert envelope["data"].keys() == {"kind", "message"}
    assert envelope["data"]["kind"] in {"info", "success", "warn", "error"}


def test_phase_batch_shape():
    envelope = _load("phase_batch.json")
    assert envelope["type"] == MessageType.PHASE_BATCH
    assert envelope["data"]["batch"] in {"boot", "rebuild"}


def test_every_message_type_has_a_fixture():
    assert {_load(f"{t}.json")["type"] for t in MessageType} == set(MessageType)
