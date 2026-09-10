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
import re
import shutil

from rinthel_tui.lifecycle import install, specs
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

    assert (pithagoras_dir / ".env").read_text() == "EXISTING=1\n"
    assert any("no lo piso" in msg for msg in report.warnings)


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


# ── INSTALL_UNITS / specs.install_phases ─────────────────────────────


def _numbers(phase_specs):
    out = []
    for spec in phase_specs:
        match = re.search(r"\[(\d+)/(\d+)\]", spec.label)
        assert match is not None
        out.append((int(match.group(1)), int(match.group(2))))
    return out


def test_install_phases_includes_all_units_by_default(cfg):
    labels = [s.label for s in specs.install_phases(cfg)]
    assert any("PREFLIGHT" in l for l in labels)
    assert any("LLAMA.CPP — clone" in l for l in labels)
    assert any("LLAMA.CPP — build CUDA" in l for l in labels)
    assert any("MODELO GGUF" in l for l in labels)
    assert any("PITHAGORAS" in l for l in labels)
    assert any("UNDERSTORY" in l for l in labels)
    numbers = _numbers(specs.install_phases(cfg))
    total = len(numbers)
    assert [n for n, _ in numbers] == list(range(1, total + 1))
    assert all(n_total == total for _, n_total in numbers)


def test_install_phases_excludes_disabled_unit_and_renumbers(cfg):
    disabled = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, enabled=False))
    phase_specs = specs.install_phases(disabled)
    labels = [s.label for s in phase_specs]
    assert not any("LLAMA.CPP" in l for l in labels)
    assert not any("MODELO GGUF" in l for l in labels)
    assert any("PREFLIGHT" in l for l in labels)
    assert any("PITHAGORAS" in l for l in labels)
    numbers = _numbers(phase_specs)
    total = len(numbers)
    assert [n for n, _ in numbers] == list(range(1, total + 1))


def test_install_phases_excludes_only_the_disabled_service(cfg):
    disabled = dataclasses.replace(cfg, pithagoras=dataclasses.replace(cfg.pithagoras, enabled=False))
    labels = [s.label for s in specs.install_phases(disabled)]
    assert not any("PITHAGORAS" in l for l in labels)
    assert any("LLAMA.CPP" in l for l in labels)
    assert any("UNDERSTORY" in l for l in labels)
