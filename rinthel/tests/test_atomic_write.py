"""``atomic_write`` — el archivo queda entero o no cambia: un lector de otro
proceso (o un crash a mitad) nunca ve uno truncado."""

import pytest

from rinthel_tui.atomic_write import atomic_write


def test_writes_text_and_bytes(tmp_path):
    atomic_write(tmp_path / "a.txt", "hola")
    atomic_write(tmp_path / "b.bin", b"\x00\x01")

    assert (tmp_path / "a.txt").read_text() == "hola"
    assert (tmp_path / "b.bin").read_bytes() == b"\x00\x01"


def test_replaces_existing_file_whole_and_keeps_its_mode(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("viejo y más largo")
    target.chmod(0o640)

    atomic_write(target, "nuevo")

    assert target.read_text() == "nuevo"
    assert target.stat().st_mode & 0o777 == 0o640


def test_new_file_gets_new_mode_default_0644_and_creates_parent(tmp_path):
    default = tmp_path / "sub" / "a.txt"
    private = tmp_path / "b.txt"

    atomic_write(default, "x")
    atomic_write(private, "x", new_mode=0o600)

    assert default.stat().st_mode & 0o777 == 0o644
    assert private.stat().st_mode & 0o777 == 0o600


def test_failed_serialization_leaves_old_file_intact_and_no_temp(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("viejo")

    with pytest.raises(TypeError):
        atomic_write(target, 123)  # type: ignore[arg-type]

    assert target.read_text() == "viejo"
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]


def test_a_replace_that_fails_leaves_old_file_intact_and_no_temp(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("viejo")

    def failing(*_args):
        raise OSError("disco lleno")

    with pytest.raises(OSError, match="disco lleno"):
        atomic_write(target, "nuevo", replace=failing)

    assert target.read_text() == "viejo"
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]


def test_interrupt_during_replace_leaves_old_file_intact_and_no_temp(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("viejo")

    def interrupted(*_args):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        atomic_write(target, "nuevo", replace=interrupted)

    assert target.read_text() == "viejo"
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]
