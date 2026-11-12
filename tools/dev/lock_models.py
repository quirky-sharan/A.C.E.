r"""Pin the S10 STT models into core/src/ace_core/models/models.lock.json (review the diff!).

From the repo root (downloads ~5.3 GB into ACE_MODELS_DIR, e.g. E:\ACE-Models):
    uv run --project core python tools/dev/lock_models.py

For each candidate it reads the repository at a fixed commit, downloads the files a CTranslate2
Whisper model needs, hashes them, cross-checks every large file against the SHA-256 Hugging Face
publishes for it, and writes the lock. Licenses are those verified on the ORIGINAL model cards
(conversions inherit them) and recorded in the Progress Log.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

from ace_core.models.downloader import model_folder, sha256_of
from ace_core.models.lock import LockedFile, LockedModel, dump_lock

NEEDED = ("config.json", "model.bin", "tokenizer.json", "vocabulary.json", "vocabulary.txt",
          "preprocessor_config.json")

CANDIDATES = [
    # name, repo, revision, subfolder, license, original model
    ("stt-turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
     "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf", None, "MIT", "openai/whisper-large-v3-turbo"),  # pragma: allowlist secret
    ("stt-small", "Systran/faster-whisper-small",
     "536b0662742c02347bc0e980a01041f333bce120", None, "Apache-2.0", "openai/whisper-small"),  # pragma: allowlist secret
    ("stt-hinglish-swift", "MSpider3/whisper-hindi2hinglish-swift-ct2",
     "484362f23d657c07c2762ce1c52d7b4a7ab49d25", None, "Apache-2.0",  # pragma: allowlist secret
     "Oriserve/Whisper-Hindi2Hinglish-Swift"),
    ("stt-hinglish-prime", "Hub84/faster-whisper-hinglish-prime",
     "da5b871e2b709091d067e7b729515cf49a0d56cf", None, "Apache-2.0",  # pragma: allowlist secret
     "Oriserve/Whisper-Hindi2Hinglish-Prime"),
    ("stt-hinglish-trelis", "nikh360pro/capsbro-hinglish-ct2",
     "87a1f963adb6e7902a766a3d20217fa63d7f018b", "int8", "Apache-2.0",  # pragma: allowlist secret
     "Trelis/whisper-hinglish-preview"),
]


def main() -> int:
    root = Path(os.environ.get("ACE_MODELS_DIR", "")).resolve()
    if not os.environ.get("ACE_MODELS_DIR"):
        print("Set ACE_MODELS_DIR first (E:\\ACE-Models on the dev PC).", file=sys.stderr)
        return 2
    api = HfApi()
    locked: list[LockedModel] = []
    for name, repo, revision, subfolder, license_name, source in CANDIDATES:
        info = api.model_info(repo, revision=revision, files_metadata=True)
        prefix = f"{subfolder}/" if subfolder else ""
        lfs = {s.rfilename: s.lfs.sha256 for s in info.siblings or [] if s.lfs}
        wanted = [
            s.rfilename[len(prefix):]
            for s in info.siblings or []
            if s.rfilename.startswith(prefix) and s.rfilename[len(prefix):] in NEEDED
        ]
        files = []
        for relative in sorted(wanted):
            print(f"{name}: {relative} ...", flush=True)
            path = Path(hf_hub_download(repo_id=repo, filename=relative, subfolder=subfolder,
                                        revision=revision, local_dir=root / "stt" / name))
            digest = sha256_of(path)
            published = lfs.get(prefix + relative)
            if published and published != digest:
                raise SystemExit(f"{name}/{relative}: SHA-256 differs from Hugging Face's")
            files.append(LockedFile(path=relative, size=path.stat().st_size, sha256=digest))
        model = LockedModel(name, "stt", repo, revision, subfolder, license_name, source, tuple(files))
        assert model_folder(root, model).is_dir()
        locked.append(model)
        print(f"{name}: {model.size / 1e9:.2f} GB pinned")
    dump_lock(locked)
    print("wrote models.lock.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
