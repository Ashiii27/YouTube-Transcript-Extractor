# YouTube-Transcript-Extractor

A Python CLI tool that extracts transcripts from **YouTube or almost any other
video platform** and then produces a **proper, well-structured summary** of the
content. It also has a **refined output** mode that turns a plain summary into an
organised report (overview, key points, highlights, action items, stats).

The tool works **out of the box** for YouTube captions and non-YouTube platforms
that expose subtitles. If no captions are available, it can download the audio
and transcribe it with a local Whisper install or the OpenAI `whisper-1` API.

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
- **Summarisation**:
  - `extractive` — built-in frequency-based summarizer, no keys required.
  - `llm` — OpenAI, Anthropic, or Gemini summarization when a key is set.
  - `auto` — uses an LLM when available, otherwise extractive.
- **Refined output**: structured report with `overview`, `summary`,
  `key_points`, `highlights`, `action_items`, and `stats`.
- **Flexible output**: plain text, Markdown, or JSON. Save to a file or print.

---

## Installation

```bash
cd YouTube-Transcript-Extractor
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional extras (comment/uncomment in `requirements.txt` or install directly):

```bash
# LLM-powered summaries (pick at least one)
pip install openai
# pip install anthropic
# pip install google-generativeai

# Fully local transcription (heavy; also needs ffmpeg on PATH)
pip install openai-whisper
```

[ffmpeg](https://ffmpeg.org/download.html) is required only when downloading
audio for transcription.

---

## Quick Start

### 1. Extract a transcript and get a summary

```bash
python extract_transcript.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

This prints the full transcript plus a summary. No API key is required because
the built-in extractive summarizer is used.

### 2. Get a refined, structured summary

```bash
python extract_transcript.py "https://youtu.be/dQw4w9WgXcQ" --refine
```

The refined report looks like:

```text
Refined Summary
================
<overview paragraph>

Key Points
----------
1. ...
2. ...

Action Items
------------
1. ...

Stats
-----
Word Count: 1240
Estimated Reading Minutes: 6.2
```

### 3. Use an LLM for better summaries

```bash
export OPENAI_API_KEY="sk-..."
python extract_transcript.py "https://youtu.be/dQw4w9WgXcQ" \
  --refine --summary-mode llm --output-format markdown --save summary.md
```

Supported providers (set the relevant env var):

| Provider | Env var | Notes |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | Uses `gpt-4o-mini` by default |
| Anthropic | `ANTHROPIC_API_KEY` | Uses `claude-3-5-haiku-latest` by default |
| Gemini | `GEMINI_API_KEY` | Uses `gemini-1.5-flash` by default |

### 4. Any other platform

```bash
python extract_transcript.py "https://vimeo.com/123456789" --refine
```

### 5. Transcribe a local file

```bash
# With local whisper installed
python extract_transcript.py ./meeting.m4a --platform file --refine

# Or with the OpenAI API (always available if you have a key)
OPENAI_API_KEY="sk-..." python extract_transcript.py ./meeting.mp3 --platform file
```

### 6. Parse a local subtitle file

```bash
python extract_transcript.py ./captions.srt --platform file --refine
```

---

## CLI Reference

```
python extract_transcript.py [URL] [options]

positional arguments:
  url                   Video URL or YouTube video id

options:
  -h, --help            show help
  --input, -i PATH      Local audio/video/subtitle file
  --platform {auto,youtube,file}
                        Input type (auto-detect by default)
  --languages LIST      Caption languages to try (default: en,en-US,en-GB,en-orig,eng)
  --language LANG       Transcription language hint
  --summary-language LANG
                        Language for the generated summary (default: English)
  --summary-mode {auto,extractive,llm}
                        auto = LLM if key exists, else local extractive
  --no-summary          Skip summary generation
  --refine              Output a structured/refined summary
  --output-format {text,markdown,json}
  --save PATH           Write output to a file
  --model NAME          LLM model name (provider-specific)
  --whisper-model SIZE  Local Whisper model size (default: base)
  --audio-dir PATH      Keep downloaded audio in this directory
  --max-summary-sentences N
                        Sentences used by the extractive summarizer
  --summary-only        Print only the summary (not the transcript)
  --verbose             Print progress messages to stderr
```

---

## Output Formats

### JSON

The JSON output is machine-readable and contains the transcript with timestamps
plus the (optionally refined) summary:

```json
{
  "transcript": {
    "title": "...",
    "url": "...",
    "language": "...",
    "word_count": 1234,
    "segments": [
      {"start": 0.0, "end": 3.2, "duration": 3.2, "text": "..."}
    ]
  },
  "summary": {
    "type": "refined",
    "overview": "...",
    "key_points": ["..."],
    "...": "..."
  },
  "summary_method": "llm",
  "refined": true
}
```

### Markdown

Produces a clean document with metadata, the full transcript, and the summary
sections — ideal for documentation or notes.

---

## How It Works

```
 URL / local file
        |
        v
 +---------------------+   youtube id?    +-----------------------+
 | youtube-transcript-  | ----------------> | fetch captions quickly |
 | api                  |                    +-----------------------+
 +---------------------+
        | (fallback / other platforms)
        v
   yt-dlp
   ├── subtitles? ──> parse VTT/SRT
   └── no subtitles ──> download audio ──> whisper / OpenAI whisper-1
        |
        v
   Transcript text
        |
        v
   Summary
   ├── extractive (offline, no keys)
   └── LLM (OpenAI / Anthropic / Gemini)
        |
        v
   Text / Markdown / JSON  (+ --refine structured report)
```

---

## Troubleshooting

- **`No transcript available` on YouTube** — Some videos disable captions; the
  tool falls back to `yt-dlp` and then to audio transcription.
- **Audio transcription needs `ffmpeg`** — Install ffmpeg and make sure it is on
  your `PATH` (e.g. `sudo apt install ffmpeg` on Debian/Ubuntu).
- **`--summary-mode llm` says no provider configured** — Set `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`.
- **Missing modules** — `pip install -r requirements.txt`, plus any optional
  extra you want to use.

---

## Notes

- This tool is for personal, educational, and fair-use analytics. Respect the
  terms of service of the video platform and the copyright of the content you
  summarise.
- The local Whisper path is computationally heavy and is optional; the OpenAI
  `whisper-1` API path is lighter if you already have an API key.
