"""Suite de contrato del puerto ``DataDirs``: el adapter real sobre ``tmp_path``
(con el uid del que corre el test, el único al que puede dar un directorio sin
ser root) contra ``FakeDataDirs``."""

import os
from dataclasses import dataclass

import pytest

from rinthel_tui.lifecycle.adapters.data_dirs import SystemDataDirs
from rinthel_tui.lifecycle.domain.errors import DataDirError
from tests.lifecycle.fakes import FakeDataDirs


@dataclass
class World:
    dirs: object
    root: object
    uid: int
    gid: int


@pytest.fixture(params=["system", "fake"])
def world(request, tmp_path):
    if request.param == "system":
        return World(SystemDataDirs(), tmp_path, os.getuid(), os.getgid())
    return World(FakeDataDirs(), tmp_path, 1000, 1000)


def test_a_missing_directory_is_created_with_its_parents_for_the_user(world):
    path = world.root / "data" / "deck"

    owner = world.dirs.ensure(path, uid=world.uid, gid=world.gid)

    assert owner == (world.uid, world.gid)


def test_an_existing_directory_keeps_its_owner_and_its_content(world):
    path = world.root / "deck"
    world.dirs.ensure(path, uid=world.uid, gid=world.gid)
    if isinstance(world.dirs, SystemDataDirs):
        (path / "sessions").mkdir()

    again = world.dirs.ensure(path, uid=world.uid + 1, gid=world.gid + 1)

    assert again == (world.uid, world.gid)
    if isinstance(world.dirs, SystemDataDirs):
        assert (path / "sessions").is_dir()


def test_a_directory_that_cannot_be_created_raises_the_domain_error(world):
    if isinstance(world.dirs, SystemDataDirs):
        blocker = world.root / "a-file"
        blocker.write_text("")
        path = blocker / "deck"
    else:
        path = world.root / "deck"
        world.dirs.fail_next("ensure", DataDirError("nope"))

    with pytest.raises(DataDirError):
        world.dirs.ensure(path, uid=world.uid, gid=world.gid)
