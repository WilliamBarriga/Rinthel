"""``require_ok``: lo que toda phase hace con el resultado de un comando."""

import pytest

from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.domain.outcome import fail_on_error, require_ok
from rinthel_tui.lifecycle.domain.types import RunResult
from tests.lifecycle.fakes import FakeReport


def test_a_zero_exit_only_forwards_the_output():
    report = FakeReport()

    require_ok(report, RunResult(0, "hecho\n"), failed="falló", error="failed")

    assert report.infos == ["hecho"] and report.errors == []


def test_a_nonzero_exit_reports_the_failure_with_its_hint_and_stops_the_phase():
    report = FakeReport()

    with pytest.raises(PhaseError, match=r"failed \(rc 2\)"):
        require_ok(report, RunResult(2, "boom"), failed="falló", error="failed", hint=" — probá X")

    assert report.infos == ["boom"]
    assert report.errors == ["falló (rc 2) — probá X"]


def test_fail_on_error_does_not_repeat_the_output_the_caller_already_forwarded():
    report = FakeReport()

    with pytest.raises(PhaseError):
        fail_on_error(report, RunResult(1, "ya mostrada"), failed="falló", error="failed")

    assert report.infos == []
