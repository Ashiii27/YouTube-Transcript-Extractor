#!/usr/bin/env python3
"""
extract_transcript.py
=====================

Extract transcripts from YouTube or almost any other video platform, then
produce either a simple or a "refined" (structured, polished) summary.

What it does
------------
1.  YouTube videos        -> uses ``youtube-transcript-api`` to grab captions
                             instantly (no download required).
2.  Other platforms       -> uses ``yt-dlp`` to fetch available subtitles
                             (VTT/SRT). If no subtitles exist, it downloads
                             the audio and transcribes it with either a local
                             Whisper install or the OpenAI ``whisper-1`` API.
3.  Local files           -> passes a local audio/video/subtitle file through
                             the same pipeline.
4.  Summarisation         -> uses Google Gemini (the only cloud AI used by this
                             project) when GEMINI_API_KEY is present, otherwise
                             falls back to a built-in extractive summarizer so
                             the tool always works out of the box. Long videos
                             are summarised in chunks (map-reduce).

Examples
--------
    # Youtube captions + extractive summary (no API key required)
    python extract_transcript.py "https://youtu.be/VIDEO_ID"

    # Structured, polished summary
    python extract_transcript.py "https://youtu.be/VIDEO_ID" --refine

    # Use a Google Gemini AI summary and save markdown/JSON
    GEMINI_API_KEY=AIza... python extract_transcript.py \
        https://youtu.be/VIDEO_ID --refine --summary-mode llm --save out.md

    # Any other platform (e.g. Vimeo/Facebook/TED) via yt-dlp
    python extract_transcript.py "https://vimeo.com/..." --refine

    # Transcribe a local file (local Whisper offline, or Gemini in the cloud)
    python extract_transcript.py ./meeting.m4a --platform file --refine

Requires (see requirements.txt): youtube-transcript-api, yt-dlp, google-genai;
optional: openai-whisper (fully offline local transcription).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_LANGUAGES = [
    "en",
    "en-US",
    "en-GB",
    "en-orig",
    "eng",
]

# Small built-in stopword list used by the fallback extractive summarizer.
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "could", "did", "do", "does", "doing",
    "down", "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs",
    "them", "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with", "would", "you",
    "your", "yours", "yourself", "yourselves", "shall", "may", "must", "im", "dont",
    "couldnt", "wouldnt", "shouldnt", "cant", "one", "two", "three", "get", "got",
    "go", "going", "know", "need", "like", "really", "okay", "ok", "yeah", "right",
    "well", "thing", "things", "look", "lot", "make", "let", "want", "say", "says",
    "see", "way", "use", "also", "even", "much", "many", "still", "find", "first",
    "time", "didnt", "even", "going", "im", "just", "kind", "want", "way", "see",
    "something", "maybe", "think", "going", "little", "around", "back", "also",
}

SUPPORTED_SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".txt"}


@dataclass
class TranscriptSegment:
    """One caption/text segment with an optional timestamp."""

    start: Optional[float]
    duration: Optional[float]
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": (self.start + self.duration)
            if (self.start is not None and self.duration is not None)
            else None,
            "duration": self.duration,
            "text": self.text,
        }


@dataclass
class Transcript:
    """The result of transcript extraction."""

    source: str = ""
    title: str = ""
    url: str = ""
    language: str = ""
    segments: List[TranscriptSegment] = field(default_factory=list)
    is_auto_caption: bool = False

    @property
    def text(self) -> str:
        return " ".join(seg.text for seg in self.segments).strip()

    @property
    def word_count(self) -> int:
        return len(_tokenize(self.text))


VERBOSE = False


def _log(message: str) -> None:
    if VERBOSE:
        print(f"[extract_transcript] {message}", file=sys.stderr)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def _clean_text(value: str) -> str:
    """Remove common VTT/HTML artifacts and collapse whitespace."""
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\[[^\]]*\]", "", value)
    value = value.replace("&nbsp;", " ").replace("&amp;", "&")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


# ---------------------------------------------------------------------------
# URL / platform helpers
# ---------------------------------------------------------------------------
def extract_youtube_id(value: str) -> Optional[str]:
    """Return a YouTube video id from a URL, or the value itself if it looks
    like a bare 11-character video id."""
    if not value:
        return None
    value = value.strip()
    patterns = [
        r"(?:v=|/v/|/embed/|/shorts/|youtu\.be/)([A-Za-z0-9_-]{6,50})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return None


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://", "http%", "www."))


def _detect_file_type(path: str) -> str:
    """Return 'subtitle' or 'media' based on the extension."""
    ext = Path(path).suffix.lower()
    if ext in SUPPORTED_SUBTITLE_EXTENSIONS:
        return "subtitle"
    return "media"


# ---------------------------------------------------------------------------
# YouTube transcript extraction
# ---------------------------------------------------------------------------
def _fetch_youtube_transcript(video_id: str, languages: List[str]) -> Transcript:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    ordered = list(languages) + ["en", "en-US", "en-GB", "en-orig"]
    tried: List[str] = []

    # New API surface (yt-transcript-api >= 0.6 / 1.x)
    if hasattr(api, "fetch"):
        # Prefer list() so we can tell manual captions apart from YouTube's
        # auto-generated ones (the fetched object itself does not always carry
        # that flag).
        try:
            available = api.list(video_id)
            for language in ordered:
                if language in tried:
                    continue
                tried.append(language)
                try:
                    transcript_ref = available.find_transcript([language])
                    fetched = transcript_ref.fetch()
                    segments = [
                        TranscriptSegment(
                            start=float(getattr(s, "start", 0.0)),
                            duration=float(getattr(s, "duration", 0.0) or 0.0),
                            text=_clean_text(getattr(s, "text", "")),
                        )
                        for s in fetched
                    ]
                    lang = (
                        getattr(fetched, "language_code", None)
                        or getattr(transcript_ref, "language_code", None)
                        or language
                    )
                    is_auto = bool(getattr(transcript_ref, "is_generated", False))
                    return _build_yt_transcript(video_id, lang, segments, is_auto)
                except Exception as exc:  # noqa: BLE001 - try next language
                    if "transcript not available" in str(exc).lower():
                        continue
                    _log(f"YouTube caption lookup for '{language}' failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - older 1.x without list()
            _log(f"YouTube transcript list() failed, trying direct fetch: {exc}")

        for language in ordered:
            if language in tried:
                continue
            tried.append(language)
            try:
                fetched = api.fetch(video_id, languages=[language])
                segments = [
                    TranscriptSegment(
                        start=float(getattr(s, "start", 0.0)),
                        duration=float(getattr(s, "duration", 0.0) or 0.0),
                        text=_clean_text(getattr(s, "text", "")),
                    )
                    for s in fetched
                ]
                lang = getattr(fetched, "language_code", None) or language
                is_auto = bool(getattr(fetched, "is_generated", False))
                return _build_yt_transcript(video_id, lang, segments, is_auto)
            except Exception as exc:  # noqa: BLE001 - try next language
                if "transcript not available" in str(exc).lower():
                    continue
                # Some errors (e.g. IP/consent) should not be silenced silently.
                _log(f"YouTube caption fetch for '{language}' failed: {exc}")
        raise RuntimeError("No transcript available for the requested languages")

    # Legacy API surface (youtube-transcript-api < 0.6)
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        for language in ordered:
            try:
                data = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
                segments = [
                    TranscriptSegment(
                        start=float(item.get("start", 0.0)),
                        duration=float(item.get("duration", 0.0) or 0.0),
                        text=_clean_text(item.get("text", "")),
                    )
                    for item in data
                ]
                return _build_yt_transcript(video_id, language, segments, False)
            except Exception as exc:  # noqa: BLE001
                if "transcript not available" in str(exc).lower():
                    continue
                _log(f"YouTube caption fetch for '{language}' failed: {exc}")
        raise RuntimeError("No transcript available for the requested languages")

    raise RuntimeError("youtube-transcript-api is too old; please upgrade it.")


def _build_yt_transcript(
    video_id: str,
    language: str,
    segments: List[TranscriptSegment],
    is_auto: bool,
) -> Transcript:
    return Transcript(
        source="youtube",
        title=f"YouTube video {video_id}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        language=language,
        segments=segments,
        is_auto_caption=is_auto,
    )


# ---------------------------------------------------------------------------
# yt-dlp based extraction (other platforms + YouTube fallback)
# ---------------------------------------------------------------------------
def _parse_timestamp(value: str) -> float:
    """Convert '00:01:02.345', '00:01:02,345', or '01:02.345' into seconds."""
    # Normalise SRT comma-milliseconds to a decimal point.
    value = value.replace(",", ".")
    parts = [float(p) for p in re.split(":", value) if p.strip() != ""]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] if parts else 0.0


def _parse_vtt(path: Path) -> List[TranscriptSegment]:
    content = Path(path).read_text(encoding="utf-8", errors="ignore")
    segments: List[TranscriptSegment] = []
    in_cue = False
    cue_text: List[str] = []
    start: Optional[float] = None
    end: Optional[float] = None

    def flush() -> None:
        nonlocal cue_text, start, end, in_cue
        if cue_text:
            segments.append(
                TranscriptSegment(
                    start=start,
                    duration=(end - start) if (start is not None and end is not None) else None,
                    text=_clean_text(" ".join(cue_text).replace("\n", " ")),
                )
            )
        cue_text = []
        start = end = None
        in_cue = False

    for raw in content.splitlines():
        line = raw.strip()
        if re.match(r"^WEBVTT", line) or line in ("Kind:", "Language:", "NOTE"):
            continue
        if "-->" in line:
            flush()
            match = re.match(r"(\S+)\s+-->\s+(\S+)", line)
            if match:
                start = _parse_timestamp(match.group(1))
                end = _parse_timestamp(match.group(2))
                in_cue = True
            continue
        if in_cue:
            if line == "":
                flush()
            elif not re.match(r"^(timestamp|caption|setting)\b", line, re.I):
                cue_text.append(line)
    flush()
    return [s for s in segments if s.text]


def _parse_srt(path: Path) -> List[TranscriptSegment]:
    content = Path(path).read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", content)
    segments: List[TranscriptSegment] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        timing_idx = None
        for idx, ln in enumerate(lines):
            if "-->" in ln:
                timing_idx = idx
                break
        if timing_idx is None:
            continue
        timing = lines[timing_idx]
        text = " ".join(lines[timing_idx + 1 :])
        if not text:
            continue
        match = re.match(r"(\S+)\s+-->\s+(\S+)", timing)
        if not match:
            continue
        start = _parse_timestamp(match.group(1))
        end = _parse_timestamp(match.group(2))
        segments.append(
            TranscriptSegment(start=start, duration=end - start, text=_clean_text(text))
        )
    return segments


def _parse_subtitle_file(path: Path) -> List[TranscriptSegment]:
    if path.suffix.lower() == ".srt":
        return _parse_srt(path)
    if path.suffix.lower() == ".vtt":
        return _parse_vtt(path)
    # Plain text transcript (one line per caption is enough).
    content = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    return [
        TranscriptSegment(start=idx * 3.0, duration=3.0, text=_clean_text(ln))
        for idx, ln in enumerate(lines)
    ]


def _download_subtitles_ytdlp(url: str, languages: List[str], temp_dir: Path) -> List[Path]:
    import yt_dlp

    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": languages,
        "subtitlesformat": "vtt",
        "outtmpl": str(temp_dir / "%(title)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    return sorted(temp_dir.glob("*.vtt")) + sorted(temp_dir.glob("*.srt"))


def _download_audio_ytdlp(url: str, temp_dir: Path, keep_audio: bool) -> Tuple[Path, str]:
    import yt_dlp

    ffmpeg = shutil.which("ffmpeg")
    postprocessors = []
    if ffmpeg:
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        )
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(temp_dir / "audio.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
    }
    if postprocessors:
        opts["postprocessors"] = postprocessors
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = (info or {}).get("title", "") if isinstance(info, dict) else ""
    candidates = sorted(
        list(temp_dir.glob("audio.*")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("yt-dlp could not download audio for this URL")
    audio_path = candidates[0]
    return audio_path, title or ""


def _gemini_api_key() -> Optional[str]:
    """Return the Google API key from the environment, if set."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def gemini_available() -> bool:
    """True when a Google API key is configured (AI summarization/transcription)."""
    return bool(_gemini_api_key())


def _get_gemini_client():
    """Create a google-genai client. Raises a helpful error when the SDK is
    not installed."""
    try:
        from google import genai  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "The 'google-genai' package is required for Google AI features. "
            "Install it with:  pip install google-genai"
        ) from exc
    return genai.Client(api_key=_gemini_api_key())


def _mime_type(audio_path: Path) -> str:
    suffix = audio_path.suffix.lower()
    return {
        ".mp3": "audio/mp3",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".mp4": "audio/mp4",
    }.get(suffix, "audio/mp3")


def _transcribe_with_gemini(
    audio_path: Path, language: Optional[str]
) -> List[TranscriptSegment]:
    """Transcribe audio/video with Google Gemini (cloud) and return segments
    with timestamps when the model provides them."""
    from google.genai import types  # type: ignore

    client = _get_gemini_client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    lang_line = f" The spoken language is {language}." if language else ""

    segment_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "segments": types.Schema(
                type=types.Type.ARRAY,
                description="Ordered transcript segments with timestamps",
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "start": types.Schema(
                            type=types.Type.NUMBER, description="Start time in seconds"
                        ),
                        "text": types.Schema(
                            type=types.Type.STRING, description="Spoken text"
                        ),
                    },
                    required=["start", "text"],
                ),
            )
        },
        required=["segments"],
    )

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    def _do_transcribe(use_schema: bool) -> Any:
        kwargs: Dict[str, Any] = {
            "model": model,
            "contents": [
                f"Transcribe the full spoken content of this media file{lang_line} "
                "Do not add commentary, timestamps in the prose, or any text "
                "other than the transcription. Provide the complete verbatim "
                "transcript ordered chronologically.",
                types.Part.from_bytes(data=audio_bytes, mime_type=_mime_type(audio_path)),
            ],
        }
        if use_schema:
            kwargs["config"] = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=segment_schema,
                temperature=0.1,
            )
        else:
            kwargs["config"] = types.GenerateContentConfig(temperature=0.1)
        return client.models.generate_content(**kwargs)

    try:
        response = _do_transcribe(True)
        parsed = _extract_json(getattr(response, "text", "") or "")
        raw_segments = (parsed or {}).get("segments") if parsed else None
        if raw_segments:
            segments = []
            for item in raw_segments:
                text = _clean_text(str(item.get("text", "")))
                if not text:
                    continue
                try:
                    start = float(item.get("start"))
                except (TypeError, ValueError):
                    start = None
                segments.append(TranscriptSegment(start=start, duration=None, text=text))
            if segments:
                return segments
    except Exception as exc:  # noqa: BLE001 - structured output not supported
        _log(f"Gemini structured transcription failed ({exc}); retrying as plain text.")

    response = _do_transcribe(False)
    raw_text = getattr(response, "text", "") or ""
    # Fall back to sentence-length chunks with estimated timestamps.
    sentences = _split_sentences(raw_text) or [raw_text.strip()]
    chunks = [s for s in sentences if s]
    duration = max(len(audio_bytes) / 16000.0, 1.0) if audio_bytes else 0.0
    per = duration / max(len(chunks), 1) if duration else 3.0
    return [
        TranscriptSegment(start=round(i * per, 2), duration=round(per, 2), text=chunk)
        for i, chunk in enumerate(chunks)
    ]


def _transcribe_audio(audio_path: Path, language: Optional[str], whisper_model: str) -> List[TranscriptSegment]:
    """Transcribe audio using local openai-whisper if available, otherwise
    Google Gemini (cloud, requires GEMINI_API_KEY / GOOGLE_API_KEY).

    Only Google models are used for cloud AI; local Whisper is an optional,
    fully offline open-source engine.
    """
    try:
        import whisper  # type: ignore

        _log(f"Transcribing with local Whisper (model='{whisper_model}')...")
        model = whisper.load_model(whisper_model)
        result = model.transcribe(str(audio_path), language=language)
        segments = []
        for seg in result.get("segments", []):
            segments.append(
                TranscriptSegment(
                    start=float(seg.get("start", 0.0)),
                    duration=float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)),
                    text=_clean_text(seg.get("text", "")),
                )
            )
        return segments
    except ImportError:
        pass

    if not gemini_available():
        raise RuntimeError(
            "No caption/subtitle and no transcription engine available. "
            "Either install local Whisper (`pip install openai-whisper`, fully "
            "offline) or set GEMINI_API_KEY to transcribe with Google Gemini."
        )

    _log("Transcribing with Google Gemini (cloud)...")
    return _transcribe_with_gemini(audio_path, language)


def _extract_with_ytdlp(
    url: str,
    languages: List[str],
    language_hint: Optional[str],
    whisper_model: str,
    keep_audio_dir: Optional[Path],
) -> Transcript:
    import yt_dlp

    with tempfile.TemporaryDirectory(prefix="ytex_") as temp_dir:
        temp = Path(temp_dir)
        title = ""
        info = {}
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(url, download=False) or {}
                title = info.get("title", "")
        except Exception as exc:  # noqa: BLE001
            _log(f"Could not read metadata with yt-dlp: {exc}")

        subtitle_files = _download_subtitles_ytdlp(url, languages, temp)
        if subtitle_files:
            all_segments: List[TranscriptSegment] = []
            chosen_lang = ""
            for f in subtitle_files:
                segments = _parse_vtt(f) if f.suffix == ".vtt" else _parse_srt(f)
                if segments and not all_segments:
                    all_segments = segments
                    chosen_lang = f.stem.split(".")[-1] if "." in f.name else ""
                elif all_segments:
                    # Prefer the first non-empty English caption file.
                    break
            if all_segments:
                return Transcript(
                    source=info.get("extractor_key", "yt-dlp"),
                    title=title or url,
                    url=url,
                    language=chosen_lang or "unknown",
                    segments=all_segments,
                    is_auto_caption=True,
                )

        _log("No usable subtitles found; downloading audio for transcription...")
        audio_path, audio_title = _download_audio_ytdlp(url, temp, keep_audio=keep_audio_dir is not None)
        segments = _transcribe_audio(audio_path, language_hint, whisper_model)

        # Persist audio if requested.
        if keep_audio_dir:
            keep_audio_dir.mkdir(parents=True, exist_ok=True)
            target = keep_audio_dir / audio_path.name
            shutil.copy2(audio_path, target)
            _log(f"Audio kept at {target}")

        return Transcript(
            source=info.get("extractor_key", "yt-dlp"),
            title=title or audio_title or url,
            url=url,
            language=language_hint or "unknown",
            segments=segments,
            is_auto_caption=True,
        )


# ---------------------------------------------------------------------------
# Main extraction dispatcher
# ---------------------------------------------------------------------------
def extract_transcript(
    url: Optional[str] = None,
    input_path: Optional[str] = None,
    platform: str = "auto",
    languages: Optional[List[str]] = None,
    language_hint: Optional[str] = None,
    whisper_model: str = "base",
    keep_audio_dir: Optional[Path] = None,
) -> Transcript:
    languages = languages or DEFAULT_LANGUAGES
    platform = (platform or "auto").lower()

    # Local file input
    if platform == "file" or (input_path and not is_url(input_path or "")):
        path = Path(input_path or "").expanduser()
        if not input_path or not path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path or '(none)'}")
        kind = _detect_file_type(str(path))
        if kind == "subtitle":
            segments = _parse_subtitle_file(path)
            return Transcript(
                source="local-file",
                title=path.name,
                url=str(path),
                language=language_hint or "",
                segments=segments,
            )
        segments = _transcribe_audio(path, language_hint, whisper_model)
        return Transcript(
            source="local-file",
            title=path.name,
            url=str(path),
            language=language_hint or "",
            segments=segments,
        )

    # URL input
    if not url:
        raise ValueError("No URL or input file provided.")

    youtube_id = extract_youtube_id(url)
    if platform == "youtube" or (platform == "auto" and youtube_id):
        try:
            transcript = _fetch_youtube_transcript(youtube_id, languages)
            # Try to enrich the title via yt-dlp when available.
            try:
                transcript.title = _ytdlp_title(f"https://www.youtube.com/watch?v={youtube_id}")
            except Exception:  # noqa: BLE001
                pass
            return transcript
        except Exception as exc:  # noqa: BLE001
            _log(f"YouTube caption path failed ({exc}); falling back to yt-dlp.")
            fallback_url = (
                f"https://www.youtube.com/watch?v={youtube_id}"
                if not is_url(url)
                else url
            )
            return _extract_with_ytdlp(
                fallback_url, languages, language_hint, whisper_model, keep_audio_dir
            )

    return _extract_with_ytdlp(url, languages, language_hint, whisper_model, keep_audio_dir)


def _ytdlp_title(url: str) -> str:
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
        return (ydl.extract_info(url, download=False) or {}).get("title", "")


# ---------------------------------------------------------------------------
# Summarisation
# ---------------------------------------------------------------------------
def _split_sentences(text: str) -> List[str]:
    text = _clean_text(text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 1]


def _words(sentence: str) -> List[str]:
    return [w for w in _tokenize(sentence) if w not in STOPWORDS and len(w) > 1]


def _extractive_summary(text: str, max_sentences: int = 6, max_chars: int = 1800) -> str:
    """Simple frequency-based extractive summarizer (no external models)."""
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    freq = Counter()
    for sent in sentences:
        for word in _words(sent):
            freq[word] += 1
    if not freq:
        return " ".join(sentences)[:max_chars]

    scored = []
    for idx, sent in enumerate(sentences):
        words = _words(sent)
        score = sum(freq.get(w, 0) for w in words) / max(len(words), 1)
        # Slightly reward the first sentence (often the thesis).
        if idx == 0:
            score *= 1.1
        scored.append((idx, score, sent))

    scored.sort(key=lambda x: (x[1], -x[0]), reverse=True)
    chosen = sorted([x[0] for x in scored[:max_sentences]])
    selected = [sentences[idx] for idx in chosen]
    summary = " ".join(selected)
    return summary[:max_chars]


def _heuristic_refined_summary(transcript: Transcript, abstract: str) -> Dict[str, Any]:
    """Turn a plain extractive summary into a structured, refined report."""
    sentences = _split_sentences(transcript.text) or [""]
    key_points = [s for s in _split_sentences(abstract) if s][:6]
    if not key_points and sentences:
        key_points = sentences[:3]

    action_markers = ("should", "need to", "must", "remember", "don't forget",
                      "we need", "you should", "make sure", "let's", "next step",
                      "action", "todo", "follow up")
    action_items = [
        s for s in sentences
        if any(m in s.lower() for m in action_markers) and len(s) < 350
    ][:6]

    quotes = [s for s in sentences if re.search(r'["«»“”]', s)][:4]

    return {
        "type": "refined",
        "title": transcript.title or "Untitled video",
        "source": transcript.source,
        "url": transcript.url,
        "overview": (sentences[0] if sentences else "No summary available."),
        "summary": abstract,
        "key_points": key_points,
        "action_items": action_items or ["No explicit action items detected."],
        "highlights": quotes or ["No direct quotes detected."],
        "stats": {
            "word_count": transcript.word_count,
            "char_count": len(transcript.text),
            "estimated_reading_minutes": round(max(transcript.word_count / 200, 0), 1),
            "language": transcript.language or "unknown",
        },
    }


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    # Strip code fences.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None


# ---------------------------------------------------------------------------
# Google Gemini summarisation (the only cloud AI used by this project)
# ---------------------------------------------------------------------------
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Transcripts larger than this (in characters) are summarised in chunks with a
# map-reduce pass so very long videos never exceed the model's context window.
_GEMINI_CHUNK_CHARS = 28000
_GEMINI_CHUNK_OVERLAP = 600


def _chunk_text(text: str, size: int = _GEMINI_CHUNK_CHARS, overlap: int = _GEMINI_CHUNK_OVERLAP) -> List[str]:
    """Split text into roughly `size`-char chunks on sentence boundaries."""
    sentences = _split_sentences(text)
    if not sentences:
        return [text] if text.strip() else []
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for sentence in sentences:
        if current_len + len(sentence) > size and current:
            chunks.append(" ".join(current))
            # Carry a little overlap for context continuity.
            tail = " ".join(current)[-overlap:]
            current = [tail, sentence]
            current_len = len(tail) + len(sentence) + 1
        else:
            current.append(sentence)
            current_len += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _gemini_refined_schema() -> Any:
    from google.genai import types  # type: ignore

    def _str(desc: str) -> Any:
        return types.Schema(type=types.Type.STRING, description=desc)

    def _arr(desc: str) -> Any:
        return types.Schema(
            type=types.Type.ARRAY,
            description=desc,
            items=types.Schema(type=types.Type.STRING),
        )

    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "overview": _str("2-3 sentence paragraph overview"),
            "summary": _str("4-8 sentence narrative summary"),
            "key_points": _arr("5-8 key takeaways"),
            "highlights": _arr("Notable quotes or sound bites"),
            "action_items": _arr("Practical actionable takeaways or next steps"),
        },
        required=["overview", "summary", "key_points"],
    )


def _gemini_generate(prompt: str, model: str, response_schema: Any = None) -> str:
    """Single Gemini generate_content call; retries once without the JSON
    schema for SDKs/models that reject structured output."""
    from google.genai import types  # type: ignore

    client = _get_gemini_client()

    def _call(with_schema: bool) -> str:
        config_kwargs: Dict[str, Any] = {"temperature": 0.2}
        if with_schema and response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return getattr(response, "text", "") or ""

    try:
        return _call(True)
    except Exception as exc:  # noqa: BLE001
        _log(f"Gemini structured call failed ({exc}); retrying without schema.")
        return _call(False)


def _gemini_summarize_chunk(
    chunk: str, refine: bool, model: str, language: str
) -> Any:
    """Summarise one chunk of transcript.

    Returns a refined dict when `refine` is set, otherwise a plain string.
    """
    if refine:
        prompt = textwrap.dedent(
            f"""
            You are a professional video transcript analyst working in {language}.
            Analyse the transcript chunk below and return ONLY a JSON object:
            {{
              "overview": "2-3 sentence overview of this chunk",
              "summary": "4-8 sentence factual narrative of this chunk",
              "key_points": ["important point", "..."],
              "highlights": ["notable quote or moment", "..."],
              "action_items": ["actionable takeaway", "..."]
            }}
            Rules: use only information present in the transcript; do not invent
            facts; write in {language}; keep lists concise (1-8 items each).

            <transcript>
            {chunk}
            </transcript>
            """
        )
        result = _gemini_generate(prompt, model, _gemini_refined_schema())
        parsed = _extract_json(result)
        if parsed:
            return parsed
        return {"overview": result, "summary": result, "key_points": []}

    prompt = textwrap.dedent(
        f"""
        You are a professional video summarizer working in {language}.
        Summarise the transcript chunk below in 4-8 concise, factual sentences.
        Use only information present in the transcript; do not invent facts;
        write in {language}.

        <transcript>
        {chunk}
        </transcript>
        """
    )
    return _gemini_generate(prompt, model).strip()


def _gemini_reduce(chunk_summaries: List[Any], refine: bool, model: str, language: str) -> Any:
    """Combine per-chunk summaries into one final summary."""
    if refine:
        combined = json.dumps(chunk_summaries, ensure_ascii=False, indent=1)
        prompt = textwrap.dedent(
            f"""
            You are a professional video transcript analyst working in {language}.
            Below are per-section analyses of a long video, in JSON form. Merge
            them into ONE final coherent report for the whole video and return
            ONLY a JSON object:
            {{
              "overview": "2-3 sentence overview of the whole video",
              "summary": "5-10 sentence narrative summary of the whole video",
              "key_points": ["most important point", "..."],
              "highlights": ["best quote or moment", "..."],
              "action_items": ["actionable takeaway", "..."]
            }}
            Deduplicate points, keep the most important ones, and use only the
            information provided. Write everything in {language}.

            <sections>
            {combined}
            </sections>
            """
        )
        result = _gemini_generate(prompt, model, _gemini_refined_schema())
        parsed = _extract_json(result)
        if parsed:
            return parsed
        return {"overview": result, "summary": result, "key_points": []}

    joined = "\n\n".join(f"- {s}" for s in chunk_summaries)
    prompt = textwrap.dedent(
        f"""
        You are a professional video summarizer working in {language}.
        Below are section summaries of a long video. Merge them into one
        concise, coherent 5-10 sentence summary of the whole video, using only
        the information provided. Write in {language}.

        <section-summaries>
        {joined}
        </section-summaries>
        """
    )
    return _gemini_generate(prompt, model).strip()


def _summarize_gemini(text: str, refine: bool, model: Optional[str], language: str) -> Any:
    """Summarise with Google Gemini, chunking long transcripts map-reduce
    style so the model's context window is never exceeded."""
    model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
    chunks = _chunk_text(text)
    if len(chunks) == 1:
        return _gemini_summarize_chunk(chunks[0], refine, model, language)

    _log(f"Long transcript: summarising {len(chunks)} chunks with Gemini then merging.")
    partial = [_gemini_summarize_chunk(chunk, refine, model, language) for chunk in chunks]
    return _gemini_reduce(partial, refine, model, language)


def _ensure_refined_shape(summary: Dict[str, Any], transcript: "Transcript") -> Dict[str, Any]:
    """Make sure every refined report has the fields the UI/CLI expect, and
    fill in stats from the transcript."""
    def _as_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    refined = {
        "type": "refined",
        "title": transcript.title or "Untitled video",
        "source": transcript.source,
        "url": transcript.url,
        "overview": str(summary.get("overview") or summary.get("summary") or "").strip(),
        "summary": str(summary.get("summary") or summary.get("overview") or "").strip(),
        "key_points": _as_list(summary.get("key_points")),
        "highlights": _as_list(summary.get("highlights")),
        "action_items": _as_list(summary.get("action_items")),
    }
    if not refined["overview"]:
        sentences = _split_sentences(transcript.text)
        refined["overview"] = sentences[0] if sentences else "No summary available."
    if not refined["summary"]:
        refined["summary"] = refined["overview"]
    if not refined["key_points"]:
        refined["key_points"] = _split_sentences(transcript.text)[:5] or ["No key points detected."]
    if not refined["highlights"]:
        refined["highlights"] = ["No direct quotes detected."]
    if not refined["action_items"]:
        refined["action_items"] = ["No explicit action items detected."]
    refined["stats"] = {
        "word_count": transcript.word_count,
        "char_count": len(transcript.text),
        "estimated_reading_minutes": round(max(transcript.word_count / 200, 0), 1),
        "language": transcript.language or "unknown",
    }
    return refined


def _llm_available() -> Optional[str]:
    # Google Gemini is the only cloud AI provider used by this project.
    return "gemini" if gemini_available() else None


def _summarize_llm(
    text: str,
    refine: bool,
    model: Optional[str],
    language: str,
    force: bool = False,
) -> Tuple[Any, str]:
    provider = _llm_available()
    if not provider:
        if force:
            raise RuntimeError(
                "Google Gemini is not configured. Set GEMINI_API_KEY (or "
                "GOOGLE_API_KEY) and install google-genai (`pip install "
                "google-genai`), then try --summary-mode llm again."
            )
        return "", "extractive"
    return _summarize_gemini(text, refine, model, language), "llm"


def summarize_transcript(
    transcript: Transcript,
    refine: bool = False,
    mode: str = "auto",
    model: Optional[str] = None,
    language: str = "English",
    max_sentences: int = 6,
) -> Tuple[Any, str, List[str]]:
    """Return (summary, method, warnings). `method` is 'llm', 'extractive', or
    'none'. The LLM is always Google Gemini."""
    text = transcript.text
    warnings: List[str] = []
    if not text:
        return "", "none", warnings

    if mode in ("auto", "llm"):
        try:
            result, method = _summarize_llm(
                text, refine=refine, model=model, language=language,
                force=(mode == "llm"),
            )
        except RuntimeError:
            if mode == "llm":
                raise
            result, method = "", "extractive"
        except Exception as exc:  # noqa: BLE001 - never let an API error kill extraction
            if mode == "llm":
                raise
            warnings.append(
                f"Google Gemini summarization failed ({exc}); fell back to the local extractive summary."
            )
            result, method = "", "extractive"

        if method == "llm":
            if refine and isinstance(result, dict):
                result = _ensure_refined_shape(result, transcript)
            return result, method, warnings

    # Fallback / explicit extractive path.
    abstract = _extractive_summary(text, max_sentences=max_sentences)
    if refine:
        return _heuristic_refined_summary(transcript, abstract), "extractive", warnings
    return abstract, "extractive", warnings


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def _format_timestamp(seconds: Optional[float]) -> str:
    if seconds is None:
        return "00:00"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _metadata_lines(transcript: Transcript) -> List[str]:
    return [
        f"Title:    {transcript.title}",
        f"Source:   {transcript.source}",
        f"URL:      {transcript.url}",
        f"Language: {transcript.language or 'unknown'}",
        f"Segments: {len(transcript.segments)}",
        f"Words:    {transcript.word_count}",
    ]


def _format_refined_text(refined: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("")
    lines.append("Refined Summary")
    lines.append("================")
    if refined.get("overview"):
        lines.append(refined["overview"])
    if refined.get("summary") and refined.get("summary") != refined.get("overview"):
        lines.append("")
        lines.append("Summary")
        lines.append("-------")
        lines.append(refined["summary"])
    for key in ("key_points", "highlights", "action_items"):
        values = refined.get(key) or []
        if not values:
            continue
        title = {
            "key_points": "Key Points",
            "highlights": "Highlights / Quotes",
            "action_items": "Action Items",
        }[key]
        lines.append("")
        lines.append(title)
        lines.append("-" * len(title))
        for idx, value in enumerate(values, 1):
            lines.append(f"{idx}. {value}")
    stats = refined.get("stats") or {}
    if stats:
        lines.append("")
        lines.append("Stats")
        lines.append("-----")
        for key, value in stats.items():
            lines.append(f"{key.replace('_', ' ').title()}: {value}")
    return "\n".join(lines)


def format_output(
    transcript: Transcript,
    summary: Any,
    method: str,
    output_format: str,
    refine: bool,
    summary_only: bool = False,
) -> str:
    is_refined = isinstance(summary, dict)
    if output_format == "json":
        payload = {
            "transcript": {
                "source": transcript.source,
                "title": transcript.title,
                "url": transcript.url,
                "language": transcript.language,
                "is_auto_caption": transcript.is_auto_caption,
                "word_count": transcript.word_count,
                "segments": [s.to_dict() for s in transcript.segments],
            },
            "summary": summary or "",
            "summary_method": method,
            "refined": is_refined,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if output_format == "markdown":
        parts: List[str] = []
        parts.append(f"# {transcript.title or 'Transcript Summary'}")
        parts.append("")
        for line in _metadata_lines(transcript):
            parts.append(f"- {line}")
        parts.append("")
        parts.append(f"> **Summary method:** `{method}`")
        parts.append("")
        if not summary_only:
            parts.append("## Full Transcript")
            parts.append("")
            if transcript.segments:
                for seg in transcript.segments:
                    timestamp = f"[{_format_timestamp(seg.start)}]" if seg.start is not None else ""
                    parts.append(f"{timestamp} {seg.text}")
            else:
                parts.append(transcript.text)
            parts.append("")
        parts.append("## Summary")
        parts.append("")
        if is_refined:
            if summary.get("overview"):
                parts.append(summary["overview"])
                parts.append("")
            if summary.get("summary") and summary.get("summary") != summary.get("overview"):
                parts.append(summary["summary"])
                parts.append("")
            for key in ("key_points", "highlights", "action_items"):
                values = summary.get(key) or []
                if not values:
                    continue
                title = {
                    "key_points": "### Key Points",
                    "highlights": "### Highlights",
                    "action_items": "### Action Items",
                }[key]
                parts.append(title)
                parts.append("")
                for value in values:
                    parts.append(f"- {value}")
                parts.append("")
            stats = summary.get("stats") or {}
            if stats:
                parts.append("### Stats")
                parts.append("")
                for key, value in stats.items():
                    parts.append(f"- **{key.replace('_', ' ').title()}:** {value}")
        else:
            parts.append(str(summary or "No summary generated."))
        return "\n".join(parts).rstrip() + "\n"

    # Plain text
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("TRANSCRIPT EXTRACTOR OUTPUT")
    lines.append("=" * 70)
    lines.extend(_metadata_lines(transcript))
    lines.append(f"Summary method: {method}")
    lines.append("")
    if not summary_only:
        lines.append("=" * 70)
        lines.append("TRANSCRIPT")
        lines.append("=" * 70)
        for seg in transcript.segments:
            timestamp = f"[{_format_timestamp(seg.start)}]" if seg.start is not None else ""
            lines.append(f"{timestamp} {seg.text}")
        lines.append("")
    lines.append("=" * 70)
    if is_refined:
        lines.append(_format_refined_text(summary))
    else:
        lines.append("SUMMARY")
        lines.append("=" * 70)
        lines.append(str(summary or "No summary generated."))
    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="extract_transcript.py",
        description=(
            "Extract transcripts from YouTube or almost any video platform and "
            "produce a simple or refined summary."
        ),
        epilog=(
            "Examples:\n"
            "  python extract_transcript.py https://youtu.be/VIDEO_ID --refine\n"
            "  python extract_transcript.py https://vimeo.com/... --summary-mode llm --save out.md\n"
            "  python extract_transcript.py ./meeting.m4a --platform file --refine\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="Video URL or YouTube video id")
    parser.add_argument("--input", "-i", help="Local audio/video/subtitle file")
    parser.add_argument(
        "--platform",
        choices=["auto", "youtube", "file"],
        default="auto",
        help="Input type (default: auto-detect)",
    )
    parser.add_argument(
        "--languages",
        default=",".join(DEFAULT_LANGUAGES),
        help="Comma-separated caption languages to try (default: en,en-US,...)",
    )
    parser.add_argument(
        "--language",
        dest="transcribe_language",
        help="Language hint passed to the transcription engine / used for captions",
    )
    parser.add_argument(
        "--summary-language",
        default="English",
        help="Language for the generated summary (default: English)",
    )
    parser.add_argument(
        "--summary-mode",
        choices=["auto", "extractive", "llm"],
        default="auto",
        help="auto uses an LLM when a key is available, otherwise extractive",
    )
    parser.add_argument("--no-summary", action="store_true", help="Skip summary generation")
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Produce a more refined, structured summary (key points, action items, etc.)",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--save", help="Write the output to a file instead of stdout")
    parser.add_argument("--model", help="LLM model name (provider-specific)")
    parser.add_argument("--whisper-model", default="base", help="Local whisper model size")
    parser.add_argument("--audio-dir", help="Directory in which to keep downloaded audio")
    parser.add_argument("--max-summary-sentences", type=int, default=6)
    parser.add_argument("--summary-only", action="store_true", help="Print only the summary")
    parser.add_argument("--verbose", action="store_true", help="Print progress messages")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    global VERBOSE
    parser = build_parser()
    args = parser.parse_args(argv)
    VERBOSE = bool(args.verbose)

    source = args.url or args.input
    if not source:
        parser.error("Provide a video URL, YouTube id, or --input file path.")

    # A positional argument that is a local path (not a URL) is treated as a
    # local input file, matching the documented `./meeting.m4a` usage.
    url_arg = args.url
    input_path = args.input
    if url_arg and not is_url(url_arg) and not extract_youtube_id(url_arg):
        candidate = Path(url_arg).expanduser()
        if candidate.exists():
            input_path = str(candidate)
            url_arg = None

    try:
        transcript = extract_transcript(
            url=url_arg,
            input_path=input_path,
            platform=args.platform,
            languages=[
                lang.strip() for lang in args.languages.split(",") if lang.strip()
            ],
            language_hint=args.transcribe_language,
            whisper_model=args.whisper_model,
            keep_audio_dir=Path(args.audio_dir).expanduser() if args.audio_dir else None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error extracting transcript: {exc}", file=sys.stderr)
        return 1

    if not transcript.segments:
        print("Error: no transcript content was extracted.", file=sys.stderr)
        return 1

    summary: Any = ""
    method = "none"
    if not args.no_summary:
        try:
            summary, method, summary_warnings = summarize_transcript(
                transcript,
                refine=args.refine,
                mode=args.summary_mode,
                model=args.model,
                language=args.summary_language,
                max_sentences=args.max_summary_sentences,
            )
            for warning in summary_warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"Error generating summary: {exc}", file=sys.stderr)
            return 1

    output = format_output(
        transcript,
        summary,
        method,
        args.output_format,
        args.refine,
        summary_only=args.summary_only,
    )

    if args.save:
        save_path = Path(args.save).expanduser()
        if save_path.suffix == "":
            save_path = save_path.with_suffix("." + args.output_format)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(output, encoding="utf-8")
        _log(f"Output saved to {save_path}")
        return 0
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())