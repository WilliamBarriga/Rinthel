"""El sobre ``{"type", "data"}`` de cada mensaje de ``/ws/monitor`` y los
``type`` que puede llevar. Espejo en ``rinthel-client/src/protocol.rs``,
atado por las fixtures de ``tests/protocol_fixtures/`` (ADR-0001: sin
codegen)."""

import json
from enum import StrEnum


class MessageType(StrEnum):
    # Telemetry streams.
    DOCKER_STATUS = "docker_status"
    GPU_SAMPLE = "gpu_sample"
    CPU_RAM_SAMPLE = "cpu_ram_sample"
    LOG_LINE = "log_line"
    LLAMA_STATUS = "llama_status"
    # Progreso de un Lifecycle plan.
    PHASE_STATUS = "phase_status"
    PHASE_LOG = "phase_log"
    PHASE_BATCH = "phase_batch"


def envelope(type_: MessageType, data: dict) -> str:
    return json.dumps({"type": type_, "data": data})
