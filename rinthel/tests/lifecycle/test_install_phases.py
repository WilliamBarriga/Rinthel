"""Fases de INSTALL que clonan, compilan y bajan llama.cpp y su modelo.
Corren sobre el ``Host`` de dobles con
``tmp_path`` real; lo que el comando deja en el disco (``curl`` que escribe el
archivo) lo escribe el doble con ``on_success`` y ``on_failure``. El argv exacto de cada comando
no es contrato de la phase: se afirma qué programas corrieron y con qué pins."""

import dataclasses
import hashlib
from pathlib import Path

import pytest

from rinthel_tui.lifecycle import install, install_tasks
from rinthel_tui.lifecycle.domain.errors import PhaseError
from rinthel_tui.lifecycle.install_tasks import ModelDownload
from tests.lifecycle.fakes import RunCall, fake_host


@pytest.fixture
def host():
    host, _ = fake_host()
    host.runner.succeed_by_default()
    return host


def _writes(content: bytes):
    """Lo que deja un ``curl``: ``content`` donde dice ``-o``."""

    def effect(call: RunCall) -> None:
        Path(call.cmd[call.cmd.index("-o") + 1]).write_bytes(content)

    return effect


def _with(cfg, **sections):
    """``cfg`` con cada sección reemplazada por ``dataclasses.replace(sección, **campos)``."""
    return dataclasses.replace(
        cfg, **{name: dataclasses.replace(getattr(cfg, name), **fields) for name, fields in sections.items()}
    )


# ── PREFLIGHT ─────────────────────────────────────────────────────


def _all_tools(host):
    for tool in ("git", "curl", "cmake", "nvidia-smi", "nvcc"):
        host.host_info.install(tool, f"/usr/bin/{tool}")
    host.runner.script(["docker", "info"])


@pytest.mark.parametrize("missing", ["git", "nvcc"])
async def test_preflight_fails_naming_the_missing_tool(host, report, missing):
    _all_tools(host)
    host.host_info._tools.pop(missing)

    with pytest.raises(PhaseError, match=missing):
        await install.phase_install_preflight(host, report)

    assert not host.runner.ran("docker")


@pytest.mark.parametrize(
    ("program", "rc", "output", "pattern", "reported"),
    [
        ("/usr/bin/nvidia-smi", 9, "driver/library version mismatch", "nvidia-smi.*rc 9", "driver"),
        ("/usr/bin/nvcc", 127, "Permission denied", "nvcc.*rc 127", "CUDA toolkit"),
    ],
    ids=["driver", "toolkit"],
)
async def test_preflight_rejects_a_present_but_inoperative_tool(host, report, program, rc, output, pattern, reported):
    _all_tools(host)
    host.runner.script_program(program, rc=rc, output=output)

    with pytest.raises(PhaseError, match=pattern):
        await install.phase_install_preflight(host, report)

    assert any(reported in error and f"rc {rc}" in error for error in report.errors)
    assert not host.runner.ran("docker")


@pytest.mark.parametrize("nvcc_on_path", [True, False], ids=["nvcc-on-path", "nvcc-outside-path"])
async def test_preflight_succeeds_when_everything_is_present(host, report, nvcc_on_path):
    _all_tools(host)
    if not nvcc_on_path:
        host.host_info._tools.pop("nvcc")
        host.host_info.install_cuda("/usr/local/cuda/bin/nvcc")

    await install.phase_install_preflight(host, report)

    assert not report.errors


async def test_preflight_fails_when_docker_is_inactive_without_passwordless_sudo(host, report):
    _all_tools(host)
    host.runner.script(["docker", "info"], rc=1)
    host.runner.script(["sudo", "-n", "systemctl", "start", "docker"], rc=1)

    with pytest.raises(PhaseError):
        await install.phase_install_preflight(host, report)


# ── LLAMA.CPP ─────────────────────────────────────────────────────


@pytest.fixture
def llamacpp(cfg, tmp_path):
    return install_tasks.llamacpp_install(_with(cfg, install={"llamacpp_repo_dir": tmp_path / "llama.cpp"}))


def _origin_of(llamacpp, url):
    return ["git", "-C", str(llamacpp.repo_dir), "remote", "get-url", "origin"], url


async def test_clone_llamacpp_clones_the_pinned_branch_when_missing(host, report, llamacpp):
    await install.phase_install_clone_llamacpp(host, report, task=llamacpp)

    (clone,) = host.runner.calls
    assert clone.cmd[:2] == ("git", "clone")
    assert llamacpp.branch == install_tasks.LLAMACPP_BRANCH
    assert {llamacpp.repo_url, llamacpp.branch, str(llamacpp.repo_dir)} <= set(clone.cmd)


@pytest.mark.parametrize(
    ("origin", "warnings"),
    [("https://github.com/ggml-org/llama.cpp.git", 1), ("https://github.com/thecodacus/llama.cpp.git", 2)],
    ids=["upstream", "old-fork"],
)
async def test_clone_llamacpp_never_touches_an_existing_checkout_and_warns_about_the_old_fork(
    host, report, llamacpp, origin, warnings
):
    (llamacpp.repo_dir / ".git").mkdir(parents=True)
    cmd, url = _origin_of(llamacpp, origin + "\n")
    host.runner.script(cmd, output=url)

    await install.phase_install_clone_llamacpp(host, report, task=llamacpp)

    assert not [call for call in host.runner.calls if call.cmd[:2] == ("git", "clone")]
    assert (llamacpp.repo_dir / ".git").exists()
    assert len(report.warnings) == warnings


async def test_clone_llamacpp_raises_when_git_fails(host, report, llamacpp):
    host.runner.script_program("git", rc=1)

    with pytest.raises(PhaseError):
        await install.phase_install_clone_llamacpp(host, report, task=llamacpp)


@pytest.mark.parametrize("binary", ["bin/llama-server", "bin/llama-server.exe", "bin/Release/llama-server.exe"])
async def test_build_llamacpp_skips_when_the_binary_exists(host, report, llamacpp, binary):
    binary = llamacpp.repo_dir / "build-cuda" / binary
    binary.parent.mkdir(parents=True)
    binary.touch()

    await install.phase_install_build_llamacpp(host, report, task=llamacpp)

    assert host.runner.calls == []


async def test_build_llamacpp_configures_then_builds_inside_the_repo(host, report, llamacpp):
    host.host_info.install("nvcc", "/usr/bin/nvcc")
    await install.phase_install_build_llamacpp(host, report, task=llamacpp)

    configure, build = host.runner.ran("cmake")
    assert "--build" not in configure.cmd and "--build" in build.cmd
    assert ("--config", "Release") == build.cmd[build.cmd.index("--config"):build.cmd.index("--config") + 2]
    assert configure.cwd == build.cwd == llamacpp.repo_dir
    assert "-DCMAKE_CUDA_COMPILER=/usr/bin/nvcc" in configure.cmd


async def test_build_llamacpp_uses_cuda_toolkit_outside_path(host, report, llamacpp):
    host.host_info.install_cuda("/usr/local/cuda-12.8/bin/nvcc")

    await install.phase_install_build_llamacpp(host, report, task=llamacpp)

    configure, _ = host.runner.ran("cmake")
    assert "-DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc" in configure.cmd


async def test_build_llamacpp_requires_nvcc_before_running_cmake(host, report, llamacpp):
    with pytest.raises(PhaseError, match="nvcc not found"):
        await install.phase_install_build_llamacpp(host, report, task=llamacpp)

    assert host.runner.calls == []


async def test_build_llamacpp_stops_when_cmake_configure_fails(host, report, llamacpp):
    host.host_info.install("nvcc", "/usr/bin/nvcc")
    host.runner.script_program("cmake", rc=1)

    with pytest.raises(PhaseError):
        await install.phase_install_build_llamacpp(host, report, task=llamacpp)

    assert len(host.runner.ran("cmake")) == 1


# ── DESCARGAS ─────────────────────────────────────────────────────


async def test_download_skips_when_the_file_is_already_there(host, report, tmp_path):
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"not empty")

    await install.phase_install_download(host, report, task=ModelDownload("Modelo", "https://x/m.gguf", dest))

    assert host.runner.calls == []


async def test_interrupted_download_keeps_only_a_resumable_partial(host, report, tmp_path):
    dest = tmp_path / "model.gguf"
    host.runner.script_program("curl", rc=18)
    host.runner.on_failure("curl", _writes(b"partial"))

    with pytest.raises(PhaseError):
        await install.phase_install_download(host, report, task=ModelDownload("Modelo", "https://x/m.gguf", dest))

    assert not dest.exists()
    assert dest.with_name("model.gguf.part").read_bytes() == b"partial"


async def test_retry_resumes_the_partial_and_publishes_only_after_success(host, report, tmp_path):
    dest = tmp_path / "model.gguf"
    partial = dest.with_name("model.gguf.part")
    partial.write_bytes(b"part")

    def resume(call):
        target = Path(call.cmd[call.cmd.index("-o") + 1])
        assert target == partial
        assert call.cmd[call.cmd.index("-C") + 1] == "-"
        assert not dest.exists()
        with target.open("ab") as stream:
            stream.write(b"ial")

    host.runner.on_success("curl", resume)
    await install.phase_install_download(host, report, task=ModelDownload("Modelo", "https://x/m.gguf", dest))

    assert dest.read_bytes() == b"partial"
    assert not partial.exists()


async def test_download_rejects_a_successful_but_empty_response(host, report, tmp_path):
    dest = tmp_path / "model.gguf"
    host.runner.on_success("curl", _writes(b""))

    with pytest.raises(PhaseError):
        await install.phase_install_download(host, report, task=ModelDownload("Modelo", "https://x/m.gguf", dest))

    assert not dest.exists()


async def test_download_verifies_a_known_hash_before_skipping_an_existing_file(host, report, tmp_path):
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"truncated")
    task = ModelDownload("Modelo", "https://x/m.gguf", dest, hashlib.sha256(b"complete").hexdigest())
    host.runner.on_success("curl", _writes(b"complete"))

    await install.phase_install_download(host, report, task=task)

    assert dest.read_bytes() == b"complete"
    assert len(host.runner.ran("curl")) == 1


async def test_an_http_error_never_publishes_its_response_body(host, report, tmp_path):
    dest = tmp_path / "model.gguf"

    # This phase owns the curl adapter: assert its HTTP failure intent.
    host.runner.on_failure("curl", _writes(b"<html>error</html>"))
    host.runner.script_program("curl", rc=22)
    with pytest.raises(PhaseError):
        await install.phase_install_download(host, report, task=ModelDownload("Modelo", "https://x/m.gguf", dest))

    assert "--fail" in host.runner.ran("curl")[0].cmd
    assert not dest.exists()


async def test_download_skips_a_final_with_a_verified_hash(host, report, tmp_path):
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"complete")
    partial = dest.with_name("model.gguf.part")
    partial.write_bytes(b"stale partial")
    task = ModelDownload("Modelo", "https://x/m.gguf", dest, hashlib.sha256(b"complete").hexdigest())

    await install.phase_install_download(host, report, task=task)

    assert host.runner.calls == []
    assert dest.read_bytes() == b"complete"
    assert partial.read_bytes() == b"stale partial"


@pytest.mark.parametrize("failure", ["transfer", "hash"])
async def test_a_failed_replacement_preserves_the_existing_final(host, report, tmp_path, failure):
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"existing model")
    task = ModelDownload("Modelo", "https://x/m.gguf", dest, hashlib.sha256(b"new model").hexdigest())
    if failure == "transfer":
        host.runner.script_program("curl", rc=18)
        host.runner.on_failure("curl", _writes(b"partial"))
    else:
        host.runner.on_success("curl", _writes(b"wrong hash"))

    with pytest.raises(PhaseError):
        await install.phase_install_download(host, report, task=task)

    assert dest.read_bytes() == b"existing model"
    if failure == "hash":
        assert not dest.with_name("model.gguf.part").exists()


async def test_download_redoes_an_empty_file(host, report, tmp_path):
    dest = tmp_path / "model.gguf"
    dest.touch()
    host.runner.on_success("curl", _writes(b"weights"))

    await install.phase_install_download(host, report, task=ModelDownload("Modelo", "https://x/m.gguf", dest))

    assert dest.read_bytes() == b"weights"


async def test_download_fetches_the_url_into_a_new_directory(host, report, tmp_path):
    dest = tmp_path / "models" / "model.gguf"
    host.runner.on_success("curl", _writes(b"weights"))

    await install.phase_install_download(host, report, task=ModelDownload("Modelo", "https://x/m.gguf", dest))

    (curl,) = host.runner.ran("curl")
    assert curl.cmd[-1] == "https://x/m.gguf"
    assert dest.read_bytes() == b"weights"


async def test_download_raises_when_curl_fails(host, report, tmp_path):
    host.runner.script_program("curl", rc=22)

    with pytest.raises(PhaseError):
        await install.phase_install_download(
            host, report, task=ModelDownload("Modelo", "https://x/m.gguf", tmp_path / "m.gguf")
        )
