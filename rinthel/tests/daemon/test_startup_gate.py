"""Startup gate of ``rinthel.db``: ``daemon.run`` migrates it before building
the app, stops with a clear error on a schema newer than the code, and warns
when there is no active admin."""

import pytest

import rinthel_tui.daemon
from rinthel_tui import database
from rinthel_tui.identity.adapters.sqlite import SqliteIdentity


class _Built(Exception):
    pass


def _no_app(*args, **kwargs):
    raise _Built


def test_startup_migrates_rinthel_db_before_building_the_app(cfg):
    with pytest.raises(_Built):
        rinthel_tui.daemon.run(cfg.instance, cfg, create_app=_no_app)

    assert SqliteIdentity(cfg.instance.database_path).list_users() == []


def test_startup_without_an_active_admin_warns_to_run_reset_admin(cfg, capsys):
    with pytest.raises(_Built):
        rinthel_tui.daemon.run(cfg.instance, cfg, create_app=_no_app)

    assert "sin admin activo: corré reset-admin" in capsys.readouterr().err


def test_startup_with_an_active_admin_does_not_warn(cfg, capsys):
    database.migrate(cfg.instance.database_path)
    SqliteIdentity(cfg.instance.database_path).create_user(username="admin", password_hash="h", role="admin")

    with pytest.raises(_Built):
        rinthel_tui.daemon.run(cfg.instance, cfg, create_app=_no_app)

    assert "reset-admin" not in capsys.readouterr().err


def test_a_schema_newer_than_the_code_stops_startup_with_a_clear_error(cfg, capsys):
    database.migrate(cfg.instance.database_path, migrations=(*database.MIGRATIONS, "SELECT 1;"))

    with pytest.raises(SystemExit) as stopped:
        rinthel_tui.daemon.run(cfg.instance, cfg, create_app=_no_app)

    assert stopped.value.code == 1
    assert "schema version" in capsys.readouterr().err
