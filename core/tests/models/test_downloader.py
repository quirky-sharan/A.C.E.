"""Pinned, verified model downloads (§7.8, §15.1 item 8) with a fake fetch."""

from __future__ import annotations

import hashlib
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from ace_core.models.downloader import ModelDownloadError, ensure, model_folder, verify
from ace_core.models.lock import LOCK_FILE, LockedFile, LockedModel, dump_lock, load_lock

CONTENT = {"config.json": b"{}", "model.bin": b"weights" * 100}


def locked(subfolder: str | None = None, *, tamper: str | None = None) -> LockedModel:
    files = tuple(
        LockedFile(name, len(data), hashlib.sha256(data if name != tamper else b"x").hexdigest())
        for name, data in CONTENT.items()
    )
    return LockedModel(
        "stt-test", "stt", "org/repo", "abc123", subfolder, "MIT", "org/original", files
    )


def fake_fetch(calls: list[str]):  # type: ignore[no-untyped-def]
    def fetch(model: LockedModel, file: LockedFile, base: Path) -> Path:
        calls.append(file.path)
        target = base / (model.subfolder or "") / file.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(CONTENT[file.path])
        return target

    return fetch


@pytest.mark.parametrize("subfolder", [None, "int8"])
def test_ensure_downloads_once_and_verifies(tmp_path: Path, subfolder: str | None) -> None:
    model = locked(subfolder)
    calls: list[str] = []
    folder = ensure(tmp_path, model, fetch=fake_fetch(calls))
    assert folder == model_folder(tmp_path, model)
    assert folder == tmp_path / "stt" / "stt-test" / (subfolder or "")
    assert sorted(calls) == ["config.json", "model.bin"]
    assert verify(tmp_path, model) == {}
    ensure(tmp_path, model, fetch=fake_fetch(calls))
    assert len(calls) == 2  # nothing fetched again
    (folder / "model.bin").write_bytes(b"corrupted")
    assert verify(tmp_path, model) == {"model.bin": "size 9 != 700"}
    ensure(tmp_path, model, fetch=fake_fetch(calls))
    assert calls[-1] == "model.bin"  # only the broken file is fetched again


def test_a_file_with_the_wrong_hash_is_deleted(tmp_path: Path) -> None:
    model = locked(tamper="model.bin")
    with pytest.raises(ModelDownloadError, match="SHA-256 mismatch"):
        ensure(tmp_path, model, fetch=fake_fetch([]))
    assert not (model_folder(tmp_path, model) / "model.bin").exists()


def test_free_space_is_checked_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _: usage(10, 9, 1000))
    with pytest.raises(ModelDownloadError, match="GB is free"):
        ensure(tmp_path, locked(), fetch=fake_fetch([]))


def test_the_lock_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "models.lock.json"
    dump_lock([locked("int8")], path)
    assert load_lock(path) == {"stt-test": locked("int8")}


def test_the_shipped_lock_pins_every_stt_candidate() -> None:
    lock = load_lock(LOCK_FILE)
    assert {"stt-turbo", "stt-small"} <= set(lock)
    for model in lock.values():
        assert len(model.revision) == 40  # a full commit hash, never a branch
        assert model.license in {"MIT", "Apache-2.0"}
        assert all(len(f.sha256) == 64 and f.size > 0 for f in model.files)
        assert "model.bin" in {f.path for f in model.files}
