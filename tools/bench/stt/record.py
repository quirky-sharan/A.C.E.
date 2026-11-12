r"""Record the S10 STT benchmark phrases (Sharan's voice). From the repo root, in a normal terminal:

    uv run --project core python tools/bench/stt/record.py

For each phrase: press Enter, say it, press Enter. Type r + Enter to redo the last one, s to skip,
q to quit (it continues where it stopped next time). Recordings are 16 kHz mono WAV files in
tools/bench/stt/data/ (git-ignored: they never leave this PC unless Sharan decides otherwise).
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import wave
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import yaml

HERE = Path(__file__).resolve().parent
RATE = 16_000
MAX_SECONDS = 12.0
SHORT = {"english": 5, "hinglish": 20}  # --short: Sharan's choice at S10 (2026-11-11)


def phrases(short: bool = False) -> list[tuple[str, str]]:
    data = yaml.safe_load((HERE / "phrases.yaml").read_text(encoding="utf-8"))
    items: list[tuple[str, str]] = []
    for group in ("english", "hinglish"):
        texts = data[group][: SHORT[group]] if short else data[group]
        for number, text in enumerate(texts, start=1):
            items.append((f"{group[:2]}{number:02d}", str(text)))
    return items


def wasapi_input(name: str | None) -> int:
    """The WASAPI input device called ``name``, else the WASAPI default input."""
    for api in sd.query_hostapis():
        if api["name"] != "Windows WASAPI":
            continue
        if name is None:
            return int(api["default_input_device"])
        for index in api["devices"]:
            info = sd.query_devices(index)
            if info["max_input_channels"] > 0 and str(info["name"]).casefold() == name.casefold():
                return int(index)
        raise SystemExit(f"no WASAPI microphone called {name!r}")
    raise SystemExit("Windows WASAPI audio is not available")


def record_until_enter(device: int) -> np.ndarray:
    chunks: queue.Queue[np.ndarray] = queue.Queue()

    def on_block(indata: np.ndarray, frames: int, at: object, status: object) -> None:
        chunks.put(indata[:, 0].copy())

    stop = threading.Event()
    threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
    with sd.InputStream(
        device=device,
        samplerate=RATE,
        channels=1,
        dtype="int16",
        blocksize=1280,
        extra_settings=sd.WasapiSettings(auto_convert=True),
        callback=on_block,
    ):
        started = time.monotonic()
        while not stop.is_set() and time.monotonic() - started < MAX_SECONDS:
            time.sleep(0.05)
    parts = []
    while not chunks.empty():
        parts.append(chunks.get())
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)


def save(path: Path, samples: np.ndarray) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.astype(np.int16).tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the STT benchmark phrases.")
    parser.add_argument("--speaker", default="sharan")
    parser.add_argument("--device", default=None, help="input device name (default: Windows default)")
    parser.add_argument("--short", action="store_true", help="only 5 English + 20 Hinglish phrases")
    args = parser.parse_args()
    folder = HERE / "data" / args.speaker
    folder.mkdir(parents=True, exist_ok=True)
    meta = folder / "meta.json"
    device = wasapi_input(args.device)
    if not meta.exists():
        info = sd.query_devices(device)
        meta.write_text(
            json.dumps({"device": info["name"], "started": datetime.now(UTC).isoformat()}, indent=1),
            encoding="utf-8",
        )
    items = phrases(args.short)
    index = 0
    while index < len(items):
        key, text = items[index]
        target = folder / f"{key}.wav"
        if target.exists():
            index += 1
            continue
        print(f"\n[{index + 1}/{len(items)}]  {text}")
        answer = input("  Enter = start, r = redo previous, s = skip, q = quit: ").strip().lower()
        if answer == "q":
            break
        if answer == "s":
            index += 1
            continue
        if answer == "r" and index > 0:
            previous = folder / f"{items[index - 1][0]}.wav"
            previous.unlink(missing_ok=True)
            index -= 1
            continue
        print("  Recording... press Enter when done.")
        samples = record_until_enter(device)
        peak = float(np.max(np.abs(samples))) / 32768 if len(samples) else 0.0
        if len(samples) < RATE * 0.3 or peak < 0.02:
            print(f"  Too short or too quiet (peak {peak:.0%}); let's try again.")
            continue
        save(target, samples)
        print(f"  Saved {len(samples) / RATE:.1f} s (peak {peak:.0%}).")
        index += 1
    done = sum(1 for key, _ in items if (folder / f"{key}.wav").exists())
    print(f"\n{done} of {len(items)} phrases recorded in {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
