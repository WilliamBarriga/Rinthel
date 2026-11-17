"""La huella del código que lleva la línea de arranque del daemon: dice si
dos boots corrieron el mismo código. Una Instance puede no tener ``.git`` y
``__version__`` no cambia, así que sale del contenido."""

from rinthel_tui.code_version import code_version


def _package(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_the_same_code_in_two_places_has_the_same_version(tmp_path):
    files = {"a.py": "x = 1\n", "sub/b.py": "y = 2\n"}
    daemon = _package(tmp_path / "host", files)
    image = _package(tmp_path / "image", files)

    assert code_version(daemon) == code_version(image)


def test_a_change_in_any_source_file_changes_the_version(tmp_path):
    package = _package(tmp_path / "pkg", {"a.py": "x = 1\n", "sub/b.py": "y = 2\n"})
    before = code_version(package)

    (package / "sub" / "b.py").write_text("y = 3\n")

    assert code_version(package) != before


def test_bytecode_and_caches_do_not_count(tmp_path):
    package = _package(tmp_path / "pkg", {"a.py": "x = 1\n"})
    before = code_version(package)

    _package(package, {"__pycache__/a.cpython-313.pyc": "junk", "notes.md": "no es código"})

    assert code_version(package) == before
