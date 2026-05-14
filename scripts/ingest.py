#!/usr/bin/env python3
"""Ingest raw video clips: validate with ffprobe, hash for dedupe, emit manifest.

Usage:
    python ingest.py --input /path/to/raw --output /path/to/library
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
SHORT_CLIP_THRESHOLD_SEC = 3.0


@dataclass
class ClipMeta:
    path: str
    filename: str
    size_bytes: int
    md5: str
    duration_sec: float | None
    codec: str | None
    valid: bool
    short_clip: bool
    error: str | None = None


def md5_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def ffprobe(path: Path) -> tuple[float | None, str | None, str | None]:
    """Return (duration_sec, codec, error)."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name:format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, timeout=30, check=True,
        )
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0)) or None
        codec = (data.get("streams") or [{}])[0].get("codec_name")
        return duration, codec, None
    except subprocess.CalledProcessError as e:
        return None, None, f"ffprobe-failed: {e.stderr.strip()[:200]}"
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        return None, None, f"ffprobe-error: {type(e).__name__}: {e}"


def scan(input_dir: Path) -> list[Path]:
    return sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def move_to_review(src: Path, library: Path, bucket: str) -> Path:
    dest_dir = library / "_review" / bucket
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}__{counter}{src.suffix}"
        counter += 1
    shutil.move(str(src), str(dest))
    return dest


def run(input_dir: Path, library: Path, state_dir: Path, move_dupes_corrupt: bool) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    library.mkdir(parents=True, exist_ok=True)

    files = scan(input_dir)
    if not files:
        print(f"[ingest] no video files found in {input_dir}", file=sys.stderr)

    seen_hashes: dict[str, str] = {}
    manifest: list[ClipMeta] = []

    for fp in files:
        print(f"[ingest] {fp.name}")
        try:
            digest = md5_of(fp)
        except OSError as e:
            print(f"[ingest]   read-error: {e}", file=sys.stderr)
            continue

        duration, codec, err = ffprobe(fp)
        if err is not None:
            print(f"[ingest]   {err}", file=sys.stderr)
            if move_dupes_corrupt:
                move_to_review(fp, library, "corrupted")
            manifest.append(ClipMeta(
                path=str(fp), filename=fp.name, size_bytes=fp.stat().st_size if fp.exists() else 0,
                md5=digest, duration_sec=None, codec=None, valid=False, short_clip=False, error=err,
            ))
            continue

        if digest in seen_hashes:
            print(f"[ingest]   duplicate of {seen_hashes[digest]}")
            if move_dupes_corrupt:
                move_to_review(fp, library, "duplicates")
            manifest.append(ClipMeta(
                path=str(fp), filename=fp.name, size_bytes=fp.stat().st_size if fp.exists() else 0,
                md5=digest, duration_sec=duration, codec=codec, valid=False,
                short_clip=False, error=f"duplicate-of:{seen_hashes[digest]}",
            ))
            continue
        seen_hashes[digest] = fp.name

        short = bool(duration is not None and duration < SHORT_CLIP_THRESHOLD_SEC)
        manifest.append(ClipMeta(
            path=str(fp), filename=fp.name, size_bytes=fp.stat().st_size,
            md5=digest, duration_sec=duration, codec=codec, valid=True,
            short_clip=short, error=None,
        ))

    manifest_path = state_dir / "manifest.json"
    manifest_path.write_text(json.dumps(
        {"input_dir": str(input_dir), "library": str(library),
         "clips": [asdict(c) for c in manifest]},
        indent=2,
    ))
    print(f"[ingest] wrote {manifest_path} ({sum(1 for c in manifest if c.valid)}/{len(manifest)} valid)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path, help="content library root")
    ap.add_argument("--state", type=Path, default=None,
                    help="state dir (default: <script>/../state)")
    ap.add_argument("--no-move", action="store_true",
                    help="do not move duplicates/corrupt files; just log them")
    args = ap.parse_args()

    state_dir = args.state or (Path(__file__).resolve().parent.parent / "state")
    run(args.input.resolve(), args.output.resolve(), state_dir.resolve(),
        move_dupes_corrupt=not args.no_move)
    return 0


if __name__ == "__main__":
    sys.exit(main())
