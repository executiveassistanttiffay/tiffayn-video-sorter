#!/usr/bin/env python3
"""Generate content-database.csv and run-summary.json from state/."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean


CSV_HEADERS = [
    "original_filename", "new_filename", "topic", "shot_type",
    "confidence", "transcript_summary", "tags", "folder_path", "status",
]


def summarize_transcript(text: str, limit: int = 140) -> str:
    text = (text or "").strip().replace("\n", " ")
    return (text[: limit - 1] + "…") if len(text) > limit else text


def run(library: Path, state_dir: Path) -> None:
    organize = json.loads((state_dir / "organize.json").read_text())
    decisions = organize["decisions"]

    transcripts: dict[str, dict] = {}
    for tf in (state_dir / "transcripts").glob("*.json"):
        data = json.loads(tf.read_text())
        if data.get("md5"):
            transcripts[data["md5"]] = data

    csv_path = library / "content-database.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADERS)
        for d in decisions:
            md5 = d.get("md5") or ""
            tr = transcripts.get(md5, {})
            new_path = d.get("new_path") or ""
            new_filename = Path(new_path).name if new_path else ""
            folder_path = str(Path(new_path).parent) if new_path else ""
            w.writerow([
                d.get("original_filename", ""),
                new_filename or "_skipped",
                d.get("topic", "-"),
                d.get("shot_type", "-"),
                d.get("confidence", ""),
                summarize_transcript(tr.get("transcript", "")),
                ",".join(d.get("tags", []) or []),
                folder_path,
                d.get("status", ""),
            ])

    statuses = Counter(d.get("status", "") for d in decisions)
    confidences = [float(d["confidence"]) for d in decisions
                   if isinstance(d.get("confidence"), (int, float)) and d["confidence"] > 0]
    topics_found = sorted({d.get("topic") for d in decisions
                           if d.get("topic") and d["topic"] not in ("-", "_unmatched")})

    summary = {
        "run_date": date.today().isoformat(),
        "total_clips": len(decisions),
        "processed": statuses.get("auto-placed", 0) + statuses.get("placed-needs-review", 0),
        "flagged_review": statuses.get("placed-needs-review", 0) + statuses.get("unmatched", 0),
        "no_audio": statuses.get("no-audio", 0),
        "corrupted": sum(1 for d in decisions
                         if d.get("status") == "skipped-by-ingest"
                         and "ffprobe" in (d.get("reason") or "")),
        "duplicates": sum(1 for d in decisions
                          if d.get("status") == "skipped-by-ingest"
                          and "duplicate" in (d.get("reason") or "")),
        "unmatched": statuses.get("unmatched", 0),
        "topics_found": topics_found,
        "avg_confidence": round(mean(confidences), 3) if confidences else None,
        "status_breakdown": dict(statuses),
    }
    summary_path = library / "run-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"[report] wrote {csv_path}")
    print(f"[report] wrote {summary_path}")
    print(f"[report] summary: {json.dumps(summary, indent=2)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--state", type=Path,
                    default=Path(__file__).resolve().parent.parent / "state")
    args = ap.parse_args()
    run(args.output.resolve(), args.state.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
