r"""S10 STT benchmark (ACE_MASTER_PLAN.md S10 task 4): every candidate model on Sharan's recordings.

From the repo root, after tools/bench/stt/record.py and tools/dev/lock_models.py:
    uv run --project core python tools/bench/stt/run.py

Per model / language setting it measures, on the same audio ACE would get (VAD-trimmed):
- WER and CER against the reference texts (English and Hinglish separately; numbers and
  punctuation normalised),
- latency per utterance (transcription time) and the real-time factor,
- command accuracy: does ACE's fast-path router make the same decision from the transcript as from
  the reference text? (Hinglish spelling varies, so this is what matters for ACE),
- GPU memory in use after loading.
Writes RESULTS.md and results.json next to this file (no audio, no transcripts of Sharan's voice
beyond the per-phrase table).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from rapidfuzz.distance import Levenshtein

from ace_core.brain.router import Router
from ace_core.models.downloader import model_folder, verify
from ace_core.models.lock import load_lock
from ace_core.skills.catalog import build_registry
from ace_core.voice.listen import command_prompt
from ace_core.voice.stt import Verdict, WhisperOptions, WhisperTranscriber, judge, trim_silence

HERE = Path(__file__).resolve().parent
PROMPT = command_prompt(())  # what ACE sends before any app has been launched through it
CONFIGS = [  # (label, model, language, device)
    ("turbo · auto", "stt-turbo", None, "cuda"),
    ("turbo · en", "stt-turbo", "en", "cuda"),
    ("hinglish-swift · auto", "stt-hinglish-swift", None, "cuda"),
    ("hinglish-swift · en", "stt-hinglish-swift", "en", "cuda"),
    ("hinglish-prime · auto", "stt-hinglish-prime", None, "cuda"),
    ("hinglish-prime · en", "stt-hinglish-prime", "en", "cuda"),
    ("hinglish-trelis · auto", "stt-hinglish-trelis", None, "cuda"),
    ("hinglish-trelis · en", "stt-hinglish-trelis", "en", "cuda"),
    ("small · en · CPU", "stt-small", "en", "cpu"),
    ("swift · en · CPU", "stt-hinglish-swift", "en", "cpu"),
    ("turbo · en · CPU", "stt-turbo", "en", "cpu"),
]
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen " \
       "fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    return str(n)


def normalise(text: str) -> str:
    text = text.casefold().replace("’", "'")
    text = re.sub(r"(\d+):(\d+)", lambda m: f"{m[1]} {m[2]}", text)
    text = re.sub(r"\d+", lambda m: number_words(int(m[0])), text)
    text = re.sub(r"[^\w' ]+", " ", text)
    return " ".join(text.split())


def wer(reference: str, hypothesis: str) -> tuple[int, int]:
    ref, hyp = normalise(reference).split(), normalise(hypothesis).split()
    return Levenshtein.distance(ref, hyp), max(1, len(ref))


def skeleton(word: str) -> str:
    """One spelling for the many romanisations of a Hindi word (gaana / gana, chhota / chota,
    awaaz / avaaz): long vowels, w / v, z / j, q / k, ph / f, aspiration h, doubled letters."""
    word = word.replace("ee", "i").replace("oo", "u").replace("ph", "f")
    word = word.replace("w", "v").replace("z", "j").replace("q", "k")
    word = re.sub(r"([bcdgjkpt])h+", r"\1", word)
    return re.sub(r"(.)\1+", r"\1", word)


def lenient_wer(reference: str, hypothesis: str) -> tuple[int, int]:
    """WER that forgives Hinglish spelling variants (romanised Hindi has no standard spelling)."""
    ref = [skeleton(w) for w in normalise(reference).split()]
    hyp = [skeleton(w) for w in normalise(hypothesis).split()]
    return Levenshtein.distance(ref, hyp), max(1, len(ref))


def cer(reference: str, hypothesis: str) -> tuple[int, int]:
    ref, hyp = normalise(reference), normalise(hypothesis)
    return Levenshtein.distance(ref, hyp), max(1, len(ref))


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        return np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)


def gpu_memory_mb() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout
        return int(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


@dataclass
class Row:
    key: str
    group: str
    reference: str
    audio: np.ndarray  # VAD-trimmed, as ACE transcribes it
    vad_ms: float  # time the VAD trim took


def canonical(value: object) -> object:
    """Entity text as ACE resolves it: case and punctuation don't change the app it picks."""
    if isinstance(value, str):
        return " ".join(re.sub(r"[^\w' ]+", " ", value.casefold()).split())
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def decision(router: Router, text: str) -> tuple[str, object]:
    route = router.route(text)
    params = route.params.model_dump(mode="json", exclude_defaults=True) if route.params else None
    return route.intent, canonical(params)


def load_row(path: Path, group: str, reference: str) -> Row:
    audio = read_wav(path)
    started = time.perf_counter()
    trimmed = trim_silence(audio)
    return Row(path.stem, group, reference, trimmed, 1000 * (time.perf_counter() - started))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the STT benchmark.")
    parser.add_argument("--speaker", default="sharan")
    parser.add_argument("--only", nargs="*", help="labels of configs to run")
    parser.add_argument("--data", type=Path, default=HERE / "data", help="recordings root")
    parser.add_argument("--out", type=Path, default=HERE, help="where RESULTS.md / results.json go")
    args = parser.parse_args()
    models_root = Path(__import__("os").environ["ACE_MODELS_DIR"])
    phrases = yaml.safe_load((HERE / "phrases.yaml").read_text(encoding="utf-8"))
    folder = args.data / args.speaker
    paths = [
        (folder / f"{group[:2]}{number:02d}.wav", group, str(text))
        for group in ("english", "hinglish")
        for number, text in enumerate(phrases[group], start=1)
    ]
    paths = [item for item in paths if item[0].exists()]
    if not paths:
        print("no recordings yet: run tools/bench/stt/record.py first", file=sys.stderr)
        return 2
    trim_silence(read_wav(paths[0][0]))  # loads the VAD model, so it is not timed below
    rows = [load_row(*item) for item in paths]
    print(f"{len(rows)} recordings")
    lock = load_lock()
    router = Router(build_registry(settings=None, dev=True))  # type: ignore[arg-type]
    results = []
    for label, name, language, device in CONFIGS:
        if args.only and label not in args.only:
            continue
        model = lock[name]
        if verify(models_root, model):
            print(f"skip {label}: {name} is not downloaded")
            continue
        before = gpu_memory_mb()
        started = time.perf_counter()
        transcriber = WhisperTranscriber(model_folder(models_root, model), label=name, device=device,
                                         options=WhisperOptions(language=language))
        load_s = time.perf_counter() - started
        after = gpu_memory_mb()
        transcriber.transcribe(rows[0].audio, PROMPT)  # warm-up
        per = []
        for row in rows:
            out = transcriber.transcribe(row.audio, PROMPT)
            verdict = judge(out)  # empty: ACE says "I didn't catch that"; unsure: "Did you say ...?"
            per.append({
                "key": row.key, "group": row.group, "reference": row.reference, "hypothesis": out.text,
                "wer": wer(row.reference, out.text), "cer": cer(row.reference, out.text),
                "lwer": lenient_wer(row.reference, out.text),
                "ms": out.elapsed_ms, "vad_ms": round(row.vad_ms), "audio_ms": out.duration_ms,
                "confidence": round(out.confidence, 3), "verdict": verdict.value,
                # only phrases the fast path understands today say something about commands
                "routable": decision(router, row.reference)[0] != "unknown",
                "same_command": verdict is not Verdict.EMPTY
                and decision(router, out.text) == decision(router, row.reference),
            })
        summary = {"label": label, "model": name, "language": language, "device": transcriber.device,
                   "compute": transcriber.compute_type, "load_s": round(load_s, 1),
                   "vram_mb": (after - before) if before is not None and after is not None else None}
        for group in ("english", "hinglish", "all"):
            items = [p for p in per if group == "all" or p["group"] == group]
            if not items:
                continue
            summary[f"{group}_wer"] = round(100 * sum(p["wer"][0] for p in items) / sum(p["wer"][1] for p in items), 1)
            summary[f"{group}_lwer"] = round(100 * sum(p["lwer"][0] for p in items) / sum(p["lwer"][1] for p in items), 1)
            summary[f"{group}_cer"] = round(100 * sum(p["cer"][0] for p in items) / sum(p["cer"][1] for p in items), 1)
            routable = [p for p in items if p["routable"]]
            summary[f"{group}_routable"] = len(routable)
            summary[f"{group}_command"] = (
                round(100 * sum(p["same_command"] for p in routable) / len(routable), 1) if routable else None
            )
        times = [p["ms"] for p in per]
        totals = sorted(p["ms"] + p["vad_ms"] for p in per)  # key released -> text (NFR-1)
        summary["median_ms"] = round(statistics.median(times))
        summary["p95_ms"] = round(sorted(times)[int(0.95 * (len(times) - 1))])
        summary["p95_total_ms"] = round(totals[int(0.95 * (len(totals) - 1))])
        summary["rtf"] = round(sum(times) / max(1, sum(p["audio_ms"] for p in per)), 3)
        for verdict in (Verdict.UNSURE, Verdict.EMPTY):
            share = sum(p["verdict"] == verdict.value for p in per) / len(per)
            summary[f"{verdict.value}_pct"] = round(100 * share, 1)
        results.append({"summary": summary, "utterances": per})
        print(json.dumps(summary))
        del transcriber
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8", newline="\n")  # LF, like the repo
    first = results[0]["summary"] if results else {}
    lines = ["# S10 STT benchmark", "",
             f"{len(rows)} recordings by {args.speaker} (audio kept local). WER / CER in %; HI WER~ = WER with Hinglish spelling variants "
             "forgiven (gaana / gana, chhota / chota, awaaz / avaaz); cmd % = "
             "the fast-path router makes the same decision as from the reference text, over the "
             f"{first.get('english_routable')} English / {first.get('hinglish_routable')} Hinglish "
             "phrases it understands today (a dropped transcript counts as wrong); asks % = "
             "\"Did you say ...?\" (confidence < 0.55); drops % = "
             "rejected by the guards (\"I didn't catch that\"); ms = transcription time per utterance; "
             "p95 total = VAD trim + transcription (NFR-1: ≤ 700 ms from the end of speech).", "",
             "| Config | Device | EN WER | HI WER | HI WER~ | HI CER | EN cmd % | HI cmd % | asks % | drops % "
             "| median ms | p95 ms | p95 total ms | RTF | VRAM MB |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["summary"]
        lines.append(f"| {s['label']} | {s['device']} {s['compute']} | {s.get('english_wer')} | "
                     f"{s.get('hinglish_wer')} | {s.get('hinglish_lwer')} | {s.get('hinglish_cer')} | {s.get('english_command')} | "
                     f"{s.get('hinglish_command')} | {s['unsure_pct']} | {s['empty_pct']} | "
                     f"{s['median_ms']} | {s['p95_ms']} | {s['p95_total_ms']} | {s['rtf']} | "
                     f"{s['vram_mb']} |")
    (args.out / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote RESULTS.md and results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
