#!/usr/bin/env python3
"""
extract_transcript.py
=====================

CLI entrypoint for the transcript extractor.

The actual implementation lives in ``app.core.transcript``; this thin wrapper
keeps the original command-line interface:

    python extract_transcript.py "https://youtu.be/VIDEO_ID" --refine
"""

from app.core.transcript import main

if __name__ == "__main__":
    raise SystemExit(main())