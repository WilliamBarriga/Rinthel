"""Instance root discovery from the rinthel/ application directory."""

from rinthel_tui.instance import Instance


def test_discover_resolves_root_from_rinthel_dir(tmp_path):
    (tmp_path / ".git").mkdir()
    package_dir = tmp_path / "rinthel" / "rinthel_tui"
    package_dir.mkdir(parents=True)

    instance = Instance.discover(package_dir)

    assert instance.root == tmp_path
    assert instance.app_dir == tmp_path / "rinthel"
    assert instance.env_path == tmp_path / ".env"
    assert instance.data_dir == tmp_path / "data"
    assert instance.logs_dir == tmp_path / "logs"


def test_discover_without_git_falls_back_to_parent_of_rinthel(tmp_path):
    package_dir = tmp_path / "rinthel" / "rinthel_tui"
    package_dir.mkdir(parents=True)

    assert Instance.discover(package_dir).root == tmp_path


def test_discover_default_matches_this_checkout():
    instance = Instance.discover()

    assert (instance.root / "rinthel" / "rinthel_tui" / "instance.py").is_file()
