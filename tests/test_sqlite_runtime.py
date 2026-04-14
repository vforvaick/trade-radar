import sqlite3

from bot.sqlite_utils import sqlite_connection


def test_sqlite_connection_enables_wal(tmp_path):
    db_path = tmp_path / "state.db"

    with sqlite_connection(str(db_path)) as conn:
        conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, status TEXT)")
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


def test_wal_reader_does_not_block_writer(tmp_path):
    db_path = tmp_path / "state.db"

    with sqlite_connection(str(db_path)) as conn:
        conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, status TEXT)")
        conn.execute("INSERT INTO positions (status) VALUES ('OPEN')")

    with sqlite_connection(str(db_path), readonly=True) as reader:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM positions").fetchall()

        with sqlite_connection(str(db_path)) as writer:
            writer.execute("UPDATE positions SET status = 'TP1_HIT' WHERE id = 1")

    with sqlite_connection(str(db_path), readonly=True) as conn:
        status = conn.execute("SELECT status FROM positions WHERE id = 1").fetchone()[0]

    assert status == "TP1_HIT"
