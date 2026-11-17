"""Fases de INSTALL del portal, Understory y los secretos de la Instance —
idempotencia (reruns seguros, omiten lo que ya existe) y generación de .env a
partir de .env.example. Corren sobre el ``Host`` de dobles con ``tmp_path``
real: ningún comando real, ningún parche."""

import json
import stat
from pathlib import Path

import pytest
from dotenv import dotenv_values

from rinthel_tui import database
from rinthel_tui.identity import tokens
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle import install, install_tasks
from rinthel_tui.lifecycle.domain.errors import PhaseError
from tests.lifecycle.fakes import RunCall, fake_host


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    # El entorno de quien corre los tests no debe elegir perfil ni token.
    monkeypatch.delenv("COMPOSE_FILE", raising=False)
    monkeypatch.delenv("RINTHEL_HOSTEXECD_TOKEN", raising=False)


@pytest.fixture
def host():
    host, _ = fake_host()
    host.runner.succeed_by_default()
    return host


@pytest.fixture
def portal(cfg, tmp_path):
    return install_tasks.PortalInstall(
        instance=cfg.instance,
        dir=tmp_path / "pithagoras",
        repo_url="https://example.test/portal.git",
        branch=install_tasks.PORTAL_BRANCH,
        workspaces_dir=tmp_path / "workspaces",
        pi_agent_dir=tmp_path / "pi",
        llama_port=8080,
        llama_model=tmp_path / "model.gguf",
    )


def _clone_leaves_an_example(call: RunCall) -> None:
    dest = call.cmd[-1]
    Path(dest).mkdir(parents=True, exist_ok=True)
    (Path(dest) / ".env.example").write_text("PORTAL_PASSWORD=changeme\n")


# ── PORTAL ─────────────────────────────────────────────────────────


async def test_setup_portal_clones_and_generates_env(host, report, portal):
    host.runner.on_success("git", _clone_leaves_an_example)

    await install.phase_install_setup_portal(host, report, task=portal)

    (clone,) = host.runner.ran("git")
    assert {portal.repo_url, portal.branch, str(portal.dir)} <= set(clone.cmd)
    content = (portal.dir / ".env").read_text()
    assert "PORTAL_PASSWORD=" in content and "PORTAL_PASSWORD=changeme" not in content
    assert f"WORKSPACES_DIR={portal.workspaces_dir}" in content
    assert "LLAMA_BASE_URL=http://127.0.0.1:8080" in content


async def test_setup_portal_skips_clone_and_env_when_they_already_exist(host, report, portal):
    (portal.dir / ".git").mkdir(parents=True)
    (portal.dir / ".env").write_text("EXISTING=1\n")

    await install.phase_install_setup_portal(host, report, task=portal)

    assert host.runner.calls == []
    assert "EXISTING=1" in (portal.dir / ".env").read_text()
    assert any("conservo sus secretos" in msg for msg in report.warnings)


async def test_setup_portal_on_windows_points_pi_at_the_host_llama_server(host, report, portal):
    host.host_info.os = "windows"
    (portal.dir / ".git").mkdir(parents=True)
    (portal.dir / ".env").write_text("EXISTING=1\n")

    await install.phase_install_setup_portal(host, report, task=portal)

    content = (portal.dir / ".env").read_text()
    assert "LLAMA_BASE_URL=http://host.docker.internal:8080" in content
    assert "PI_PROVIDER=local-llm" in content
    assert f"PI_MODEL={portal.llama_model}" in content
    assert json.loads((portal.pi_agent_dir / "models.json").read_text())["providers"]["local-llm"]


async def test_setup_portal_provisions_one_host_exec_token(host, report, portal, cfg):
    portal.dir.mkdir()
    (portal.dir / ".env.example").write_text("PORTAL_PASSWORD=changeme\n")

    await install.phase_install_setup_portal(host, report, task=portal)

    root_token = dotenv_values(cfg.instance.env_path).get("RINTHEL_HOSTEXECD_TOKEN")
    assert root_token and len(root_token) >= 64
    assert dotenv_values(portal.dir / ".env")["RINTHEL_HOSTEXECD_TOKEN"] == root_token
    await install.phase_install_setup_portal(host, report, task=portal)
    assert dotenv_values(cfg.instance.env_path)["RINTHEL_HOSTEXECD_TOKEN"] == root_token


async def test_setup_portal_preserves_existing_host_exec_secret(host, report, portal, cfg):
    portal.dir.mkdir()
    (portal.dir / ".env").write_text("PORTAL_PASSWORD=keep-me\nRINTHEL_HOSTEXECD_TOKEN=existing-token\n")

    await install.phase_install_setup_portal(host, report, task=portal)

    assert dotenv_values(cfg.instance.env_path)["RINTHEL_HOSTEXECD_TOKEN"] == "existing-token"
    assert dotenv_values(portal.dir / ".env")["PORTAL_PASSWORD"] == "keep-me"


async def test_setup_portal_rejects_conflicting_host_exec_secrets(host, report, portal, cfg):
    portal.dir.mkdir()
    cfg.instance.env_path.write_text("RINTHEL_HOSTEXECD_TOKEN=root-secret\n")
    (portal.dir / ".env").write_text("RINTHEL_HOSTEXECD_TOKEN=portal-secret\n")

    with pytest.raises(PhaseError):
        await install.phase_install_setup_portal(host, report, task=portal)

    assert dotenv_values(cfg.instance.env_path)["RINTHEL_HOSTEXECD_TOKEN"] == "root-secret"
    assert dotenv_values(portal.dir / ".env")["RINTHEL_HOSTEXECD_TOKEN"] == "portal-secret"


async def test_setup_portal_raises_when_example_missing(host, report, portal):
    (portal.dir / ".git").mkdir(parents=True)

    with pytest.raises(PhaseError):
        await install.phase_install_setup_portal(host, report, task=portal)


def test_prepare_portal_for_windows_is_idempotent(report, tmp_path):
    portal_dir = tmp_path / "pithagoras"
    portal_dir.mkdir()
    compose_path = portal_dir / "docker-compose.yml"
    dockerfile_path = portal_dir / "Dockerfile"
    compose_path.write_text(
        "services:\n"
        "  portal:\n"
        "    network_mode: host\n"
        "  tailscale:\n"
        "    environment:\n"
        "      TS_AUTHKEY: ${TS_AUTHKEY:?set TS_AUTHKEY in .env}\n"
    )
    dockerfile_path.write_text("RUN mkdir -p /data/home /data/bin\n")

    install.prepare_portal_for_windows(portal_dir, report)
    first_compose = compose_path.read_text()
    first_dockerfile = dockerfile_path.read_text()
    install.prepare_portal_for_windows(portal_dir, report)

    assert "127.0.0.1:${PORT:-4100}:${PORT:-4100}" in first_compose
    assert "network_mode: host" not in first_compose
    assert "TS_AUTHKEY: ${TS_AUTHKEY:-}" in first_compose
    assert "chown -R node:node /data" in first_dockerfile
    assert compose_path.read_text() == first_compose
    assert dockerfile_path.read_text() == first_dockerfile


def test_write_local_model_config_is_idempotent(report, tmp_path):
    agent_dir = tmp_path / "agent"
    model_path = tmp_path / "model.gguf"

    install.write_local_model_config(agent_dir, model_path, 8080, report)
    first = (agent_dir / "models.json").read_text()
    install.write_local_model_config(agent_dir, model_path, 8080, report)

    provider = json.loads(first)["providers"]["local-llm"]
    assert provider["baseUrl"] == "http://host.docker.internal:8080/v1"
    assert provider["models"][0]["id"] == str(model_path)
    assert (agent_dir / "models.json").read_text() == first


# ── UNDERSTORY ──────────────────────────────────────────────────────


def _understory(cfg, tmp_path):
    return install_tasks.UnderstoryInstall(cfg.instance, tmp_path / "understory", tmp_path / "pithagoras" / ".env")


async def test_setup_understory_raises_when_token_missing(host, report, cfg, tmp_path):
    with pytest.raises(PhaseError):
        await install.phase_install_setup_understory(host, report, task=_understory(cfg, tmp_path))


async def test_setup_understory_generates_env_and_bundle(host, report, cfg, tmp_path):
    task = _understory(cfg, tmp_path)
    task.portal_env.parent.mkdir(parents=True)
    task.portal_env.write_text("UNDERSTORY_TOKEN=abc123\n")

    await install.phase_install_setup_understory(host, report, task=task)

    assert (task.dir / "docker-compose.yml").exists()
    assert (task.dir / ".env").read_text() == "AUTH_TOKEN=abc123\n"
    assert (task.dir / "bundle" / "agents" / "index.md").exists()
    assert (task.dir / "bundle" / "index.md").exists()


# ── el perfil Ubuntu ────────────────────────────────────────────────


@pytest.mark.parametrize("phase", ["portal", "understory"])
async def test_the_ubuntu_profile_prepares_the_monorepo_from_the_instance_env(
    host, report, cfg, tmp_path, portal, monkeypatch, phase
):
    from rinthel_tui.install import ubuntu

    cfg.instance.env_path.write_text("COMPOSE_FILE=docker-compose.ubuntu.yml\n")
    calls = []
    monkeypatch.setattr(ubuntu, "prepare", calls.append)

    if phase == "portal":
        await install.phase_install_setup_portal(host, report, task=portal)
    else:
        await install.phase_install_setup_understory(host, report, task=_understory(cfg, tmp_path))

    assert calls == [cfg.instance.root]


# ── SECRETOS DE LA INSTANCE ─────────────────────────────────────────


async def test_instance_secrets_are_generated_in_the_root_env(host, report, tmp_path):
    instance = Instance(tmp_path)
    instance.env_example_path.write_text("RINTHEL_SERVICE_SECRET=\nRINTHEL_PANEL_SECRET=\n")

    await install.phase_install_instance_secrets(host, report, task=install_tasks.InstanceSecrets(instance))

    assert len(instance.get("RINTHEL_SERVICE_SECRET")) == 64
    assert len(instance.get("RINTHEL_PANEL_SECRET")) == 64
    assert stat.S_IMODE(instance.env_path.stat().st_mode) == 0o600


async def test_instance_secrets_skip_what_is_already_set(host, report, tmp_path):
    instance = Instance(tmp_path)
    instance.env_path.write_text("RINTHEL_SERVICE_SECRET=keep\n")

    await install.phase_install_instance_secrets(host, report, task=install_tasks.InstanceSecrets(instance))

    assert instance.get("RINTHEL_SERVICE_SECRET") == "keep"
    assert instance.get("RINTHEL_PANEL_SECRET")
    assert len(report.warnings) == 1


async def test_instance_secrets_raise_when_neither_env_nor_example_exist(host, report, tmp_path):
    with pytest.raises(PhaseError):
        await install.phase_install_instance_secrets(
            host, report, task=install_tasks.InstanceSecrets(Instance(tmp_path))
        )


# ── IDENTITY ───────────────────────────────────────────────────────


async def test_identity_creates_rinthel_db_and_shows_the_first_admin_password_once(host, report, tmp_path):
    instance = Instance(tmp_path)

    await install.phase_install_identity(host, report, task=install_tasks.IdentitySetup(instance.database_path))

    user = SqliteIdentity(instance.database_path).get_user_by_username("admin")
    assert user.is_active_admin
    shown = [w for m in report.successes for w in m.split() if tokens.verify_password(w, user.password_hash)]
    assert len(shown) == 1


async def test_identity_with_an_active_admin_changes_nothing(host, report, tmp_path):
    task = install_tasks.IdentitySetup(Instance(tmp_path).database_path)
    await install.phase_install_identity(host, report, task=task)
    before = SqliteIdentity(task.database_path).list_users()

    await install.phase_install_identity(host, report, task=task)

    assert SqliteIdentity(task.database_path).list_users() == before
    assert any("admin activo" in w for w in report.warnings)


async def test_identity_stops_on_a_newer_schema(host, report, tmp_path):
    path = Instance(tmp_path).database_path
    database.migrate(path, migrations=(*database.MIGRATIONS, "SELECT 1;"))

    with pytest.raises(PhaseError):
        await install.phase_install_identity(host, report, task=install_tasks.IdentitySetup(path))

    assert any("schema version" in e for e in report.errors)
