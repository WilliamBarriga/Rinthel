"""Cada boot del daemon abre con una línea de inicio (fecha ISO + PID + código)
antes de armar la app, para separar boots en un ``daemon.log`` que se anexa."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import rinthel_tui.daemon


class _Stop(Exception):
    pass


def _no_app(*args, **kwargs):
    raise _Stop


def test_startup_line_has_iso_date_pid_and_code_version() -> None:
    now = datetime(2026, 10, 22, 14, 3, 11, tzinfo=timezone(timedelta(hours=-5)))
    line = rinthel_tui.daemon.startup_line(now, 1234, "abc123def456")
    assert line == "[daemon] inicio 2026-10-22T14:03:11-05:00 pid=1234 codigo=abc123def456"
    assert "traceback" not in line.lower()


def test_run_prints_marker_before_building_the_app(cfg, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(_Stop):
        rinthel_tui.daemon.run(cfg.instance, cfg, create_app=_no_app)
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("[daemon] inicio ")
    assert " pid=" in first


def test_run_warns_when_the_service_secret_is_missing(cfg, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(_Stop):
        rinthel_tui.daemon.run(cfg.instance, cfg, create_app=_no_app)
    assert "RINTHEL_SERVICE_SECRET" in capsys.readouterr().err
