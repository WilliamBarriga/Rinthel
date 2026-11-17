"""Contract of the ``rinthel.db`` migrator, on a temporary file: the schema
version is ``PRAGMA user_version``, each migration applies once and whole,
and a file newer than the code or an SQLite older than 3.37 stops startup
with a clear error before anything is written."""

import sqlite3
from contextlib import closing

import pytest

from rinthel_tui import database
from rinthel_tui.database import SchemaTooNew, SqliteTooOld

ONE = ("CREATE TABLE a (id INTEGER PRIMARY KEY) STRICT;",)
TWO = (*ONE, "CREATE TABLE b (id INTEGER PRIMARY KEY, name TEXT NOT NULL) STRICT;")


def _version(path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def _tables(path) -> dict[str, int]:
    """Table name -> strict flag, for the tables the migrations created."""
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("SELECT name, strict FROM pragma_table_list WHERE schema = 'main'").fetchall()
    return {name: strict for name, strict in rows if not name.startswith("sqlite_")}


def test_a_new_file_gets_every_migration_and_their_count_as_its_version(tmp_path):
    path = tmp_path / "rinthel.db"

    database.migrate(path, migrations=TWO)

    assert _version(path) == 2
    assert _tables(path) == {"a": 1, "b": 1}


def test_migrating_twice_changes_nothing(tmp_path):
    path = tmp_path / "rinthel.db"
    database.migrate(path, migrations=TWO)

    database.migrate(path, migrations=TWO)

    assert _version(path) == 2


def test_only_the_pending_migrations_apply(tmp_path):
    path = tmp_path / "rinthel.db"
    database.migrate(path, migrations=ONE)

    database.migrate(path, migrations=TWO)

    assert (_version(path), set(_tables(path))) == (2, {"a", "b"})


def test_a_file_newer_than_the_code_fails_clearly_and_stays_untouched(tmp_path):
    path = tmp_path / "rinthel.db"
    database.migrate(path, migrations=TWO)

    with pytest.raises(SchemaTooNew) as raised:
        database.migrate(path, migrations=ONE)

    assert "2" in str(raised.value) and "1" in str(raised.value)
    assert _version(path) == 2


def test_an_sqlite_older_than_3_37_fails_before_creating_the_file(tmp_path):
    path = tmp_path / "rinthel.db"

    with pytest.raises(SqliteTooOld) as raised:
        database.migrate(path, migrations=TWO, sqlite_version=(3, 36, 9))

    assert "3.37" in str(raised.value)
    assert not path.exists()


def test_a_migration_that_fails_leaves_the_previous_version(tmp_path):
    path = tmp_path / "rinthel.db"
    database.migrate(path, migrations=ONE)
    broken = (*ONE, "CREATE TABLE b (id INTEGER PRIMARY KEY) STRICT; CREATE TABLE a (x TEXT) STRICT;")

    with pytest.raises(sqlite3.Error):
        database.migrate(path, migrations=broken)

    assert (_version(path), set(_tables(path))) == (1, {"a"})


def test_the_real_schema_is_strict_and_the_journal_is_rollback(tmp_path):
    path = tmp_path / "rinthel.db"

    database.migrate(path)

    assert _version(path) == len(database.MIGRATIONS)
    assert _tables(path) and all(_tables(path).values())
    with database.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] > 0


def test_the_missing_state_directory_is_created(tmp_path):
    path = tmp_path / "data" / "rinthel.db"

    database.migrate(path)

    assert path.exists()
