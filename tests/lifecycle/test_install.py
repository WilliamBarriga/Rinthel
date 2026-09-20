"""Fases de INSTALL — idempotencia (reruns seguros, omiten lo que ya existe)
y generación de .env a partir de .env.example.

Estilo de mocking: `install.py` importa `_run` directamente de `phases.py`
(`from rinthel_tui.lifecycle.phases import _run`), así que se parchea sobre
`install`, no sobre `phases` — es el nombre que install.py realmente usa.
`shutil.which` y `asyncio.create_subprocess_exec` se parchean para
`phase_install_preflight` (que no toca disco/red propios, solo detecta
herramientas).
"""

import asyncio
import dataclasses
import json
import os
import shutil

from rinthel_tui.lifecycle import install
from rinthel_tui.lifecycle.phases import PhaseError


def _recording_run(rc_by_first_arg: dict[str, int] | None = None):
    rc_by_first_arg = rc_by_first_arg or {}
    calls: list[list[str]] = []

    async def fake(cmd, report, cwd=None, env=None):
        calls.append(list(cmd))
        return rc_by_first_arg.get(cmd[0], 0)

    return fake, calls


# ── PREFLIGHT ─────────────────────────────────────────────────────


async def test_preflight_raises_when_tool_missing(monkeypatch, cfg, report):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    try:
        await install.phase_install_preflight(cfg, report)
        raised = False
    except PhaseError:
        raised = True
    assert raised
    assert any("falta 'git'" in msg for msg in report.errors)


async def test_preflight_succeeds_when_everything_present(monkeypatch, cfg, report):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    async def fake_exec(*args, **kwargs):
        class _Proc:
            async def wait(self):
                return 0

        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await install.phase_install_preflight(cfg, report)

    assert any("Docker daemon activo" in msg for msg in report.successes)


# ── CLONE LLAMA.CPP ────────────────────────────────────────────────


def _with_llamacpp_repo_dir(cfg, repo_dir):
    return dataclasses.replace(cfg, install=dataclasses.replace(cfg.install, llamacpp_repo_dir=repo_dir))


def _with_pithagoras_dir(cfg, pithagoras_dir):
    return dataclasses.replace(cfg, pithagoras=dataclasses.replace(cfg.pithagoras, dir=pithagoras_dir))


def _with_understory_dir(cfg, understory_dir):
    return dataclasses.replace(cfg, understory=dataclasses.replace(cfg.understory, dir=understory_dir))


async def test_clone_llamacpp_skips_when_already_cloned(cfg, report, tmp_path):
    repo_dir = tmp_path / "llama.cpp"
    (repo_dir / ".git").mkdir(parents=True)
    cfg = _with_llamacpp_repo_dir(cfg, repo_dir)

    await install.phase_install_clone_llamacpp(cfg, report)

    assert any("ya existe — omito clone" in msg for msg in report.warnings)


async def test_clone_llamacpp_clones_when_missing(monkeypatch, cfg, report, tmp_path):
    repo_dir = tmp_path / "llama.cpp"
    cfg = _with_llamacpp_repo_dir(cfg, repo_dir)
    fake, calls = _recording_run()
    monkeypatch.setattr(install, "_run", fake)

    await install.phase_install_clone_llamacpp(cfg, report)

    assert calls[0][0] == "git"
    assert any("clonado en" in msg for msg in report.successes)


async def test_clone_llamacpp_raises_when_git_fails(monkeypatch, cfg, report, tmp_path):
    repo_dir = tmp_path / "llama.cpp"
    cfg = _with_llamacpp_repo_dir(cfg, repo_dir)
    fake, _ = _recording_run({"git": 1})
    monkeypatch.setattr(install, "_run", fake)

    try:
        await install.phase_install_clone_llamacpp(cfg, report)
        raised = False
    except PhaseError:
        raised = True
    assert raised


# ── BUILD LLAMA.CPP ────────────────────────────────────────────────


async def test_build_llamacpp_skips_when_binary_exists(cfg, report, tmp_path):
    repo_dir = tmp_path / "llama.cpp"
    bin_path = repo_dir / "build-cuda" / "bin" / "llama-server"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_text("fake binary")
    cfg = _with_llamacpp_repo_dir(cfg, repo_dir)

    await install.phase_install_build_llamacpp(cfg, report)

    assert any("ya existe — omito build" in msg for msg in report.warnings)


async def test_build_llamacpp_raises_when_cmake_configure_fails(monkeypatch, cfg, report, tmp_path):
    repo_dir = tmp_path / "llama.cpp"
    cfg = _with_llamacpp_repo_dir(cfg, repo_dir)
    fake, _ = _recording_run({"cmake": 1})
    monkeypatch.setattr(install, "_run", fake)

    try:
        await install.phase_install_build_llamacpp(cfg, report)
        raised = False
    except PhaseError:
        raised = True
    assert raised
    assert any("cmake configure falló" in msg for msg in report.errors)


# ── DOWNLOAD MODEL ─────────────────────────────────────────────────


async def test_download_model_skips_when_already_downloaded(cfg, report, tmp_path):
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"not empty")
    cfg = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, model=model_path))

    await install.phase_install_download_model(cfg, report)

    assert any("ya existe — omito descarga" in msg for msg in report.warnings)


async def test_download_model_downloads_when_missing(monkeypatch, cfg, report, tmp_path):
    model_path = tmp_path / "models" / "model.gguf"
    cfg = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, model=model_path))
    fake, calls = _recording_run()
    monkeypatch.setattr(install, "_run", fake)

    await install.phase_install_download_model(cfg, report)

    assert calls[0][0] == "curl"
    assert any("descargado en" in msg for msg in report.successes)


# ── SETUP PITHAGORAS ─────────────────────────────────────────────


def test_prepare_pithagoras_for_windows_is_idempotent(report, tmp_path):
    pithagoras_dir = tmp_path / "pithagoras"
    pithagoras_dir.mkdir()
    compose_path = pithagoras_dir / "docker-compose.yml"
    dockerfile_path = pithagoras_dir / "Dockerfile"
    compose_path.write_text(
        "services:\n"
        "  portal:\n"
        "    network_mode: host\n"
        "  tailscale:\n"
        "    environment:\n"
        "      TS_AUTHKEY: ${TS_AUTHKEY:?set TS_AUTHKEY in .env}\n"
    )
    dockerfile_path.write_text("RUN mkdir -p /data/home /data/bin\n")

    install._prepare_pithagoras_for_windows(pithagoras_dir, report, platform="nt")
    first_compose = compose_path.read_text()
    first_dockerfile = dockerfile_path.read_text()
    install._prepare_pithagoras_for_windows(pithagoras_dir, report, platform="nt")

    assert '127.0.0.1:${PORT:-4100}:${PORT:-4100}' in first_compose
    assert "network_mode: host" not in first_compose
    assert "TS_AUTHKEY: ${TS_AUTHKEY:-}" in first_compose
    assert "chown -R node:node /data" in first_dockerfile
    assert compose_path.read_text() == first_compose
    assert dockerfile_path.read_text() == first_dockerfile


def test_write_local_model_config_is_idempotent(report, tmp_path):
    agent_dir = tmp_path / "agent"
    model_path = tmp_path / "model.gguf"

    install._write_local_model_config(
        agent_dir, model_path, 8080, report, platform="nt"
    )
    first = (agent_dir / "models.json").read_text()
    install._write_local_model_config(
        agent_dir, model_path, 8080, report, platform="nt"
    )

    parsed = json.loads(first)
    provider = parsed["providers"]["local-llm"]
    assert provider["baseUrl"] == "http://host.docker.internal:8080/v1"
    assert provider["models"][0]["id"] == str(model_path)
    assert (agent_dir / "models.json").read_text() == first


async def test_setup_pithagoras_clones_and_generates_env(monkeypatch, cfg, report, tmp_path):
    pithagoras_dir = tmp_path / "pithagoras"
    cfg = _with_pithagoras_dir(cfg, pithagoras_dir)
    cfg = dataclasses.replace(
        cfg,
        install=dataclasses.replace(cfg.install, workspaces_dir=tmp_path, pi_agent_dir=tmp_path / "pi"),
    )
    fake, calls = _recording_run()

    async def fake_run_and_write_example(*args, **kwargs):
        # git clone no crea archivos de verdad acá — simulamos que el clone
        # dejó un .env.example, como pasaría con el repo real.
        pithagoras_dir.mkdir(parents=True, exist_ok=True)
        (pithagoras_dir / ".env.example").write_text("PORTAL_PASSWORD=changeme\n")
        calls.append(list(args[0]))
        return 0

    monkeypatch.setattr(install, "_run", fake_run_and_write_example)

    await install.phase_install_setup_pithagoras(cfg, report)

    env_path = pithagoras_dir / ".env"
    assert env_path.exists()
    content = env_path.read_text()
    assert "PORTAL_PASSWORD=" in content
    assert "PORTAL_PASSWORD=changeme" not in content
    assert f"WORKSPACES_DIR={tmp_path}" in content


async def test_setup_pithagoras_skips_env_when_already_exists(cfg, report, tmp_path):
    pithagoras_dir = tmp_path / "pithagoras"
    (pithagoras_dir / ".git").mkdir(parents=True)
    (pithagoras_dir / ".env").write_text("EXISTING=1\n")
    cfg = _with_pithagoras_dir(cfg, pithagoras_dir)

    await install.phase_install_setup_pithagoras(cfg, report)

    content = (pithagoras_dir / ".env").read_text()
    assert "EXISTING=1" in content
    if os.name == "nt":
        assert f"LLAMA_BASE_URL=http://host.docker.internal:{cfg.llama.port}" in content
        assert "PI_PROVIDER=local-llm" in content
        assert f"PI_MODEL={cfg.llama.model}" in content
    assert any("conservo sus secretos" in msg for msg in report.warnings)


async def test_setup_pithagoras_raises_when_example_missing(cfg, report, tmp_path):
    pithagoras_dir = tmp_path / "pithagoras"
    (pithagoras_dir / ".git").mkdir(parents=True)
    cfg = _with_pithagoras_dir(cfg, pithagoras_dir)

    try:
        await install.phase_install_setup_pithagoras(cfg, report)
        raised = False
    except PhaseError:
        raised = True
    assert raised


# ── SETUP UNDERSTORY ──────────────────────────────────────────────


async def test_setup_understory_raises_when_token_missing(cfg, report, tmp_path):
    cfg = _with_understory_dir(cfg, tmp_path / "understory")
    cfg = _with_pithagoras_dir(cfg, tmp_path / "pithagoras")
    try:
        await install.phase_install_setup_understory(cfg, report)
        raised = False
    except PhaseError:
        raised = True
    assert raised


async def test_setup_understory_generates_env_and_bundle(cfg, report, tmp_path):
    pithagoras_dir = tmp_path / "pithagoras"
    pithagoras_dir.mkdir(parents=True)
    (pithagoras_dir / ".env").write_text("UNDERSTORY_TOKEN=abc123\n")
    understory_dir = tmp_path / "understory"
    cfg = _with_understory_dir(cfg, understory_dir)
    cfg = _with_pithagoras_dir(cfg, pithagoras_dir)

    await install.phase_install_setup_understory(cfg, report)

    assert (understory_dir / "docker-compose.yml").exists()
    assert (understory_dir / ".env").read_text() == "AUTH_TOKEN=abc123\n"
    assert (understory_dir / "bundle" / "agents" / "index.md").exists()
    assert (understory_dir / "bundle" / "index.md").exists()
