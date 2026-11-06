"""runtime/ipc.json: write, read, private, removed only by its owner process."""

import os
import sys
from pathlib import Path

import pytest

from ace_core.ipc.runtime_file import (
    RUNTIME_FILE_NAME,
    IpcEndpoint,
    read_runtime_file,
    remove_runtime_file,
    write_runtime_file,
)

ENDPOINT = IpcEndpoint(port=51234, token="t" * 43, pid=os.getpid(), version="0.0.1")


def test_write_read_and_remove(tmp_path: Path) -> None:
    path = write_runtime_file(tmp_path, ENDPOINT)
    assert path.name == RUNTIME_FILE_NAME
    assert read_runtime_file(tmp_path) == ENDPOINT
    remove_runtime_file(tmp_path, pid=os.getpid())
    assert not path.exists()


def test_a_newer_core_s_file_is_left_alone(tmp_path: Path) -> None:
    other = IpcEndpoint(port=1, token="o" * 43, pid=os.getpid() + 1, version="0.0.1")
    path = write_runtime_file(tmp_path, other)
    remove_runtime_file(tmp_path, pid=os.getpid())
    assert path.exists()


def test_missing_or_damaged_file_reads_as_none(tmp_path: Path) -> None:
    assert read_runtime_file(tmp_path) is None
    (tmp_path / RUNTIME_FILE_NAME).write_text("{not json", encoding="utf-8")
    assert read_runtime_file(tmp_path) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACLs")
def test_runtime_file_is_private(tmp_path: Path) -> None:
    import win32security

    path = write_runtime_file(tmp_path, ENDPOINT)
    descriptor = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
    dacl = descriptor.GetSecurityDescriptorDacl()
    assert dacl is not None
    assert dacl.GetAceCount() == 1
