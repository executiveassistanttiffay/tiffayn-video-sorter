# Tiffany Video Sorter — Colab Quick Start

Sort multi-GB videos in Google Drive without downloading anything to your computer. Costs $0 per run.

## Prerequisites (one-time)

- A Google account with the raw clips already uploaded to a Drive folder
- A Claude account (the same one your Claude Code subscription is on)
- Nothing installed on your computer

## Setup (3 minutes the first time, then under a minute per shoot)

### 1. Open the notebook in Colab

- Go to https://colab.research.google.com/
- File → Upload notebook → pick `tiffany_video_sorter.ipynb`

### 2. Switch to GPU

Runtime → Change runtime type → **T4 GPU** → Save. (Free tier includes this.)

### 3. Paste your Drive folder URL

In Drive, open the folder containing your raw clips and copy the URL from the browser address bar — it looks like `https://drive.google.com/drive/folders/abc123...`.

In the notebook, find the **Step 4 — Configuration** cell and replace `PASTE_DRIVE_FOLDER_URL_HERE`.

### 4. (Recommended) Leave smoke-test mode on for the first run

In that same Step 4 cell, you'll see:

```python
TEST_LIMIT = 3
```

This processes only the first 3 clips so you can sanity-check the result before letting it loose on the whole folder. After the smoke test looks good, change to `TEST_LIMIT = None` and re-run.

### 5. Run all cells

Runtime → Run all.

You'll be prompted twice during the run:

- **Step 3 — Claude Code login.** A URL appears. Open it in a new tab, sign in with your Claude account, copy the code shown, paste it into the input box at the bottom of the cell, press Enter.
- **Step 5 — Google Drive login.** Colab pops a Google account picker. Choose the account that owns your Drive.

Everything else is automatic.

## What happens during the run

Per clip:
1. Streams the video through Colab's network (Google-to-Google, fast even for multi-GB)
2. Extracts only the audio (a few MB) — the video bytes are then discarded
3. Whisper transcribes the audio on the free Colab GPU
4. Your Claude Code subscription classifies the transcript (topic, A-roll/B-roll, tags)
5. The Drive API moves the video into the matching folder (metadata only — instant, no upload)
6. The renamed file keeps the original at the end, e.g. `ai-tools-a-roll-03__C2004.mp4`

After all clips finish, a single Google Doc named **All Transcripts** is created next to the sorted library, containing every clip's transcript with headers.

## What you'll see in Drive afterward

```
<your parent folder>/
├── <your raw folder>/        (files moved out)
├── Sorted Library/
│   ├── a-roll/
│   │   ├── ai-tools/
│   │   ├── e-commerce/
│   │   ├── ...auto-discovered...
│   │   └── general/
│   ├── b-roll/
│   │   ├── ai-tools/
│   │   └── general/          ← reusable cutaways
│   ├── _review/
│   │   ├── unmatched/        ← confidence < 0.60
│   │   └── no-audio/         ← silent clips
│   └── _state/               ← cache (do not delete)
└── All Transcripts (Google Doc)
```

## Re-running

Safe and idempotent — re-run any time. Already-processed clips are skipped via the `_state/` cache. To force a fresh re-classify, delete `_state/` in Drive before re-running.

To process newly uploaded clips: just upload to the same raw folder and re-run all cells.

## Tweaking results

- **Slow on huge folder?** Lower `WHISPER_MODEL` from `medium` to `small` in Step 4. Faster, slightly less accurate.
- **Too many `_review/unmatched/`?** Open `_state/topics.json` in Drive, refine the topic descriptions, delete the matching `_state/<fileId>.json` files for the misses, re-run.
- **Reset everything:** Delete `Sorted Library/` in Drive. The next run rebuilds it from scratch.

## Troubleshooting

**Step 2 fails on `npm install -g @anthropic-ai/claude-code`**
The Colab base image sometimes has stale npm. Re-run the cell — second attempt usually works.

**Step 3 hangs without a prompt**
Click inside the cell's output area and start typing — Colab's interactive input box is sometimes hidden until focused. If still stuck, restart the runtime (Runtime → Restart) and run the cells again.

**Step 3 says "not authenticated" on the sanity check**
The login didn't complete. Re-run the cell.

**Step 5 says "Insufficient Permission"**
On the Google login pop-up, make sure you grant Drive **AND** Docs access. If you accidentally denied, run `auth.authenticate_user(force_remount=True)` in a fresh cell.

**A specific clip errors out**
The batch loop catches per-clip errors and continues. Failed clips don't get a `_state/<id>.json` entry, so they'll be retried on the next run. Check the cell output for the file name + error.

**Whisper out-of-memory on a long clip**
Try `WHISPER_MODEL = 'small'`. The Colab free T4 has 15 GB VRAM, which is normally enough — but very long clips can spike.

## What's NOT in this notebook (yet)

- Multi-language transcription (currently English only — change `LANGUAGE = 'en'` if needed; Whisper auto-detects when set to `None`)
- Manual topic curation (the seed list lives in `SEED_TOPICS`; rerunning will not remove auto-discovered topics)
- Undo (Drive's trash holds deleted folders for 30 days; the file moves are not destructive, just re-parenting)
