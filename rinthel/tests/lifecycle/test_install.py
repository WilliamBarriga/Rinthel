"""Fases de INSTALL de Understory, los contenedores y los secretos de la Instance —
idempotencia (reruns seguros, omiten lo que ya existe) y generación de .env a
partir de .env.example. Corren sobre el ``Host`` de dobles con ``tmp_path``
real: ningún comando real, ningún parche."""

import stat

import pytest
from dotenv import dotenv_values

from rinthel_tui import database
from rinthel_tui.identity import tokens
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle import install, install_tasks
from rinthel_tui.lifecycle.domain.errors import PhaseError
from tests.lifecycle.fakes import fake_host


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    # El entorno de quien corre los tests no debe elegir token.
    monkeypatch.delenv("RINTHEL_HOSTEXECD_TOKEN", raising=False)


@pytest.fixture
def host():
    host, _ = fake_host()
    host.runner.succeed_by_default()
    return host


# ── UNDERSTORY ──────────────────────────────────────────────────────


def _understory(cfg):
    return install_tasks.understory_install(cfg)


async def test_setup_understory_generates_one_token_in_the_root_env_and_the_bundle(host, report, cfg):
    task = _understory(cfg)

    await install.phase_install_setup_understory(host, report, task=task)

    env = dotenv_values(cfg.instance.env_path)
    assert len(env["UNDERSTORY_TOKEN"]) >= 48
    # The root compose hands it to Understory as its AUTH_TOKEN: one source.
    assert "AUTH_TOKEN" not in env
    bundle = cfg.instance.data_dir / "understory"
    assert task.bundle_dir == bundle
    assert (bundle / "agents" / "index.md").exists()
    assert (bundle / "index.md").exists() and (bundle / "log.md").exists()
    assert not (cfg.instance.understory_dir / ".env").exists()
    assert stat.S_IMODE(cfg.instance.env_path.stat().st_mode) == 0o600


async def test_setup_understory_keeps_an_existing_token(host, report, cfg):
    cfg.instance.env_path.write_text("UNDERSTORY_TOKEN=keep-me\n")

    await install.phase_install_setup_understory(host, report, task=_understory(cfg))
    await install.phase_install_setup_understory(host, report, task=_understory(cfg))

    env = dotenv_values(cfg.instance.env_path)
    assert env["UNDERSTORY_TOKEN"] == "keep-me"
    assert "AUTH_TOKEN" not in env


async def test_setup_understory_never_overwrites_the_bundle(host, report, cfg):
    index = cfg.instance.data_dir / "understory" / "index.md"
    index.parent.mkdir(parents=True)
    index.write_text("# mine\n")

    await install.phase_install_setup_understory(host, report, task=_understory(cfg))

    assert index.read_text() == "# mine\n"


# ── CONTENEDORES: usuario y grupo de docker en Linux ─────────────────


async def test_container_user_writes_the_host_ids_and_the_docker_group_on_linux(host, report, cfg):
    host.host_info.ids = (1234, 5678)
    host.host_info.groups = {"docker": 999}

    await install.phase_install_container_user(host, report, task=install_tasks.container_user(cfg))

    env = dotenv_values(cfg.instance.env_path)
    assert (env["PUID"], env["PGID"], env["DOCKER_GID"]) == ("1234", "5678", "999")


async def test_container_user_keeps_what_the_admin_set(host, report, cfg):
    host.host_info.ids = (1234, 5678)
    host.host_info.groups = {"docker": 999}
    cfg.instance.env_path.write_text("PUID=1\nPGID=2\nDOCKER_GID=3\n")

    await install.phase_install_container_user(host, report, task=install_tasks.container_user(cfg))

    env = dotenv_values(cfg.instance.env_path)
    assert (env["PUID"], env["PGID"], env["DOCKER_GID"]) == ("1", "2", "3")


async def test_container_user_without_a_docker_group_warns_and_leaves_it_unset(host, report, cfg):
    host.host_info.ids = (1234, 5678)

    await install.phase_install_container_user(host, report, task=install_tasks.container_user(cfg))

    env = dotenv_values(cfg.instance.env_path)
    assert env["PUID"] == "1234" and "DOCKER_GID" not in env
    assert any("docker" in w for w in report.warnings)


async def test_container_user_does_nothing_on_windows(host, report, cfg):
    host.host_info.os = "windows"

    await install.phase_install_container_user(host, report, task=install_tasks.container_user(cfg))

    assert not cfg.instance.env_path.exists()


# ── COMPOSE DE LA PLATFORM: el override de Windows por COMPOSE_FILE ─────


async def test_platform_compose_picks_the_windows_override_on_windows(host, report, cfg):
    host.host_info.os = "windows"

    await install.phase_install_platform_compose(host, report, task=install_tasks.container_user(cfg))

    env = dotenv_values(cfg.instance.env_path)
    assert env["COMPOSE_FILE"] == "docker-compose.yaml;compose/windows.override.yaml"
    assert env["COMPOSE_PATH_SEPARATOR"] == ";"


async def test_platform_compose_leaves_linux_on_the_root_compose_alone(host, report, cfg):
    await install.phase_install_platform_compose(host, report, task=install_tasks.container_user(cfg))

    assert not cfg.instance.env_path.exists()


async def test_platform_compose_keeps_what_the_admin_set(host, report, cfg):
    host.host_info.os = "windows"
    cfg.instance.env_path.write_text("COMPOSE_FILE=mine.yaml\n")

    await install.phase_install_platform_compose(host, report, task=install_tasks.container_user(cfg))

    env = dotenv_values(cfg.instance.env_path)
    assert env["COMPOSE_FILE"] == "mine.yaml" and "COMPOSE_PATH_SEPARATOR" not in env
    assert any("COMPOSE_FILE" in w for w in report.warnings)


def test_the_instance_unit_sets_the_platform_compose():
    assert install.phase_install_platform_compose in [step.fn for step in install.SECRETS_INSTALL.steps]


# ── HOST EXEC: el token compartido vive en el .env raíz ───────────────


async def test_host_exec_token_is_generated_once_in_the_root_env(host, report, cfg):
    await install.phase_install_host_exec_token(host, report, task=install_tasks.instance_secrets(cfg))
    token = dotenv_values(cfg.instance.env_path)["RINTHEL_HOSTEXECD_TOKEN"]
    await install.phase_install_host_exec_token(host, report, task=install_tasks.instance_secrets(cfg))

    assert len(token) >= 64
    assert dotenv_values(cfg.instance.env_path)["RINTHEL_HOSTEXECD_TOKEN"] == token


async def test_host_exec_token_is_skipped_on_windows_where_hostexecd_does_not_run(host, report, cfg):
    host.host_info.os = "windows"

    await install.phase_install_host_exec_token(host, report, task=install_tasks.instance_secrets(cfg))

    assert not cfg.instance.env_path.exists()
    assert report.warnings


async def test_host_exec_token_conflicting_with_the_shell_fails(host, report, cfg, monkeypatch):
    cfg.instance.env_path.write_text("RINTHEL_HOSTEXECD_TOKEN=root-secret\n")
    monkeypatch.setenv("RINTHEL_HOSTEXECD_TOKEN", "shell-secret")

    with pytest.raises(PhaseError):
        await install.phase_install_host_exec_token(host, report, task=install_tasks.instance_secrets(cfg))

    assert dotenv_values(cfg.instance.env_path)["RINTHEL_HOSTEXECD_TOKEN"] == "root-secret"


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


# ── INSTANCE SOUL ──────────────────────────────────────────────────


async def test_instance_soul_is_seeded_from_the_template_where_deck_reads_it(host, report, cfg):
    task = install_tasks.instance_soul(cfg)

    await install.phase_install_instance_soul(host, report, task=task)

    assert task.path == cfg.instance.deck_data_dir / "instance" / "SOUL.md"
    seeded = task.path.read_text()
    assert seeded.startswith("# SOUL.md")
    assert "This file is your identity" in seeded
    assert seeded.endswith("\n")


async def test_instance_soul_already_there_is_never_overwritten(host, report, tmp_path):
    task = install_tasks.InstanceSoulSeed(tmp_path / "instance" / "SOUL.md")
    task.path.parent.mkdir(parents=True)
    task.path.write_text("# mine\n")

    await install.phase_install_instance_soul(host, report, task=task)

    assert task.path.read_text() == "# mine\n"
    assert any("ya existe" in w for w in report.warnings)


def test_instance_soul_install_unit_runs_only_while_deck_is_enabled(cfg):
    unit = next(u for u in install.INSTALL_UNITS if u.label == "DECK")

    assert unit.enabled_of(cfg) is cfg.deck.enabled
    assert [step.fn for step in unit.steps] == [install.phase_install_instance_soul]


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
