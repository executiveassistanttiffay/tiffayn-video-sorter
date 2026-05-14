---
description: End-to-end pipeline that turns a folder of raw clips into a structured content library (ingest → transcribe → match → organize → report).
argument-hint: --input <raw-folder> --output <library-folder> [--copy] [--dry-run] [--limit N]
---

You are the orchestrator for Tiffany's video sorting pipeline. The user is running `/video-organizer $ARGUMENTS`.

## Step 0 — parse args
Required: `--input <dir>`, `--output <dir>`
Optional: `--copy` (safer first run — copy instead of move), `--dry-run`, `--limit N` (smoke test).

If `--input` or `--output` is missing, stop and ask the user.

## Step 1 — ingest
```bash
.venv/bin/python scripts/ingest.py --input <INPUT> --output <OUTPUT>
```
Verify `state/manifest.json` exists and has > 0 valid clips. If 0 valid clips, stop and report.

## Step 2 — transcribe
```bash
.venv/bin/python scripts/transcribe.py --model medium --language en [--limit N]
```
This is the slowest step. Idempotent — already-transcribed clips are skipped.

## Step 3 — discover topics (only if topics.json missing or empty)
If `topics.json` does not exist or has `"topics": []`, spawn the `topic-discoverer` subagent. It reads all transcripts and writes `topics.json`.

Skip this step if `topics.json` already has a populated topics array.

## Step 4 — match + classify
Spawn `matcher` subagents in batches of 10 transcripts.

Pseudocode:
1. List `state/transcripts/*.json` filtered to those WITHOUT a corresponding `state/matches/<md5>.json`.
2. Chunk into batches of 10.
3. For each batch, spawn one `matcher` subagent with the explicit list of transcript paths to process. The subagent writes `state/matches/<md5>.json` per clip.
4. You can spawn multiple matcher batches in parallel (single message, multiple Agent calls) — up to 4 in flight.

## Step 5 — organize
```bash
.venv/bin/python scripts/organize.py --output <OUTPUT> [--copy] [--dry-run]
```
Reads manifest + matches + transcripts; moves clips into final folders. Writes `state/organize.json`.

## Step 6 — report
```bash
.venv/bin/python scripts/report.py --output <OUTPUT>
```
Produces `<OUTPUT>/content-database.csv` and `<OUTPUT>/run-summary.json`.

## Final output to user
A short summary:
- total clips, processed, flagged, no-audio, unmatched, duplicates, corrupted
- average confidence
- path to `content-database.csv`

## Rules
- Run every step from the project root: `/Users/admin/Projects/TiffanyParra/video-sorting/`
- ALWAYS use `.venv/bin/python` (never system python).
- If any step fails, report the failure and stop — do not try to recover automatically.
- Be terse in your status updates: one line per step start, one line per step finish.
- Keep API/credit usage minimal: do not re-spawn `topic-discoverer` if `topics.json` is populated; do not re-spawn `matcher` for clips that already have a match file.
