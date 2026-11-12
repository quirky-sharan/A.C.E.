"""``models.lock.json``: every model ACE may download, pinned to a repository commit with the size
and SHA-256 of each file (§7.8, §15.1 item 8). Downloads come only from these entries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

LOCK_FILE: Final = Path(__file__).with_name("models.lock.json")


@dataclass(frozen=True, slots=True)
class LockedFile:
    path: str  # relative to the model folder, e.g. "model.bin"
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class LockedModel:
    name: str  # e.g. "stt-turbo"
    kind: str  # stt / tts / wake / vad / llm (§5.8 folders)
    repo: str  # Hugging Face model repository
    revision: str  # the exact commit
    subfolder: str | None  # the model inside the repo, if not at its root
    license: str  # the license of the weights (for conversions: the original's)
    source: str  # the original model (conversions name what they were made from)
    files: tuple[LockedFile, ...]

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


def _model(entry: dict[str, Any]) -> LockedModel:
    return LockedModel(
        name=str(entry["name"]),
        kind=str(entry["kind"]),
        repo=str(entry["repo"]),
        revision=str(entry["revision"]),
        subfolder=entry.get("subfolder"),
        license=str(entry["license"]),
        source=str(entry["source"]),
        files=tuple(
            LockedFile(path=str(f["path"]), size=int(f["size"]), sha256=str(f["sha256"]))
            for f in entry["files"]
        ),
    )


def load_lock(path: Path = LOCK_FILE) -> dict[str, LockedModel]:
    data = json.loads(path.read_text(encoding="utf-8"))
    models = [_model(entry) for entry in data["models"]]
    by_name = {model.name: model for model in models}
    if len(by_name) != len(models):
        raise ValueError("duplicate model names in the lock file")
    return by_name


def dump_lock(models: list[LockedModel], path: Path = LOCK_FILE) -> None:
    data = {
        "comment": "Pinned models (ACE_MASTER_PLAN.md §7.8). Regenerate: tools/dev/lock_models.py",
        "models": [
            {
                "name": m.name,
                "kind": m.kind,
                "repo": m.repo,
                "revision": m.revision,
                "subfolder": m.subfolder,
                "license": m.license,
                "source": m.source,
                "files": [{"path": f.path, "size": f.size, "sha256": f.sha256} for f in m.files],
            }
            for m in models
        ],
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
