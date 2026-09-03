"""FastAPI backend for the Transcript Extractor full-stack app.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from .schemas import ExtractRequest, ExtractResponse, SegmentSchema, TranscriptMeta
from .core.transcript import (
    DEFAULT_LANGUAGES,
    Transcript,
    extract_transcript,
    gemini_available,
    summarize_transcript,
)

app = FastAPI(
    title="YouTube Transcript Extractor API",
    description=(
        "Extract transcripts from YouTube or almost any video platform and "
        "generate simple or refined summaries."
    ),
    version="1.0.0",
)

# The Next.js frontend speaks to this API through a relative /api proxy, but
# CORS is enabled so the two services can also be developed independently.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["health"])
def root() -> Dict[str, str]:
    return {"service": "YouTube Transcript Extractor API", "docs": "/docs"}


@app.get("/api/health", tags=["health"])
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "gemini_available": gemini_available(),
        "ai_provider": "Google Gemini" if gemini_available() else None,
    }


def _resolve_languages(request: ExtractRequest) -> Optional[List[str]]:
    if request.languages:
        return request.languages
    if request.languages_input:
        return [lang.strip() for lang in request.languages_input.split(",") if lang.strip()]
    return None


def _transcript_meta(transcript: Transcript) -> TranscriptMeta:
    return TranscriptMeta(
        source=transcript.source,
        title=transcript.title,
        url=transcript.url,
        language=transcript.language or "unknown",
        is_auto_caption=transcript.is_auto_caption,
        word_count=transcript.word_count,
        segment_count=len(transcript.segments),
    )


def _segments(transcript: Transcript) -> List[SegmentSchema]:
    return [
        SegmentSchema(
            start=seg.start,
            end=(seg.start + seg.duration)
            if (seg.start is not None and seg.duration is not None)
            else None,
            duration=seg.duration,
            text=seg.text,
        )
        for seg in transcript.segments
    ]


def _run_extract_and_summarize(
    params: Dict[str, Any],
) -> Tuple[Transcript, Any, str, List[str]]:
    extraction_keys = (
        "url",
        "input_path",
        "platform",
        "languages",
        "language_hint",
        "whisper_model",
    )
    extraction_params = {k: params[k] for k in extraction_keys if k in params}
    transcript = extract_transcript(**extraction_params)
    if not transcript.segments:
        raise ValueError("No transcript content was extracted.")
    summary, method, warnings = summarize_transcript(
        transcript,
        refine=bool(params.get("refine", False)),
        mode=str(params.get("summary_mode", "auto")),
        model=params.get("model"),
        language=str(params.get("summary_language", "English")),
        max_sentences=int(params.get("max_sentences", 6)),
    )
    return transcript, summary, method, warnings


def _build_response(
    transcript: Transcript,
    summary: Any,
    method: str,
    warnings: Optional[List[str]] = None,
) -> ExtractResponse:
    return ExtractResponse(
        meta=_transcript_meta(transcript),
        segments=_segments(transcript),
        full_text=transcript.text,
        summary=summary,
        refined=isinstance(summary, dict),
        summary_method=method,
        warnings=warnings or [],
    )


async def _extract_task(params: Dict[str, Any]) -> ExtractResponse:
    try:
        transcript, summary, method, warnings = await run_in_threadpool(
            _run_extract_and_summarize, params
        )
        return _build_response(transcript, summary, method, warnings)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/extract", response_model=ExtractResponse, tags=["extract"])
async def extract(request: ExtractRequest) -> ExtractResponse:
    """Extract + summarise a video from a URL/YouTube id."""
    params = {
        "url": request.url,
        "platform": request.platform,
        "languages": _resolve_languages(request),
        "language_hint": request.language,
        "whisper_model": request.whisper_model,
        "refine": request.refine,
        "summary_mode": request.summary_mode,
        "summary_language": request.summary_language,
        "model": request.model,
        "max_sentences": request.max_sentences,
    }
    return await _extract_task(params)


@app.post("/api/extract/file", response_model=ExtractResponse, tags=["extract"])
async def extract_file(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None, description="Language hint"),
    summary_language: str = Form(default="English"),
    summary_mode: str = Form(default="auto"),
    refine: bool = Form(default=False),
    whisper_model: str = Form(default="base"),
    max_sentences: int = Form(default=6),
    model: Optional[str] = Form(default=None),
) -> ExtractResponse:
    """Extract + summarise an uploaded audio/video/subtitle file."""
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        params = {
            "input_path": str(tmp_path),
            "platform": "file",
            "language_hint": language,
            "whisper_model": whisper_model,
            "refine": refine,
            "summary_mode": summary_mode,
            "summary_language": summary_language,
            "model": model,
            "max_sentences": max_sentences,
        }
        return await _extract_task(params)
    finally:
        tmp_path.unlink(missing_ok=True)