#!/usr/bin/env python3
"""Move + rename clips into the content library based on match results.

Reads:
    state/manifest.json
    state/matches/<md5>.json   (one per clip)
    state/transcripts/<md5>.json
Writes:
    <library>/<topic>/<shot-type>/<topic>-<shot-type>-NN.mp4
    <library>/_review/{unmatched,no-audio}/...
    state/organize.json  (placement decisions, used by report.py)

Usage:
    python organize.py --output /path/to/library [--dry-run] [--copy]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

AUTO_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.60
SHOT_TYPES = {"a-roll", "b-roll", "talking-head", "misc"}
SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify(s: str) -> str:
    return SLUG_RE.sub("-", s.lower()).strip("-") or "misc"


def load_state(state_dir: Path) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    manifest = json.loads((state_dir / "manifest.json").read_text())
    matches: dict[str, dict] = {}
    for mf in (state_dir / "matches").glob("*.json"):
        data = json.loads(mf.read_text())
        if data.get("md5"):
            matches[data["md5"]] = data
    transcripts: dict[str, dict] = {}
    for tf in (state_dir / "transcripts").glob("*.json"):
        data = json.loads(tf.read_text())
        if data.get("md5"):
            transcripts[data["md5"]] = data
    return manifest["clips"], matches, transcripts


def next_sequence(folder: Path, prefix: str) -> int:
    if not folder.exists():
        return 1
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)\.[a-z0-9]+$", re.IGNORECASE)
    used = []
    for p in folder.iterdir():
        m = pat.match(p.name)
        if m:
            used.append(int(m.group(1)))
    return (max(used) + 1) if used else 1


def place_clip(
    src: Path, library: Path, topic: str, shot_type: str,
    dry_run: bool, copy: bool,
) -> Path:
    topic_slug = slugify(topic)
    shot_slug = shot_type if shot_type in SHOT_TYPES else "misc"
    dest_dir = library / topic_slug / shot_slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{topic_slug}-{shot_slug}"
    seq = next_sequence(dest_dir, prefix)
    dest = dest_dir / f"{prefix}-{seq:02d}{src.suffix.lower()}"
    if dry_run:
        return dest

    op = shutil.copy2 if copy else shutil.move
    op(str(src), str(dest))
    return dest


def place_review(src: Path, library: Path, bucket: str,
                 dry_run: bool, copy: bool) -> Path:
    dest_dir = library / "_review" / bucket
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}__{counter}{src.suffix}"
        counter += 1
    if dry_run:
        return dest
    (shutil.copy2 if copy else shutil.move)(str(src), str(dest))
    return dest


def run(library: Path, state_dir: Path, dry_run: bool, copy: bool) -> None:
    clips, matches, transcripts = load_state(state_dir)
    decisions: list[dict] = []

    for clip in clips:
        md5 = clip.get("md5")
        src = Path(clip["path"])
        decision = {
            "md5": md5, "original_filename": clip.get("filename"),
            "source_path": clip.get("path"),
        }

        # Ingest-stage failures already routed (corrupt/duplicate).
        if not clip.get("valid"):
            decision.update(status="skipped-by-ingest", reason=clip.get("error"))
            decisions.append(decision)
            continue

        if not src.exists():
            decision.update(status="missing-on-disk")
            decisions.append(decision)
            continue

        tr = transcripts.get(md5, {})
        if tr and tr.get("has_speech") is False:
            dest = place_review(src, library, "no-audio", dry_run, copy)
            decision.update(status="no-audio", new_path=str(dest),
                            topic="-", shot_type="-", confidence=0.0)
            decisions.append(decision)
            continue

        m = matches.get(md5)
        if not m:
            dest = place_review(src, library, "unmatched", dry_run, copy)
            decision.update(status="no-match-record", new_path=str(dest),
                            topic="-", shot_type="-", confidence=0.0)
            decisions.append(decision)
            continue

        conf = float(m.get("confidence") or 0.0)
        topic = m.get("matched_topic") or "_unmatched"
        shot_type = m.get("shot_type") or "misc"

        if topic == "_unmatched" or conf < REVIEW_THRESHOLD:
            dest = place_review(src, library, "unmatched", dry_run, copy)
            decision.update(status="unmatched", new_path=str(dest),
                            topic=topic, shot_type=shot_type, confidence=conf,
                            tags=m.get("tags", []), reason=m.get("reason"))
            decisions.append(decision)
            continue

        dest = place_clip(src, library, topic, shot_type, dry_run, copy)
        status = "auto-placed" if conf >= AUTO_THRESHOLD else "placed-needs-review"
        decision.update(status=status, new_path=str(dest),
                        topic=topic, shot_type=shot_type, confidence=conf,
                        tags=m.get("tags", []), reason=m.get("reason"))
        decisions.append(decision)

        print(f"[organize] {'[DRY] ' if dry_run else ''}{src.name} -> "
              f"{Path(dest).relative_to(library)} ({status}, conf={conf})")

    out = state_dir / "organize.json"
    out.write_text(json.dumps({"library": str(library), "decisions": decisions}, indent=2))
    print(f"[organize] wrote {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path, help="library root")
    ap.add_argument("--state", type=Path,
                    default=Path(__file__).resolve().parent.parent / "state")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--copy", action="store_true",
                    help="copy instead of move (safer first run)")
    args = ap.parse_args()
    run(args.output.resolve(), args.state.resolve(), args.dry_run, args.copy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
