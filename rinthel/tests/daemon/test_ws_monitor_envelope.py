"""Caracterización del sobre de ``/ws/monitor``: lo que el cliente Rust
(``rinthel-client/src/protocol.rs``) deserializa, byte por campo, a través de
la composición real de ``create_app`` — sin reemplazar el Monitor. Las
fuentes del host se imitan con ejecutables falsos (``nvidia-smi``,
``docker``) al frente del ``PATH`` y un ``llama.log`` en la Instance del
test; ``models_status``, con el catálogo en memoria y el ``Probe`` de dobles
del ``Host``.
Cada mensaje tiene que ser igual a su fixture de ``tests/protocol_fixtures/``
(CPU/RAM, que no se puede fijar, en forma y tipos)."""

import dataclasses
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from rinthel_tui.api import create_app
from rinthel_tui.api.adapters import real_telemetry
from rinthel_tui.models.domain.types import CatalogEntry, LocalModel

FIXTURES = Path(__file__).parent.parent / "protocol_fixtures"
TELEMETRY = {"docker_status", "gpu_sample", "cpu_ram_sample", "log_line", "models_status"}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _fake_host(bin_dir: Path, fake_executable) -> None:
    gpu = _fixture("gpu_sample")["data"]
    csv = ", ".join(str(gpu[k]) for k in ("utilization", "memory_used", "memory_total", "temperature", "power_draw"))
    fake_executable(bin_dir / "nvidia-smi", f"print({csv!r})\n")
    rows = [
        {"Name": "understory-app-1", "State": "running", "Status": "Up 2 hours",
         "Publishers": [{"PublishedPort": 3800, "TargetPort": 3800}]},
        {"Name": "rinthel-general-deck-1", "State": "exited", "Status": "Exited (0) 5 minutes ago", "Publishers": []},
    ]
    # JSON-lines, como el ``docker compose ps`` de las versiones nuevas.
    fake_executable(bin_dir / "docker", "import sys\n" + "".join(f"print({json.dumps(r)!r})\n" for r in rows))


def test_every_telemetry_message_keeps_the_envelope_the_clients_read(
    daemon_cfg, adapters, host, service_headers, tmp_path, monkeypatch, fake_executable
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_host(bin_dir, fake_executable)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    daemon_cfg.llama.log.write_text(_fixture("log_line")["data"]["line"] + "\n")
    host.probe.script_http(f"http://127.0.0.1:{daemon_cfg.llama.port}/v1/models", True)
    host.probe.script_http(f"http://127.0.0.1:{daemon_cfg.understory.port}/", True)
    # Voice active as INSTALL with voice leaves it: whisper answers, audio.cpp not yet.
    host.probe.script_http(f"http://127.0.0.1:{daemon_cfg.whisper.port}/health", True)
    adapters.models.catalog.set_entries([
        CatalogEntry(daemon_cfg.local_model.id, daemon_cfg.local_model),
        CatalogEntry("whisper-base", LocalModel("whisper-base", "Whisper", "stt", Path("/m/ggml-base.bin"), 0)),
        CatalogEntry("pocket-tts-es", LocalModel("pocket-tts-es", "Pocket", "tts", Path("/m/pocket.gguf"), 0)),
    ])
    adapters.models.active.set("llm", daemon_cfg.local_model.id)
    adapters.models.active.set("stt", "whisper-base")
    adapters.models.active.set("tts", "pocket-tts-es")
    # Only Understory among the managed services, as in the shared fixture: Deck and hostexecd off.
    cfg = dataclasses.replace(
        daemon_cfg,
        deck=dataclasses.replace(daemon_cfg.deck, enabled=False),
        hostexecd=dataclasses.replace(daemon_cfg.hostexecd, enabled=False),
    )
    telemetry = real_telemetry(lambda: app.state.cfg, host, adapters.models)
    app = create_app(cfg, adapters=dataclasses.replace(adapters, telemetry=telemetry))
    token = service_headers["x-rinthel-service-secret"]

    first: dict[str, dict] = {}
    with TestClient(app).websocket_connect(f"/ws/monitor?token={token}") as ws:
        while first.keys() < TELEMETRY:
            message = ws.receive_json()
            assert message.keys() == {"type", "data"}
            first.setdefault(message["type"], message)

    for name in TELEMETRY - {"cpu_ram_sample"}:
        assert first[name] == _fixture(name), name
    cpu_ram = first["cpu_ram_sample"]
    assert cpu_ram["data"].keys() == _fixture("cpu_ram_sample")["data"].keys()
    assert all(isinstance(v, float) for v in cpu_ram["data"].values())
