"""El CLI offline de Local models (``python -m rinthel_tui.models``): lista el
catálogo y cambia el activo con los servicios parados. Corre ``main`` sobre
una Instance en ``tmp_path``; si llama-server sigue escuchando lo dice el
``FakeProbe``."""

import json

import pytest

from rinthel_tui.config import default_config
from rinthel_tui.instance import Instance
from rinthel_tui.models.__main__ import main
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from tests.lifecycle.fakes import FakeProbe


@pytest.fixture
def instance(tmp_path, monkeypatch):
    monkeypatch.delenv("RINTHEL_LLAMA_PORT", raising=False)
    for name in ("a", "b"):
        (tmp_path / f"{name}.gguf").write_bytes(b"GGUF" + b"\0" * 8)
    entries = [
        {"id": name, "name": name.upper(), "capability": "llm", "gguf": str(tmp_path / f"{name}.gguf"),
         "context_window": 4096}
        for name in ("a", "b")
    ]
    entries.append({**entries[0], "id": "roto", "gguf": str(tmp_path / "nada.gguf")})
    instance = Instance(tmp_path)
    instance.models_catalog_path.write_text(json.dumps({"models": entries}))
    TomlActiveModels(instance.instance_toml_path).set("llm", "a")
    return instance


def _run(instance, *args, llama_running=False):
    probe = FakeProbe()
    probe.script_port(8080, llama_running)
    return main(["--root", str(instance.root), *args], probe=probe)


def test_use_changes_the_active_model_with_the_services_stopped(instance, capsys):
    assert _run(instance, "use", "b") == 0

    assert TomlActiveModels(instance.instance_toml_path).get("llm") == "b"
    assert default_config(instance, platform="linux").local_model.id == "b"


def test_use_refuses_while_llama_server_is_running(instance, capsys):
    assert _run(instance, "use", "b", llama_running=True) == 2

    assert TomlActiveModels(instance.instance_toml_path).get("llm") == "a"
    assert "corriendo" in capsys.readouterr().err


@pytest.mark.parametrize("model_id,reason", [("nadie", "desconocido"), ("roto", "GGUF no encontrado")])
def test_use_refuses_what_cannot_be_activated(instance, capsys, model_id, reason):
    assert _run(instance, "use", model_id) == 2

    assert TomlActiveModels(instance.instance_toml_path).get("llm") == "a"
    assert reason in capsys.readouterr().err


def test_list_marks_the_active_model_and_the_invalid_entries(instance, capsys):
    assert _run(instance, "list") == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("* a")
    assert lines[1].startswith("  b")
    assert "GGUF no encontrado" in lines[2]
