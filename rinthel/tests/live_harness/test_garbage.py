"""The garbage sweep of the live suite: what a run must not leave behind and
how it is cleaned. The matchers are the safety net, so they are pinned here
with hostile names; nothing in this file touches ``/tmp`` or Docker for real
(directories live under ``tmp_path``, Docker is a recording double)."""

import os

from tests.live.garbage import (
    CONTAINER_PREFIX,
    TMP_ROOT,
    TMP_PREFIX,
    docker_containers,
    find_garbage,
    is_live_container,
    is_live_directory,
    sweep,
    tmp_directories,
)


def test_the_harness_directory_prefix_lives_under_slash_tmp():
    assert TMP_ROOT.as_posix() == "/tmp"
    assert TMP_PREFIX == "rinthel-live-"
    assert CONTAINER_PREFIX == "rinthel-live-"


def test_only_direct_children_of_the_root_with_the_prefix_are_live_directories(tmp_path):
    (tmp_path / "rinthel-live-abc").mkdir()
    (tmp_path / "rinthel-live").mkdir()
    (tmp_path / "rinthel-liveabc").mkdir()
    (tmp_path / "x-rinthel-live-abc").mkdir()
    (tmp_path / "other" / "rinthel-live-abc").mkdir(parents=True)
    (tmp_path / "rinthel-live-file").write_text("a file, not a run root")

    assert is_live_directory(tmp_path / "rinthel-live-abc", root=tmp_path)
    for hostile in (
        tmp_path / "rinthel-live",
        tmp_path / "rinthel-liveabc",
        tmp_path / "x-rinthel-live-abc",
        tmp_path / "other" / "rinthel-live-abc",
        tmp_path / "rinthel-live-file",
        tmp_path / "rinthel-live-abc" / "..",
        tmp_path / "rinthel-live-missing",
    ):
        assert not is_live_directory(hostile, root=tmp_path), hostile


def test_a_symlink_named_like_a_run_root_is_not_one(tmp_path):
    precious = tmp_path / "precious"
    precious.mkdir()
    link = tmp_path / "rinthel-live-link"
    os.symlink(precious, link)

    assert not is_live_directory(link, root=tmp_path)
    assert find_garbage([tmp_directories(tmp_path)]) == []


def test_only_containers_with_the_harness_prefix_are_live():
    assert is_live_container("rinthel-live-abc")
    for hostile in ("rinthel-llama-1", "rinthel-deck-1", "my-rinthel-live-abc", "rinthel-live", "", "portal-live-1"):
        assert not is_live_container(hostile), hostile


def test_a_clean_run_leaves_nothing(tmp_path):
    (tmp_path / "other-dir").mkdir()

    assert find_garbage([tmp_directories(tmp_path), docker_containers(lambda: ["rinthel-deck-1"])]) == []


def test_reports_each_kind_of_leftover(tmp_path):
    (tmp_path / "rinthel-live-abc").mkdir()

    garbage = find_garbage(
        [tmp_directories(tmp_path), docker_containers(lambda: ["rinthel-live-xyz", "rinthel-deck-1"])]
    )

    assert sorted(garbage) == [
        "container: rinthel-live-xyz",
        f"directory: {tmp_path / 'rinthel-live-abc'}",
    ]


def test_sweep_removes_only_matching_directories_and_containers(tmp_path):
    (tmp_path / "rinthel-live-abc").mkdir()
    (tmp_path / "rinthel-live-abc" / "daemon.log").write_text("x")
    (tmp_path / "keep-me").mkdir()
    removed_containers: list[str] = []
    containers = docker_containers(
        lambda: ["rinthel-live-xyz", "rinthel-deck-1", "qdrant"], remove=removed_containers.append
    )

    swept = sweep([tmp_directories(tmp_path), containers])

    assert not (tmp_path / "rinthel-live-abc").exists()
    assert (tmp_path / "keep-me").exists()
    assert removed_containers == ["rinthel-live-xyz"]
    assert sorted(swept) == ["container: rinthel-live-xyz", f"directory: {tmp_path / 'rinthel-live-abc'}"]


def test_sweep_never_removes_a_name_the_lister_returns_but_the_matcher_rejects(tmp_path):
    removed: list[str] = []
    containers = docker_containers(lambda: ["rinthel-deck-1", "rinthel-live"], remove=removed.append)

    assert sweep([containers]) == []
    assert removed == []
