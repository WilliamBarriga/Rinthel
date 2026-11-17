"""The existing acquisition contract with real curl/hash adapters and doubles.

A file URL exercises download/publication in isolated files without a service.
"""

import dataclasses
import hashlib
from pathlib import Path

import pytest

from rinthel_tui.lifecycle import install
from rinthel_tui.lifecycle.adapters.asyncio_runner import AsyncioRunner
from rinthel_tui.lifecycle.adapters.host_info import SystemHostInfo
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.install_tasks import ModelDownload
from tests.lifecycle.fakes import fake_host


@pytest.fixture(params=["system", "fake"])
def acquisition_host(request):
    host, _ = fake_host()
    if request.param == "system":
        return dataclasses.replace(host, runner=AsyncioRunner(), host_info=SystemHostInfo())
    host.runner.succeed_by_default()

    def download(call):
        source = Path(call.cmd[-1].removeprefix("file://"))
        Path(call.cmd[call.cmd.index("-o") + 1]).write_bytes(source.read_bytes())

    host.runner.on_success("curl", download)
    return host


async def test_verified_download_is_atomic_and_idempotent(acquisition_host, tmp_path, report):
    source = tmp_path / "source"
    source.write_bytes(b"known artifact")
    dest = tmp_path / "models" / "custom.gguf"
    task = ModelDownload("Embeddings", source.as_uri(), dest, hashlib.sha256(b"known artifact").hexdigest())

    await install.phase_install_download(acquisition_host, report, task=task)
    source.unlink()
    await install.phase_install_download(acquisition_host, report, task=task)

    assert dest.read_bytes() == b"known artifact"
    assert list(dest.parent.iterdir()) == [dest]


async def test_corrupt_download_preserves_the_existing_file(acquisition_host, tmp_path, report):
    source = tmp_path / "source"
    source.write_bytes(b"corrupt")
    dest = tmp_path / "custom.gguf"
    dest.write_bytes(b"previous model")
    task = ModelDownload("Embeddings", source.as_uri(), dest, hashlib.sha256(b"known artifact").hexdigest())

    with pytest.raises(PhaseError, match="sha256"):
        await install.phase_install_download(acquisition_host, report, task=task)

    assert dest.read_bytes() == b"previous model"
    assert not dest.with_name(dest.name + ".part").exists()
