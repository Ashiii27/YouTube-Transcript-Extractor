"""Pydantic models shared by the FastAPI backend."""

from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    """Request body for extracting a transcript from a video URL or YouTube id."""

    url: str = Field(..., description="Video URL or YouTube video id")
    platform: str = Field("auto", description="Input type: auto, youtube, or file")
    languages: Optional[List[str]] = Field(
        default=None,
        description="Caption languages to try, e.g. ['en', 'en-US']",
    )
    language: Optional[str] = Field(
        default=None,
        description="Transcription language hint used for audio / captions",
    )
    summary_language: str = Field("English", description="Language of the generated summary")
    summary_mode: str = Field(
        "auto",
        description="auto | extractive | llm",
    )
    refine: bool = Field(False, description="Produce a structured/refined summary")
    model: Optional[str] = Field(None, description="LLM model name (provider-specific)")
    whisper_model: str = Field("base", description="Local Whisper model size")
    max_sentences: int = Field(6, description="Sentences used by the extractive summarizer")
    languages_input: Optional[str] = Field(
        default=None,
        description="Comma separated caption languages (alternative to languages)",
    )


class SegmentSchema(BaseModel):
    start: Optional[float]
    end: Optional[float]
    duration: Optional[float]
    text: str


class TranscriptMeta(BaseModel):
    source: str
    title: str
    url: str
    language: str
    is_auto_caption: bool
    word_count: int
    segment_count: int


class ExtractResponse(BaseModel):
    meta: TranscriptMeta
    segments: List[SegmentSchema]
    full_text: str
    summary: Any
    refined: bool
    summary_method: str
    warnings: List[str] = Field(default_factory=list)


# pydantic v1/v2 compatibility
try:  # pragma: no cover
    from pydantic import ValidationError  # noqa: F401
except ImportError:  # pragma: no cover
    ValidationError = Exception  # type: ignore