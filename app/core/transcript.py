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
4.  Summarisation         -> uses an LLM when an API key is present, otherwise
                             falls back to a built-in extractive summarizer so
                             the tool always works out of the box.

Examples
--------
    # Youtube captions + extractive summary (no API key required)
    python extract_transcript.py "https://youtu.be/VIDEO_ID"

    # Structured, polished summary
    python extract_transcript.py "https://youtu.be/VIDEO_ID" --refine

    # Use an LLM summary and save markdown/JSON
    OPENAI_API_KEY=sk-... python extract_transcript.py \
        https://youtu.be/VIDEO_ID --refine --summary-mode llm --save out.md

    # Any other platform (e.g. Vimeo/Facebook/TED) via yt-dlp
    python extract_transcript.py "https://vimeo.com/..." --refine

    # Transcribe a local file (uses local whisper or OpenAI API for audio)
    python extract_transcript.py ./meeting.m4a --platform file --refine

Requires (see requirements.txt): youtube-transcript-api, yt-dlp, optional:
openai / anthropic / google-generativeai / openai-whisper.
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
                return _build_yt_transcript(video_id, lang, segments, False)
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


def _transcribe_audio(audio_path: Path, language: Optional[str], whisper_model: str) -> List[TranscriptSegment]:
    """Transcribe audio using local openai-whisper if available, otherwise the
    OpenAI audio transcriptions API (requires OPENAI_API_KEY)."""
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

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No caption/subtitle and no transcription engine available. "
            "Install openai-whisper locally (`pip install openai-whisper`) or set "
            "OPENAI_API_KEY to use the OpenAI whisper-1 API."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The 'openai' package is required for API transcription.") from exc

    _log("Transcribing with OpenAI whisper-1 (API)...")
    client = OpenAI(api_key=api_key)
    with open(audio_path, "rb") as file_obj:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=file_obj,
            language=language,
            response_format="verbose_json",
        )
    segments = []
    for seg in getattr(response, "segments", []) or []:
        segments.append(
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                duration=float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)),
                text=_clean_text(seg.get("text", "")),
            )
        )
    return segments


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


def _summarize_openai(text: str, refine: bool, model: Optional[str], language: str) -> Any:
    from openai import OpenAI

    model = model or "gpt-4o-mini"
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    system = (
        "You are a professional video summarizer. Produce a concise, factual "
        f"summary in {language}. Do not invent information that is not present."
    )
    if refine:
        user = textwrap.dedent(
            f"""
            Here is a video transcript:
            <transcript>
            {text}
            </transcript>

            Return ONLY a JSON object with this schema:
            {{
              "overview": "2-3 sentence paragraph",
              "summary": "4-8 sentence narrative summary",
              "key_points": ["point1", "point2"],
              "highlights": ["memorable quote or sound bite"],
              "action_items": ["actionable takeaway or next step"]
            }}
            """
        )
    else:
        user = (
            f"Summarize the following transcript in {language}.\n\n"
            f"<transcript>\n{text}\n</transcript>"
        )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    result = response.choices[0].message.content or ""
    if refine:
        parsed = _extract_json(result)
        if parsed:
            return parsed
        return {"type": "refined", "summary": result, "overview": result, "key_points": []}
    return result


def _summarize_anthropic(text: str, refine: bool, model: Optional[str], language: str) -> Any:
    import anthropic

    model = model or "claude-3-5-haiku-latest"
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    system = (
        "You are a professional video summarizer. Produce a concise, factual "
        f"summary in {language}. Do not invent information that is not present."
    )
    if refine:
        user = textwrap.dedent(
            f"""
            Here is a video transcript:
            <transcript>
            {text}
            </transcript>

            Return ONLY a JSON object with this schema:
            {{
              "overview": "2-3 sentence paragraph",
              "summary": "4-8 sentence narrative summary",
              "key_points": ["point1", "point2"],
              "highlights": ["memorable quote or sound bite"],
              "action_items": ["actionable takeaway or next step"]
            }}
            """
        )
    else:
        user = (
            f"Summarize the following transcript in {language}.\n\n"
            f"<transcript>\n{text}\n</transcript>"
        )
    response = client.messages.create(
        model=model,
        max_tokens=1800,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    result = response.content[0].text
    if refine:
        parsed = _extract_json(result)
        if parsed:
            return parsed
        return {"type": "refined", "summary": result, "overview": result, "key_points": []}
    return result


def _summarize_gemini(text: str, refine: bool, model: Optional[str], language: str) -> Any:
    import google.generativeai as genai

    model = model or "gemini-1.5-flash"
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    client = genai.GenerativeModel(model)
    if refine:
        prompt = textwrap.dedent(
            f"""
            Summarize the following transcript in {language} and return ONLY JSON:
            {{
              "overview": "...",
              "summary": "...",
              "key_points": ["..."],
              "highlights": ["..."],
              "action_items": ["..."]
            }}

            Transcript:
            {text}
            """
        )
    else:
        prompt = f"Summarize the following transcript in {language}.\n\n{text}"
    result = client.generate_content(prompt).text
    if refine:
        parsed = _extract_json(result)
        if parsed:
            return parsed
        return {"type": "refined", "summary": result, "overview": result, "key_points": []}
    return result


def _llm_available() -> Optional[str]:
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return None


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
                "No LLM provider configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                "or GEMINI_API_KEY and try --summary-mode llm again."
            )
        return "", "extractive"

    if provider == "openai":
        return _summarize_openai(text, refine, model, language), "llm"
    if provider == "anthropic":
        return _summarize_anthropic(text, refine, model, language), "llm"
    if provider == "gemini":
        return _summarize_gemini(text, refine, model, language), "llm"
    return "", "extractive"


def summarize_transcript(
    transcript: Transcript,
    refine: bool = False,
    mode: str = "auto",
    model: Optional[str] = None,
    language: str = "English",
    max_sentences: int = 6,
) -> Tuple[Any, str]:
    """Return (summary, method). `method` is 'llm' or 'extractive'."""
    text = transcript.text
    if not text:
        return "", "none"

    if mode in ("auto", "llm"):
        result, method = _summarize_llm(
            text, refine=refine, model=model, language=language, force=(mode == "llm")
        )
        if method == "llm":
            return result, method

    # Fallback / explicit extractive path.
    abstract = _extractive_summary(text, max_sentences=max_sentences)
    if refine:
        return _heuristic_refined_summary(transcript, abstract), "extractive"
    return abstract, "extractive"


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

    try:
        transcript = extract_transcript(
            url=args.url,
            input_path=args.input,
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
            summary, method = summarize_transcript(
                transcript,
                refine=args.refine,
                mode=args.summary_mode,
                model=args.model,
                language=args.summary_language,
                max_sentences=args.max_summary_sentences,
            )
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