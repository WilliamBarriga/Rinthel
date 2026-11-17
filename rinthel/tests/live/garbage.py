"""What a live run must not leave behind, and how it is cleaned: run roots
``/tmp/rinthel-live-*`` and containers ``rinthel-live-*``. Nothing else is
ever matched: not the real Instance's data, not its containers.

Every kind of leftover is a ``Resource`` (list, recognise what is ours,
remove). ``find_garbage`` and ``sweep`` walk the same list, and ``sweep``
removes a name only if its own matcher accepts it, whatever the lister
returned. It runs only with ``--sweep-leftovers``: it recognises by prefix,
not by run, so it would also take a parallel run's leftovers."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

TMP_ROOT = Path("/tmp")
TMP_PREFIX = "rinthel-live-"
CONTAINER_PREFIX = "rinthel-live-"


def is_live_directory(path: Path, *, root: Path = TMP_ROOT) -> bool:
    """A real directory (not a symlink) that is a direct child of ``root``
    named ``rinthel-live-<something>``."""
    return (
        path.parent == root
        and path.name.startswith(TMP_PREFIX)
        and len(path.name) > len(TMP_PREFIX)
        and not path.is_symlink()
        and path.is_dir()
    )


def is_live_container(name: str) -> bool:
    return name.startswith(CONTAINER_PREFIX) and len(name) > len(CONTAINER_PREFIX)


@dataclass(frozen=True)
class Resource:
    """A kind of leftover. ``names`` lists everything there is, ``ours``
    recognises what the live runs created and ``remove`` deletes it."""

    label: str
    names: Callable[[], list[str]]
    ours: Callable[[str], bool]
    remove: Callable[[str], None]

    def leftovers(self) -> list[str]:
        return [name for name in self.names() if self.ours(name)]


def tmp_directories(root: Path = TMP_ROOT) -> Resource:
    def names() -> list[str]:
        return [str(path) for path in root.glob(f"{TMP_PREFIX}*")]

    def remove(name: str) -> None:
        shutil.rmtree(name, ignore_errors=True)

    return Resource("directory", names, lambda name: is_live_directory(Path(name), root=root), remove)


def _docker_names() -> list[str]:
    try:
        out = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return out.stdout.split()


def _docker_remove(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False, timeout=60)


def docker_containers(
    names: Callable[[], list[str]] = _docker_names, remove: Callable[[str], None] = _docker_remove
) -> Resource:
    return Resource("container", names, is_live_container, remove)


def live_resources() -> list[Resource]:
    return [tmp_directories(), docker_containers()]


def find_garbage(resources: Sequence[Resource]) -> list[str]:
    return [f"{r.label}: {name}" for r in resources for name in r.leftovers()]


def sweep(resources: Sequence[Resource]) -> list[str]:
    """Removes the leftovers of dead runs and returns what it removed."""
    removed = []
    for r in resources:
        for name in r.leftovers():
            r.remove(name)
            removed.append(f"{r.label}: {name}")
    return removed
