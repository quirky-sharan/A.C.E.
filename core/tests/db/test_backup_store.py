"""Backup file naming, listing, pruning per kind, and "already backed up today" checks."""

from datetime import date, datetime
from pathlib import Path

from ace_core.db.backup import BackupKind, BackupStore, parse_backup_name

NOW = datetime(2026, 11, 6, 21, 5, 9)


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_names_per_kind(tmp_path: Path) -> None:
    store = BackupStore(tmp_path, now=lambda: NOW)
    assert store.new_path(BackupKind.REGULAR).name == "ace-20261106-210509.db"
    assert store.new_path(BackupKind.PREMIGRATION).name == "ace-premigration-20261106-210509.db"
    assert store.new_path(BackupKind.PRERESTORE).name == "ace-prerestore-20261106-210509.db"


def test_same_second_gets_a_numbered_suffix(tmp_path: Path) -> None:
    store = BackupStore(tmp_path, now=lambda: NOW)
    touch(store.new_path(BackupKind.REGULAR))
    assert store.new_path(BackupKind.REGULAR).name == "ace-20261106-210509-1.db"


def test_listing_is_newest_first_and_ignores_other_files(tmp_path: Path) -> None:
    for name in (
        "ace-20261101-080000.db",
        "ace-20261105-080000.db",
        "ace-premigration-20261103-080000.db",
        "ace-corrupt-20261104-080000.db",
        "ace.db",
        "notes.txt",
    ):
        touch(tmp_path / name)
    store = BackupStore(tmp_path)
    assert [b.path.name for b in store.list_backups()] == [
        "ace-20261105-080000.db",
        "ace-premigration-20261103-080000.db",
        "ace-20261101-080000.db",
    ]
    assert [b.path.name for b in store.list_backups(BackupKind.REGULAR)] == [
        "ace-20261105-080000.db",
        "ace-20261101-080000.db",
    ]


def test_prune_keeps_the_newest_of_each_kind_only(tmp_path: Path) -> None:
    for day in range(1, 11):
        touch(tmp_path / f"ace-202611{day:02d}-080000.db")
    for day in range(1, 8):
        touch(tmp_path / f"ace-premigration-202611{day:02d}-080000.db")
    store = BackupStore(tmp_path, keep={BackupKind.REGULAR: 7})

    removed = store.prune(BackupKind.REGULAR)

    assert sorted(p.name for p in removed) == [
        "ace-20261101-080000.db",
        "ace-20261102-080000.db",
        "ace-20261103-080000.db",
    ]
    assert len(store.list_backups(BackupKind.REGULAR)) == 7
    assert len(store.list_backups(BackupKind.PREMIGRATION)) == 7  # other kinds untouched
    store.prune(BackupKind.PREMIGRATION)
    assert len(store.list_backups(BackupKind.PREMIGRATION)) == 5  # default keep


def test_has_regular_backup_on_a_day(tmp_path: Path) -> None:
    touch(tmp_path / "ace-20261106-080000.db")
    touch(tmp_path / "ace-premigration-20261107-080000.db")
    store = BackupStore(tmp_path)
    assert store.has_regular_backup_on(date(2026, 11, 6))
    assert not store.has_regular_backup_on(date(2026, 11, 7))


def test_parse_backup_name() -> None:
    parsed = parse_backup_name(Path("ace-prerestore-20261106-210509-2.db"))
    assert parsed is not None
    assert parsed.kind is BackupKind.PRERESTORE
    assert parsed.seq == 2
    assert parsed.day == date(2026, 11, 6)
    assert parse_backup_name(Path("ace-corrupt-20261106-210509.db")) is None
