"""Suite de contrato del puerto ``HostInfo``: el adapter real con un ``PATH``,
y una raíz de CUDA controlados (``tmp_path``) contra ``FakeHostInfo``."""

import hashlib
import stat
from dataclasses import dataclass

import pytest

from rinthel_tui.lifecycle.adapters.host_info import SystemHostInfo
from tests.lifecycle.fakes import FakeHostInfo


@dataclass
class World:
    host: object
    install_on_path: object  # (name) -> ruta esperada
    install_in_cuda_dir: object  # (version) -> ruta esperada


def _executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@pytest.fixture(params=["system", "fake"])
def world(request, tmp_path):
    bin_dir, cuda_root = tmp_path / "bin", tmp_path / "usr-local"
    bin_dir.mkdir()
    cuda_root.mkdir()
    if request.param == "system":
        host = SystemHostInfo(path=str(bin_dir), cuda_root=cuda_root)

        def on_path(name):
            return _executable(bin_dir / name)

        def in_cuda(version):
            return _executable(cuda_root / f"cuda-{version}" / "bin" / "nvcc")
    else:
        host = FakeHostInfo()

        def on_path(name):
            host.install(name, f"/fake/bin/{name}")
            return f"/fake/bin/{name}"

        def in_cuda(version):
            host.install_cuda(f"/fake/cuda-{version}/bin/nvcc")
            return f"/fake/cuda-{version}/bin/nvcc"

    return World(host, on_path, in_cuda)


def test_which_finds_a_tool_on_the_path(world):
    expected = world.install_on_path("rinthel-tool")

    assert world.host.which("rinthel-tool") == expected


def test_which_is_none_for_a_missing_tool(world):
    assert world.host.which("rinthel-no-such-tool") is None


def test_nvcc_is_none_when_there_is_no_toolkit(world):
    assert world.host.find_nvcc() is None


def test_nvcc_is_found_in_the_installed_cuda_toolkit(world):
    expected = world.install_in_cuda_dir("12.4")

    assert world.host.find_nvcc() == expected


def test_nvcc_on_the_path_wins_over_the_toolkit_directory(world):
    world.install_in_cuda_dir("12.4")
    expected = world.install_on_path("nvcc")

    assert world.host.find_nvcc() == expected


def test_cpu_count_is_at_least_one(world):
    assert world.host.cpu_count() >= 1


async def test_sha256_is_the_hex_digest_of_the_file(world, tmp_path):
    target = tmp_path / "weights.gguf"
    target.write_bytes(b"gguf")

    assert await world.host.sha256(target) == hashlib.sha256(b"gguf").hexdigest()


@pytest.mark.parametrize(("os_name", "platform"), [("posix", "linux"), ("nt", "windows")])
def test_platform_names_the_host_system(os_name, platform):
    assert SystemHostInfo(os_name=os_name).platform() == platform
    assert FakeHostInfo(os=platform).platform() == platform


def test_platform_is_one_of_the_two_platforms(world):
    assert world.host.platform() in ("linux", "windows")
