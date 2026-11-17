"""INSTALL with voice (``--voice``, opt-in, Linux only): whisper.cpp (CPU) and
audio.cpp (CUDA) at their pins, the default voice models, their catalog
entries active and both services started. Runs over the ``Host`` of doubles
with a real ``tmp_path``: no real build, download or process. What a program
leaves on disk is the double's ``on_success``; the exact argv of a build is
not the phase's contract, only which programs ran and with which pins."""

import dataclasses
import json
from pathlib import Path

import pytest

from rinthel_tui.config import with_voice_from_instance
from rinthel_tui.lifecycle import install, install_tasks, specs
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.executor import execute
from rinthel_tui.models.adapters.json_catalog import JsonCatalog, write_catalog
from rinthel_tui.models.adapters.toml_active import TomlActiveModels
from tests.lifecycle.fakes import fake_host


@pytest.fixture
def host():
    host, _ = fake_host()
    host.runner.succeed_by_default()
    return host


@pytest.fixture
def voice_cfg(cfg, tmp_path):
    """Voice binaries and models under ``tmp_path``, none of them there yet."""
    return dataclasses.replace(
        cfg,
        install=dataclasses.replace(cfg.install, models_dir=tmp_path / "models"),
        whisper=dataclasses.replace(cfg.whisper, bin=tmp_path / "whisper.cpp" / "build" / "bin" / "whisper-server"),
        audiocpp=dataclasses.replace(
            cfg.audiocpp, bin=tmp_path / "audio.cpp" / "build" / "rinthel" / "bin" / "audiocpp_server",
        ),
    )


# ── the pins ───────────────────────────────────────────────────────────


def test_builds_and_downloads_follow_the_pins(voice_cfg):
    whisper, audiocpp = install_tasks.whisper_build(voice_cfg), install_tasks.audiocpp_build(voice_cfg)
    ggml, pocket = install_tasks.whisper_model(voice_cfg), install_tasks.pocket_tts(voice_cfg)

    assert (whisper.repo_url, whisper.sha) == (
        "https://github.com/ggml-org/whisper.cpp.git", "a2b36eb677918d4f9ab1db7b8a7ff968563ed163",
    )
    assert (audiocpp.repo_url, audiocpp.sha) == (
        "https://github.com/0xShug0/audio.cpp.git", "5ba81ac54fb071b835680973f8868546b4db372b",
    )
    assert ggml.sha256 == "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"
    assert "/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/" in ggml.url
    assert pocket.sha256 == "73f0e8fd85472057289b0ae6098be473a5d112cc01b0ecb17f423198bcf445e1"
    assert "/resolve/6d5436fc85f7a20c2e9f4e472b7f3a532f686444/" in pocket.url
    assert (ggml.dest.parent, pocket.dest.parent) == (voice_cfg.install.models_dir,) * 2


# ── whisper.cpp (CPU) ──────────────────────────────────────────────────


async def test_whisper_is_cloned_at_its_pin_and_built_for_cpu(host, report, voice_cfg):
    task = install_tasks.whisper_build(voice_cfg)

    await install.phase_install_whisper(host, report, task=task)

    assert host.runner.ran("git")[0].cmd[:2] == ("git", "clone")
    assert any(task.sha in call.cmd for call in host.runner.ran("git"))
    configure, build = host.runner.ran("cmake")
    assert "-DGGML_CUDA=OFF" in configure.cmd
    assert "whisper-server" in build.cmd


async def test_an_existing_checkout_is_moved_to_the_pin_not_cloned_again(host, report, voice_cfg):
    task = install_tasks.whisper_build(voice_cfg)
    (task.repo / ".git").mkdir(parents=True)

    await install.phase_install_whisper(host, report, task=task)

    assert not [c for c in host.runner.ran("git") if c.cmd[1] == "clone"]
    assert any(c.cmd[-2:] == ("checkout", task.sha) for c in host.runner.ran("git"))


async def test_a_built_whisper_is_not_built_again(host, report, voice_cfg):
    task = install_tasks.whisper_build(voice_cfg)
    task.bin.parent.mkdir(parents=True)
    task.bin.touch()

    await install.phase_install_whisper(host, report, task=task)

    assert host.runner.calls == []


# ── audio.cpp (CUDA) ───────────────────────────────────────────────────


async def test_audiocpp_is_built_with_cuda_and_only_pocket_tts(host, report, voice_cfg):
    host.host_info.install_cuda("/usr/local/cuda/bin/nvcc")
    task = install_tasks.audiocpp_build(voice_cfg)

    await install.phase_install_audiocpp(host, report, task=task)

    (build,) = host.runner.ran("bash")
    assert build.cmd[1] == "scripts/build_linux.sh"
    assert build.cmd[build.cmd.index("--cuda") + 1] == "on"
    assert build.cmd[build.cmd.index("--models") + 1] == "pocket_tts"
    assert (build.cwd, build.env) == (task.repo, {"CUDACXX": "/usr/local/cuda/bin/nvcc"})


async def test_audiocpp_without_nvcc_fails_before_cloning(host, report, voice_cfg):
    with pytest.raises(PhaseError):
        await install.phase_install_audiocpp(host, report, task=install_tasks.audiocpp_build(voice_cfg))

    assert host.runner.calls == []


# ── catalog and start: an existing Instance ends with stt/tts running ──


def _voice_files(cfg) -> None:
    """What the download and build steps leave: the models and the voice WAV."""
    for task in (install_tasks.whisper_model(cfg), install_tasks.pocket_tts(cfg)):
        task.dest.parent.mkdir(parents=True, exist_ok=True)
        task.dest.write_bytes(b"GGUF" + b"\0" * 8)
    (stt, tts) = install_tasks.default_voice_models(cfg)
    tts.voice.parent.mkdir(parents=True, exist_ok=True)
    tts.voice.write_bytes(b"RIFF")


async def _catalog_and_start(cfg, host):
    for port in (cfg.whisper.port, cfg.audiocpp.port):
        host.probe.script_http(f"http://127.0.0.1:{port}/health", True)
    (unit,) = [u for u in specs.install_plan(cfg, voice=True).batches[0].units if u.service == "voz"]
    tail = specs.Unit("voz", tuple(p for p in unit.phases if p.label.startswith("◈ VOZ")))

    async def ignore(*_):
        pass

    (outcome,) = await execute(specs.Plan("stop", (specs.Batch(None, (tail,)),)), ignore, host)
    return outcome


async def test_voice_on_an_existing_instance_adds_and_activates_its_entries_and_starts_both(host, voice_cfg):
    instance = voice_cfg.instance
    write_catalog(instance.models_catalog_path, [voice_cfg.local_model])
    TomlActiveModels(instance.instance_toml_path).set("llm", voice_cfg.local_model.id)
    _voice_files(voice_cfg)

    outcome = await _catalog_and_start(voice_cfg, host)

    assert outcome.ok, outcome.message
    ids = [e.id for e in JsonCatalog(instance.models_catalog_path).entries()]
    assert ids == [voice_cfg.local_model.id, "whisper-base", "pocket-tts-es"]
    active = TomlActiveModels(instance.instance_toml_path)
    assert (active.get("llm"), active.get("stt"), active.get("tts")) == (voice_cfg.local_model.id, "whisper-base", "pocket-tts-es")
    assert [Path(s.argv[0]).name for s in host.processes.spawns] == ["whisper-server", "audiocpp_server"]
    fresh = with_voice_from_instance(voice_cfg)
    assert (fresh.stt_model.id, fresh.tts_model.voice) == ("whisper-base", voice_cfg.audiocpp.repo / "assets" / "resources" / "b.wav")


async def test_voice_again_keeps_the_admins_entries_and_choices(host, voice_cfg, tmp_path):
    instance = voice_cfg.instance
    _voice_files(voice_cfg)
    other = tmp_path / "otro.bin"
    other.write_bytes(b"x")
    instance.models_catalog_path.write_text(json.dumps({"models": [
        {"id": "whisper-base", "name": "Mío", "capability": "stt", "gguf": str(other)},
    ]}))
    TomlActiveModels(instance.instance_toml_path).set("stt", "whisper-base")

    outcome = await _catalog_and_start(voice_cfg, host)

    assert outcome.ok, outcome.message
    entries = {e.id: e for e in JsonCatalog(instance.models_catalog_path).entries()}
    assert entries["whisper-base"].model.name == "Mío"
    assert "pocket-tts-es" in entries
    whisper = next(s for s in host.processes.spawns if Path(s.argv[0]).name == "whisper-server")
    assert whisper.argv[whisper.argv.index("--model") + 1] == str(other)


async def test_a_voice_service_that_does_not_come_up_fails_the_unit(host, voice_cfg):
    _voice_files(voice_cfg)
    stt, _ = install_tasks.default_voice_models(voice_cfg)
    host.processes.script(
        [str(voice_cfg.whisper.bin), "--host", "127.0.0.1", "--port", str(voice_cfg.whisper.port),
         "--model", str(stt.gguf), "--language", "auto", "--threads", str(voice_cfg.whisper.threads)],
        exits=True,
    )

    outcome = await _catalog_and_start(voice_cfg, host)

    assert not outcome.ok
