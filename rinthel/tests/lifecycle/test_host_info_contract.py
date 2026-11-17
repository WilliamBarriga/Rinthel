"""Suite de contrato del puerto ``HostInfo``: el adapter real con un ``PATH``,
y una raíz de CUDA controlados (``tmp_path``) contra ``FakeHostInfo``."""

import hashlib
import stat
from dataclasses import dataclass

import pytest

from rinthel_tui.lifecycle.adapters.host_info import SystemHostInfo
from rinthel_tui.lifecycle.adapters.windows_host_info import WindowsHostInfo
from tests.lifecycle.fakes import FakeHostInfo


@dataclass
class World:
    host: object
    install_on_path: object  # (name) -> ruta esperada
    install_in_cuda_dir: object  # (version) -> ruta esperada
    platform: str
    build_binary: object  # (build_dir) -> ruta del llama-server que deja un build de esta Platform


def _executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@pytest.fixture(params=["system", "windows", "fake-linux", "fake-windows"])
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

        def build_binary(build_dir):
            return _executable(build_dir / "bin" / "llama-server")

        return World(host, on_path, in_cuda, "linux", build_binary)
    if request.param == "windows":
        program_files = tmp_path / "Program Files"
        host = WindowsHostInfo(path=str(bin_dir), env={"ProgramFiles": str(program_files)})

        def on_path(name):
            return _executable(bin_dir / name)

        def in_cuda(version):
            return _executable(program_files / "NVIDIA GPU Computing Toolkit" / "CUDA" / f"v{version}" / "bin" / "nvcc.exe")

        def build_binary(build_dir):
            return _executable(build_dir / "bin" / "Release" / "llama-server.exe")

        return World(host, on_path, in_cuda, "windows", build_binary)
    platform = request.param.removeprefix("fake-")
    host = FakeHostInfo(os=platform)

    def on_path(name):
        host.install(name, f"/fake/bin/{name}")
        return f"/fake/bin/{name}"

    def in_cuda(version):
        host.install_cuda(f"/fake/cuda-{version}/bin/nvcc")
        return f"/fake/cuda-{version}/bin/nvcc"

    def build_binary(build_dir):
        path = build_dir / "bin" / ("Release/llama-server.exe" if platform == "windows" else "llama-server")
        path.parent.mkdir(parents=True)
        path.touch()
        return str(path)

    return World(host, on_path, in_cuda, platform, build_binary)


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


def test_platform_names_the_host_system(world):
    assert world.host.platform() == world.platform


def test_no_llama_server_before_the_build(world, tmp_path):
    assert world.host.find_llama_server(tmp_path / "build-cuda") is None


def test_the_llama_server_a_build_leaves_is_found(world, tmp_path):
    build_dir = tmp_path / "build-cuda"
    expected = world.build_binary(build_dir)

    assert str(world.host.find_llama_server(build_dir)) == expected


# What only the Windows adapter discovers: CMake bundled with Visual Studio,
# CUDA_PATH, the multi-config ``Release`` directory.


@pytest.fixture
def windows(tmp_path):
    program_files = tmp_path / "pf"
    env = {"ProgramFiles": str(program_files)}
    return program_files, env, WindowsHostInfo(path=str(tmp_path / "empty"), env=env)


def test_cmake_is_found_inside_visual_studio_when_it_is_not_on_the_path(windows):
    program_files, env, _ = windows
    bundled = _executable(
        program_files / "Microsoft Visual Studio" / "2022" / "Community" / "Common7" / "IDE"
        / "CommonExtensions" / "Microsoft" / "CMake" / "CMake" / "bin" / "cmake.exe"
    )

    assert WindowsHostInfo(path="", env=env).which("cmake") == bundled


def test_cmake_on_the_path_wins_over_the_one_in_visual_studio(tmp_path, windows):
    program_files, env, _ = windows
    _executable(
        program_files / "Microsoft Visual Studio" / "2022" / "Community" / "Common7" / "IDE"
        / "CommonExtensions" / "Microsoft" / "CMake" / "CMake" / "bin" / "cmake.exe"
    )
    on_path = _executable(tmp_path / "bin" / "cmake")

    assert WindowsHostInfo(path=str(tmp_path / "bin"), env=env).which("cmake") == on_path


def test_visual_studio_cmake_is_only_a_fallback_for_cmake(windows):
    program_files, env, host = windows
    assert host.which("cmake") is None
    assert host.which("git") is None


def test_nvcc_is_found_through_cuda_path(tmp_path, windows):
    _, env, _ = windows
    cuda = tmp_path / "custom-cuda"
    expected = _executable(cuda / "bin" / "nvcc.exe")

    host = WindowsHostInfo(path="", env={**env, "CUDA_PATH": str(cuda)})

    assert host.find_nvcc() == expected


def test_the_newest_installed_toolkit_wins(windows):
    program_files, _, host = windows
    root = program_files / "NVIDIA GPU Computing Toolkit" / "CUDA"
    _executable(root / "v12.9" / "bin" / "nvcc.exe")
    newest = _executable(root / "v12.10" / "bin" / "nvcc.exe")

    assert host.find_nvcc() == newest


def test_a_single_config_build_dir_is_also_found_on_windows(tmp_path, windows):
    _, _, host = windows
    binary = _executable(tmp_path / "build" / "bin" / "llama-server.exe")

    assert str(host.find_llama_server(tmp_path / "build")) == binary
