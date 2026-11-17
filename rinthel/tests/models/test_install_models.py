"""INSTALL y los Local models: baja solo el GGUF por defecto del Validated
profile y deja el catálogo inicial, su ejemplo y el modelo activo. Corre la
unidad de llama del plan de INSTALL sobre el ``Host`` de dobles; el ``curl``
que escribe el archivo lo simula el ``FakeRunner``."""

import dataclasses
import json
from pathlib import Path

import pytest

from rinthel_tui.config import VALIDATED_PROFILES, default_config
from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.executor import execute
from rinthel_tui.models.adapters.json_catalog import JsonCatalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from tests.lifecycle.fakes import RunCall, fake_host

PROFILE_MODEL = VALIDATED_PROFILES["linux"].model


def _gguf(call: RunCall) -> None:
    Path(call.cmd[call.cmd.index("-o") + 1]).write_bytes(b"GGUF" + b"\0" * 16)


@pytest.fixture
def instance_cfg(cfg, tmp_path):
    """Una Instance recién clonada: llama.cpp ya compilado, nada de modelos."""
    repo = tmp_path / "llama.cpp"
    (repo / ".git").mkdir(parents=True)
    binary = repo / "build-cuda" / "bin" / "llama-server"
    binary.parent.mkdir(parents=True)
    binary.touch()
    install = dataclasses.replace(cfg.install, llamacpp_repo_dir=repo, models_dir=tmp_path / "models")
    return dataclasses.replace(cfg, install=install)


async def _install_llama(cfg, platform="linux"):
    host, _ = fake_host()
    host.host_info.os = platform
    host.runner.succeed_by_default()
    host.runner.on_success("curl", _gguf)
    (unit,) = [u for u in specs.install_plan(cfg).batches[0].units if u.service == "llama.cpp + modelo"]
    plan = specs.Plan(on_failure="stop", batches=(specs.Batch(marker=None, units=(unit,)),))

    async def ignore(*_):
        pass

    (outcome,) = await execute(plan, ignore, host)
    return host, outcome


async def test_install_downloads_only_the_default_model_of_the_profile(instance_cfg, tmp_path):
    host, outcome = await _install_llama(instance_cfg)

    assert outcome.ok, outcome.message
    (curl,) = host.runner.ran("curl")
    assert curl.cmd[-1] == PROFILE_MODEL.url
    assert (tmp_path / "models" / PROFILE_MODEL.file).read_bytes().startswith(b"GGUF")


async def test_install_writes_the_initial_catalog_with_that_entry_active(instance_cfg, tmp_path):
    await _install_llama(instance_cfg)

    instance = instance_cfg.instance
    (entry,) = JsonCatalog(instance.models_catalog_path).entries()
    assert entry.activable
    assert (entry.id, entry.model.gguf, entry.model.context_window) == (
        PROFILE_MODEL.id, tmp_path / "models" / PROFILE_MODEL.file, 112000,
    )
    assert TomlActiveModels(instance.instance_toml_path).get("llm") == PROFILE_MODEL.id
    reread = default_config(instance, platform="linux")
    assert reread.local_model is not None and reread.local_model.id == PROFILE_MODEL.id


async def test_install_writes_a_catalog_example_that_reads_as_a_catalog(instance_cfg):
    await _install_llama(instance_cfg)

    example = instance_cfg.instance.models_example_path
    ids = [e.id for e in JsonCatalog(example).entries()]
    assert len(ids) >= 2
    raw = json.loads(example.read_text())["models"]
    assert any(m.get("mmproj") for m in raw) and any(m.get("overrides") for m in raw)


async def test_on_windows_the_entry_carries_the_measured_window(instance_cfg):
    cfg = dataclasses.replace(instance_cfg, platform="windows")
    await _install_llama(cfg, platform="windows")

    (entry,) = JsonCatalog(cfg.instance.models_catalog_path).entries()
    assert entry.model.context_window == 65536


async def test_a_rerun_never_touches_the_catalog_nor_the_active_model(instance_cfg):
    await _install_llama(instance_cfg)
    instance = instance_cfg.instance
    edited = '{"models": []}\n'
    instance.models_catalog_path.write_text(edited)
    TomlActiveModels(instance.instance_toml_path).set("llm", "otro")

    host, outcome = await _install_llama(instance_cfg)

    assert outcome.ok
    assert instance.models_catalog_path.read_text() == edited
    assert TomlActiveModels(instance.instance_toml_path).get("llm") == "otro"
    assert host.runner.ran("curl") == []
