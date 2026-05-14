# Video Sorter

Turn a folder of raw DSLR clips into a structured content library with topic folders, A-roll/B-roll split, renamed files, and a CSV index — automatically.

## Two ways to use this

**Easy — Google Colab (no install needed)** → see [`colab/README.md`](colab/README.md)
Recommended if your clips already live in Google Drive. Free, runs on Colab's GPU, costs $0 per run.

**Local — runs on your Mac** → continue reading below
For when you want clips processed on your own machine.

---

## Local pipeline overview

## What it does

1. **Ingest** — `ffprobe` validates clips, MD5 detects duplicates.
2. **Transcribe** — local OpenAI Whisper produces per-clip JSON transcripts.
3. **Discover topics** — one-time taxonomy build from your transcripts (only on first run).
4. **Match + classify** — Claude (Haiku) assigns topic + shot type per clip.
5. **Organize** — files renamed and moved into `{topic}/{shot-type}/`.
6. **Report** — `content-database.csv` + `run-summary.json` at the library root.

## Setup (already done in this repo)

```bash
cd video-sorting
python3 -m venv .venv
.venv/bin/pip install openai-whisper
brew install ffmpeg   # if not already installed
```

## Run it

From inside the Claude Code session at the repo root:

```
/video-organizer --input /path/to/raw-footage --output /path/to/content-library
```

First-run flags:
- `--copy` (recommended) — copies instead of moves, leaves originals intact
- `--dry-run` — show the plan without touching files
- `--limit 5` — transcribe only the first 5 clips (smoke test)

## Manual operation (without the slash command)

```bash
cd video-sorting
.venv/bin/python scripts/ingest.py     --input /raw --output /library
.venv/bin/python scripts/transcribe.py --model medium --language en
# (one-time) spawn topic-discoverer subagent → writes topics.json
# (batched)  spawn matcher subagent for each batch of 10 transcripts
.venv/bin/python scripts/organize.py   --output /library --copy
.venv/bin/python scripts/report.py     --output /library
```

## Output structure

```
/library/
├── e-commerce/
│   ├── a-roll/    e-commerce-a-roll-01.mp4 ...
│   └── b-roll/    e-commerce-b-roll-01.mp4 ...
├── ai-tools/
├── business-automation/
├── _review/
│   ├── unmatched/      # confidence < 0.60
│   ├── no-audio/       # silent clips
│   ├── duplicates/     # MD5 matches
│   └── corrupted/      # ffprobe failed
├── content-database.csv
└── run-summary.json
```

## Re-running

Safe — everything is idempotent. Already-transcribed clips are skipped via MD5 cache in `state/transcripts/`. To force a fresh run, delete the relevant files in `state/`.

## Tuning

- Slow transcription? Switch to `--model small` in `transcribe.py` (faster, slightly less accurate).
- Too many unmatched? Edit `topics.json` to add/refine topic descriptions, then delete `state/matches/` and re-run.
- Confidence thresholds live in `scripts/organize.py` (`AUTO_THRESHOLD`, `REVIEW_THRESHOLD`).
