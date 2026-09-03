# YouTube-Transcript-Extractor
A Python CLI tool to extract transcripts from YouTube videos

A **full-stack** application that extracts transcripts from **YouTube or almost
any other video platform**, then produces a **proper, well-structured summary**
with an optional **refined report** (overview, key points, highlights, action
items, stats).

## Stack

| Layer | Tech |
|---|---|
| Backend API | **FastAPI** (`app/`) |
| Frontend | **Next.js 14 / React** (`frontend/`) |
| Transcript engine | Python CLI + `youtube-transcript-api` + `yt-dlp` |
| Summarization | Built-in extractive (no keys) or OpenAI / Anthropic / Gemini LLM |

The original CLI still works exactly as before.

---

## Features

- **YouTube-first**: pulls official/manual subtitles instantly via
  `youtube-transcript-api` (no download needed).
- **Any platform**: uses `yt-dlp` to fetch subtitles from Vimeo, Twitter/X,
  Facebook, TED, Rumble, and many other sources.
- **Transcription fallback**: when a video has no subtitles, downloads the best
  audio and transcribes it with:
  - local OpenAI Whisper (free, offline),
  - or the OpenAI `whisper-1` API if `OPENAI_API_KEY` is set.
- **Local files**: transcribe or parse local `.mp4`, `.m4a`, `.mp3`, `.wav`,
  `.vtt`, `.srt`, or `.txt` files.
- **Web UI**: paste a URL or drop a file, choose summary mode and language,
  get a refined summary with tabs for the full transcript.
- **Summarisation**:
  - `extractive` — built-in frequency-based summarizer, no keys required.
  - `llm` — OpenAI, Anthropic, or Gemini summarization when a key is set.
  - `auto` — uses an LLM when available, otherwise extractive.
- **Refined output**: structured report with `overview`, `summary`,
  `key_points`, `highlights`, `action_items`, and `stats`.
- **CLI output**: plain text, Markdown, or JSON. Save to a file or print.

---

## Project structure

```
.
├── app/                        # FastAPI backend
│   ├── main.py                 # API routes (extract, extract/file, health)
│   ├── schemas.py              # Pydantic request/response models
│   └── core/
│       └── transcript.py       # Transcript + summary engine (reused by CLI)
├── frontend/                   # Next.js frontend
│   ├── app/
│   │   ├── page.js             # Main UI (URL + file upload, summary tabs)
│   │   ├── layout.js
│   │   └── globals.css
│   ├── next.config.mjs         # Proxies /api to FastAPI on :8000
│   └── package.json
├── extract_transcript.py       # CLI entrypoint (thin wrapper)
├── requirements.txt            # Backend dependencies
└── README.md
```

---

## Installation

### 1. Backend

```bash
cd YouTube-Transcript-Extractor
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Frontend

```bash
cd frontend
npm install
```

---

## Running the full stack

Open two terminals.

**Terminal 1 — backend:**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

Then open **http://localhost:3000**. The Next.js app proxies `/api/*` to the
FastAPI backend, so the browser never needs to call `127.0.0.1` directly.

API docs are available at **http://localhost:8000/docs**.

---

## Web UI usage

1. Paste a YouTube / any-platform URL **or** drop a local
   audio/video/subtitle file.
2. Choose **Summary mode**:
   - `Auto` (LLM if a key is set, otherwise extractive)
   - `Local extractive` (no keys needed)
   - `LLM` (requires `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`)
3. Enable **Refined summary** for a structured report.
4. Click **Extract & summarize**.
5. Switch between **Summary** and **Transcript** tabs.

---

## CLI usage

The original CLI is still available:

```bash
# Basic (works immediately, no keys)
python extract_transcript.py "https://www.youtube.com/watch?v=VIDEO_ID" --refine

# Save a polished Markdown report
python extract_transcript.py "https://youtu.be/VIDEO_ID" --refine --output-format markdown --save report.md

# Any other platform
python extract_transcript.py "https://vimeo.com/123456789" --refine

# Local file
python extract_transcript.py ./meeting.m4a --platform file --refine

# LLM-powered summary
OPENAI_API_KEY=sk-... python extract_transcript.py "https://youtu.be/VIDEO_ID" --summary-mode llm --refine
```

---

## API reference

### `POST /api/extract`

Extract + summarize a video from a URL or YouTube ID.

```json
{
  "url": "https://youtu.be/VIDEO_ID",
  "summary_mode": "auto",
  "refine": true,
  "summary_language": "English",
  "languages_input": "en,en-US,en-GB,en-orig,eng"
}
```

### `POST /api/extract/file`

`multipart/form-data` file upload (audio/video/subtitle). Supports the same
summary options as extra fields.

### `GET /api/health`

Simple liveness check.

### `GET /`

Service metadata.

### Response shape

```json
{
  "meta": {
    "source": "youtube",
    "title": "...",
    "url": "...",
    "language": "en",
    "is_auto_caption": false,
    "word_count": 1234,
    "segment_count": 120
  },
  "segments": [
    {"start": 0.0, "end": 3.2, "duration": 3.2, "text": "..."}
  ],
  "full_text": "...",
  "summary": {
    "type": "refined",
    "overview": "...",
    "summary": "...",
    "key_points": ["..."],
    "highlights": ["..."],
    "action_items": ["..."],
    "stats": {"word_count": 1234, "...": "..."}
  },
  "refined": true,
  "summary_method": "extractive",
  "warnings": []
}
```

---

## Optional extras

LLM-powered summaries (pick at least one):

```bash
pip install openai          # or
pip install anthropic       # or
pip install google-generativeai
```

Fully local transcription (heavy; also needs ffmpeg on PATH):

```bash
pip install openai-whisper
```

[ffmpeg](https://ffmpeg.org/download.html) is required only when downloading
audio for transcription.

---

## Troubleshooting

- **`No transcript available` on YouTube** — Some videos disable captions; the
  tool falls back to `yt-dlp` and then to audio transcription.
- **Audio transcription needs `ffmpeg`** — Install ffmpeg and make sure it is on
  your `PATH` (e.g. `sudo apt install ffmpeg` on Debian/Ubuntu).
- **`--summary-mode llm` says no provider configured** — Set `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`.
- **`/api` calls fail from the browser** — Make sure the FastAPI backend is
  running on port `8000` and the Next.js frontend on port `3000`.

---

## Notes

- This tool is for personal, educational, and fair-use analytics. Respect the
  terms of service of the video platform and the copyright of the content you
  summarise.
- The local Whisper path is computationally heavy and is optional; the OpenAI
  `whisper-1` API path is lighter if you already have an API key.