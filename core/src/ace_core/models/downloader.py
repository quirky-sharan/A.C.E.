"""Verified model downloads (§7.8).

Only entries of ``models.lock.json``, only from Hugging Face over HTTPS at the pinned commit, into
the models folder (``ACE_MODELS_DIR``, E: on the dev PC), after a free-space check. Every file
must match its size and SHA-256, or it is deleted.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Final

from ace_core.models.lock import LockedFile, LockedModel

SPACE_MARGIN: Final = 1 << 30  # keep 1 GB free after a download
_CHUNK: Final = 1 << 20


class ModelDownloadError(Exception):
    pass


def model_folder(models_root: Path, model: LockedModel) -> Path:
    """Where the model's files are (the folder a loader is given)."""
    base = models_root / model.kind / model.name
    return base / model.subfolder if model.subfolder else base


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _bad(path: Path, expected: LockedFile) -> str | None:
    if not path.is_file():
        return "missing"
    if path.stat().st_size != expected.size:
        return f"size {path.stat().st_size} != {expected.size}"
    if sha256_of(path) != expected.sha256:
        return "SHA-256 mismatch"
    return None


def verify(models_root: Path, model: LockedModel) -> dict[str, str]:
    """Problems by file path; empty when the model is complete and intact."""
    folder = model_folder(models_root, model)
    problems = {}
    for expected in model.files:
        problem = _bad(folder / expected.path, expected)
        if problem:
            problems[expected.path] = problem
    return problems


Fetch = Callable[[LockedModel, LockedFile, Path], Path]


def _hf_fetch(model: LockedModel, file: LockedFile, base: Path) -> Path:
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            repo_id=model.repo,
            filename=file.path,
            subfolder=model.subfolder,
            revision=model.revision,
            local_dir=base,
        )
    )


def ensure(models_root: Path, model: LockedModel, *, fetch: Fetch = _hf_fetch) -> Path:
    """Download whatever is missing or broken, verify everything, return the model folder."""
    folder = model_folder(models_root, model)
    base = models_root / model.kind / model.name
    missing = [f for f in model.files if _bad(folder / f.path, f) is not None]
    if missing:
        needed = sum(f.size for f in missing)
        models_root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(models_root).free
        if free < needed + SPACE_MARGIN:
            raise ModelDownloadError(
                f"{model.name} needs {needed / 1e9:.1f} GB but only {free / 1e9:.1f} GB is free"
            )
        for expected in missing:
            path = fetch(model, expected, base)
            problem = _bad(path, expected)
            if problem is not None:
                path.unlink(missing_ok=True)
                raise ModelDownloadError(f"{model.name}/{expected.path}: {problem}")
    return folder
