"""``phase_ensure_data_dir``: el directorio que compose monta en un
contenedor que no corre como root tiene que existir, con el dueño de ese
contenedor, antes del ``up``. Corre contra un ``Host`` de dobles."""

from pathlib import Path

import pytest

from rinthel_tui.lifecycle.domain.errors import DataDirError, PhaseError
from rinthel_tui.lifecycle.domain.phases import data_dir as phases
from tests.lifecycle.fakes import fake_host

DECK_DATA = Path("/instance/data/deck")


async def test_a_missing_directory_is_created_for_the_container_user(report):
    host, _ = fake_host()

    await phases.phase_ensure_data_dir(host, report, path=DECK_DATA, uid=1000, gid=1000)

    assert host.data_dirs.owner_of(DECK_DATA) == (1000, 1000)
    assert report.errors == []


async def test_a_directory_with_the_right_owner_is_left_alone(report):
    host, _ = fake_host()
    host.data_dirs.create(DECK_DATA, uid=1000, gid=1000)

    await phases.phase_ensure_data_dir(host, report, path=DECK_DATA, uid=1000, gid=1000)

    assert report.errors == []


async def test_a_directory_owned_by_someone_else_fails_with_the_fix(report):
    host, _ = fake_host()
    host.data_dirs.create(DECK_DATA, uid=0, gid=0)

    with pytest.raises(PhaseError):
        await phases.phase_ensure_data_dir(host, report, path=DECK_DATA, uid=1000, gid=1000)

    [message] = report.errors
    assert "0:0" in message and "1000:1000" in message and f"chown -R 1000:1000 {DECK_DATA}" in message
    assert host.data_dirs.owner_of(DECK_DATA) == (0, 0)  # no lo toca


async def test_a_directory_that_cannot_be_created_fails_with_the_reason(report):
    host, _ = fake_host()
    host.data_dirs.fail_next("ensure", DataDirError("Permission denied"))

    with pytest.raises(PhaseError):
        await phases.phase_ensure_data_dir(host, report, path=DECK_DATA, uid=1000, gid=1000)

    [message] = report.errors
    assert "Permission denied" in message
