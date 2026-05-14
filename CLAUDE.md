# Video Sorting — Project Memory

Pipeline that turns raw DSLR clips into a structured content library for Tiffany's YouTube channel.

## Entry point
`/video-organizer --input <raw-folder> --output <library-folder>`

## Architecture (hybrid)
- **Python scripts** (`scripts/`) — ingest, transcribe, organize, report. Deterministic and free.
- **Claude subagents** (`.claude/agents/`) — `topic-discoverer` (run once), `matcher` (Haiku 4.5, batches of 10).
- **Slash command** (`.claude/commands/video-organizer.md`) — orchestrator.

## Conventions
- Always use `.venv/bin/python` — never system python.
- Transcription model: `medium` (best speed/accuracy on M-series Mac, ~1× realtime).
- Confidence thresholds: ≥0.85 auto-place, 0.60–0.84 place + flag, <0.60 `_review/unmatched/`.
- Naming: `{topic-slug}-{shot-type}-{NN}.{ext}`, sequence per folder, lowercase only.
- State files keyed by MD5 (so re-runs are idempotent — no re-transcription).

## Rules
- Never edit clips in `state/transcripts/` — read-only artifacts.
- Never re-spawn `topic-discoverer` if `topics.json` has a populated `topics` array.
- Never re-spawn `matcher` for clips that already have `state/matches/<md5>.json`.
- First run on real footage: use `--copy` flag in `organize.py` (don't destroy originals).

## Cost control
LLM use is bounded: 1 `topic-discoverer` call per fresh library + 1 `matcher` call per 10 clips.
Whisper transcription is 100% local.

## Files
- `topics.json` — discovered taxonomy (root-level, persisted across runs)
- `state/manifest.json` — ingest output
- `state/transcripts/<md5>.json` — one per clip
- `state/matches/<md5>.json` — one per clip
- `state/organize.json` — placement decisions
- `<library>/content-database.csv` + `<library>/run-summary.json` — final outputs
