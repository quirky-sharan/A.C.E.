"""Normal vs portable data locations."""

from pathlib import Path

import pytest

from ace_core.app.paths import PORTABLE_FLAG_FILE, resolve_paths


def test_normal_mode_lives_in_local_app_data(tmp_path: Path) -> None:
    paths = resolve_paths(exe_dir=tmp_path / "bin", local_app_data=tmp_path / "lad")
    assert paths.portable is False
    assert paths.root == tmp_path / "lad" / "ACE"
    assert paths.logs == paths.root / "logs"
    assert paths.data == paths.root / "data"
    assert paths.config_file == paths.root / "config.toml"


def test_flag_file_next_to_executable_means_portable(tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    (exe_dir / PORTABLE_FLAG_FILE).touch()
    paths = resolve_paths(exe_dir=exe_dir, local_app_data=tmp_path / "lad")
    assert paths.portable is True
    assert paths.root == exe_dir / "data"


def test_portable_flag_argument(tmp_path: Path) -> None:
    paths = resolve_paths(portable=True, exe_dir=tmp_path, local_app_data=tmp_path / "lad")
    assert paths.portable is True
    assert paths.root == tmp_path / "data"


def test_ensure_creates_every_directory(tmp_path: Path) -> None:
    paths = resolve_paths(exe_dir=tmp_path, local_app_data=tmp_path / "lad")
    paths.ensure()
    paths.ensure()  # idempotent
    for directory in (paths.root, paths.data, paths.logs, paths.runtime, paths.cache):
        assert directory.is_dir()


def test_missing_localappdata_falls_back_to_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    paths = resolve_paths(exe_dir=tmp_path / "bin")
    assert paths.root == tmp_path / "AppData" / "Local" / "ACE"


def test_ace_home_moves_the_normal_mode_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACE_HOME", str(tmp_path / "dev-ace"))
    paths = resolve_paths(exe_dir=tmp_path / "bin")
    assert paths.root == tmp_path / "dev-ace"
    assert not paths.portable
    assert resolve_paths(exe_dir=tmp_path / "bin", local_app_data=tmp_path).root == tmp_path / "ACE"
