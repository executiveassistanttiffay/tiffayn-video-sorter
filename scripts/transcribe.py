#!/usr/bin/env python3
"""Transcribe clips listed in state/manifest.json using local Whisper.

Idempotent: skips clips that already have state/transcripts/<md5>.json.

Usage:
    python transcribe.py [--model medium] [--language en] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

NO_SPEECH_CONFIDENCE_THRESHOLD = 0.2  # avg word confidence below this → flag no_speech
MIN_TRANSCRIPT_CHARS = 8


def load_manifest(state_dir: Path) -> dict:
    mf = state_dir / "manifest.json"
    if not mf.exists():
        raise SystemExit(f"manifest not found: {mf} (run ingest.py first)")
    return json.loads(mf.read_text())


def word_confidence(segments: list[dict]) -> float | None:
    """Whisper exposes per-segment avg_logprob (negative); convert to a 0..1 proxy."""
    if not segments:
        return None
    probs = []
    for seg in segments:
        lp = seg.get("avg_logprob")
        if lp is None:
            continue
        # avg_logprob is typically in [-1.0, 0]; map to (0,1] via exp.
        import math
        probs.append(math.exp(lp))
    return round(statistics.mean(probs), 3) if probs else None


def transcribe_one(model, clip_path: Path, language: str | None) -> dict:
    """Run Whisper on one file, return the parsed schema."""
    kwargs = {"word_timestamps": True, "verbose": False}
    if language:
        kwargs["language"] = language

    t0 = time.time()
    result = model.transcribe(str(clip_path), **kwargs)
    elapsed = round(time.time() - t0, 2)

    segments = result.get("segments") or []
    text = (result.get("text") or "").strip()
    confidence = word_confidence(segments)
    has_speech = bool(text and len(text) >= MIN_TRANSCRIPT_CHARS and
                      (confidence is None or confidence >= NO_SPEECH_CONFIDENCE_THRESHOLD))

    words = []
    for seg in segments:
        for w in seg.get("words", []) or []:
            words.append({"word": w.get("word", "").strip(),
                          "start": round(float(w.get("start", 0)), 3),
                          "end": round(float(w.get("end", 0)), 3)})

    return {
        "file": clip_path.name,
        "language": result.get("language"),
        "duration_seconds": None,  # filled in by caller from manifest
        "has_speech": has_speech,
        "confidence": confidence,
        "transcript": text,
        "timestamps": words[:500],  # cap to keep files small
        "elapsed_sec": elapsed,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="medium",
                    choices=["tiny", "base", "small", "medium", "large-v3"])
    ap.add_argument("--language", default="en")
    ap.add_argument("--limit", type=int, default=None,
                    help="only transcribe first N pending clips (smoke test)")
    ap.add_argument("--state", type=Path,
                    default=Path(__file__).resolve().parent.parent / "state")
    args = ap.parse_args()

    state_dir: Path = args.state.resolve()
    transcripts_dir = state_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(state_dir)
    valid = [c for c in manifest["clips"] if c.get("valid")]
    pending = [c for c in valid if not (transcripts_dir / f"{c['md5']}.json").exists()]
    if args.limit:
        pending = pending[: args.limit]

    print(f"[transcribe] manifest={len(valid)} valid, pending={len(pending)} "
          f"(skipping {len(valid) - len(pending)} cached)")
    if not pending:
        return 0

    print(f"[transcribe] loading whisper model={args.model} (one-time, may take a minute)...")
    import whisper  # type: ignore
    model = whisper.load_model(args.model)

    for clip in pending:
        clip_path = Path(clip["path"])
        if not clip_path.exists():
            print(f"[transcribe]   missing on disk: {clip_path}", file=sys.stderr)
            continue
        try:
            schema = transcribe_one(model, clip_path, args.language)
        except Exception as e:  # whisper can raise on weird inputs
            print(f"[transcribe]   error on {clip_path.name}: {e}", file=sys.stderr)
            schema = {"file": clip_path.name, "has_speech": False, "confidence": None,
                      "transcript": "", "error": str(e)[:300]}
        schema["duration_seconds"] = clip.get("duration_sec")
        schema["md5"] = clip["md5"]

        out = transcripts_dir / f"{clip['md5']}.json"
        out.write_text(json.dumps(schema, indent=2))
        marker = "✓" if schema.get("has_speech") else "∅"
        conf = schema.get("confidence")
        print(f"[transcribe] {marker} {clip_path.name}  conf={conf}  "
              f"chars={len(schema.get('transcript') or '')}  t={schema.get('elapsed_sec')}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
