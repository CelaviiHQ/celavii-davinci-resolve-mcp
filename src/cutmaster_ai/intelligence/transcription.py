"""Whole-timeline transcription — extract audio + STT in one MCP call.

Chains :func:`cutmaster.media.ffmpeg_audio.extract_timeline_audio` and
:func:`cutmaster.stt.base.transcribe_audio` so callers don't have to
juggle a temp WAV. The intermediate audio is deleted on success;
``keep_audio=True`` keeps it for debugging.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import mcp
from ..cutmaster.media.ffmpeg_audio import extract_timeline_audio
from ..cutmaster.stt.base import DEFAULT_PROVIDER, transcribe_audio
from ..errors import safe_resolve_call
from ..resolve import _boilerplate, _resolve_safe_dir

_VALID_FORMATS = ("json", "srt", "vtt", "txt")


def _find_timeline(project, name: str):
    """Return a timeline by name, or the current timeline when ``name`` is empty."""
    if not name:
        tl = project.GetCurrentTimeline()
        if tl is None:
            raise ValueError("No current timeline — open one or pass timeline_name.")
        return tl

    count = int(project.GetTimelineCount() or 0)
    for i in range(1, count + 1):
        tl = project.GetTimelineByIndex(i)
        if tl is None:
            continue
        if (tl.GetName() or "") == name:
            return tl
    raise ValueError(f"Timeline '{name}' not found in current project.")


def _fmt_ts(seconds: float, *, vtt: bool = False) -> str:
    """``HH:MM:SS,mmm`` (SRT) or ``HH:MM:SS.mmm`` (VTT)."""
    if seconds < 0:
        seconds = 0.0
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    ms = int(round((s - int(s)) * 1000))
    sep = "." if vtt else ","
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{ms:03d}"


def _group_into_cues(
    words: list[dict],
    *,
    max_gap_s: float = 0.8,
    max_duration_s: float = 5.0,
    max_chars: int = 84,
) -> list[dict]:
    """Group word-level entries into subtitle cues.

    Splits on: speaker change, gap above ``max_gap_s``, cue length above
    ``max_duration_s``, or text length above ``max_chars``.
    """
    cues: list[dict] = []
    if not words:
        return cues

    cur: dict | None = None
    for w in words:
        text = (w.get("word") or "").strip()
        if not text:
            continue
        start = float(w.get("start_time", 0.0))
        end = float(w.get("end_time", start))
        speaker = w.get("speaker_id") or "S1"

        if cur is None:
            cur = {"start": start, "end": end, "speaker": speaker, "text": text}
            continue

        gap = start - cur["end"]
        prospective = (cur["text"] + " " + text).strip()
        if (
            speaker != cur["speaker"]
            or gap > max_gap_s
            or (end - cur["start"]) > max_duration_s
            or len(prospective) > max_chars
        ):
            cues.append(cur)
            cur = {"start": start, "end": end, "speaker": speaker, "text": text}
        else:
            cur["end"] = end
            cur["text"] = prospective

    if cur is not None:
        cues.append(cur)
    return cues


def _render_srt(cues: list[dict]) -> str:
    lines: list[str] = []
    for i, c in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_ts(c['start'])} --> {_fmt_ts(c['end'])}")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines)


def _render_vtt(cues: list[dict]) -> str:
    lines: list[str] = ["WEBVTT", ""]
    for c in cues:
        lines.append(f"{_fmt_ts(c['start'], vtt=True)} --> {_fmt_ts(c['end'], vtt=True)}")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines)


def _render_txt(cues: list[dict]) -> str:
    return "\n".join(f"[{_fmt_ts(c['start'])}] {c['text']}" for c in cues)


@mcp.tool
@safe_resolve_call
def cutmaster_transcribe_timeline(
    timeline_name: str = "",
    output_dir: str = "",
    audio_track: int = 0,
    provider: str = "",
    output_format: str = "json",
    keep_audio: bool = False,
) -> str:
    """Transcribe an entire timeline's audio in one call.

    Extracts the timeline's audio to a temp WAV (via ffmpeg on source
    files — no Resolve render queue), then transcribes with Deepgram or
    Gemini. Word-level timestamps with diarization (Deepgram) are
    preserved.

    Args:
        timeline_name: Timeline to transcribe. Empty = current timeline.
        output_dir: Directory to write the transcript into. Empty =
            ``~/Documents/resolve-exports/transcripts``.
        audio_track: 1-based audio track index. ``0`` = auto-pick
            (prefers dialogue-labelled tracks).
        provider: ``"deepgram"`` or ``"gemini"``. Empty = env default
            (``CUTMASTER_STT_PROVIDER``, else Deepgram if its key is set,
            else Gemini).
        output_format: ``json`` | ``srt`` | ``vtt`` | ``txt``. JSON
            preserves per-word timestamps + speaker IDs + confidence.
        keep_audio: If True, leave the intermediate WAV next to the
            transcript instead of deleting it.

    Returns:
        JSON string with ``path``, ``timeline``, ``provider``,
        ``duration_s``, and ``word_count``.
    """
    if output_format not in _VALID_FORMATS:
        raise ValueError(f"output_format must be one of {_VALID_FORMATS}, got {output_format!r}.")

    _, project, _ = _boilerplate()
    tl = _find_timeline(project, timeline_name)
    tl_name = tl.GetName() or "timeline"

    out_root = output_dir.strip() or str(
        Path.home() / "Documents" / "resolve-exports" / "transcripts"
    )
    out_root = _resolve_safe_dir(out_root)
    out_dir = Path(out_root).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in tl_name) or "timeline"
    transcript_path = out_dir / f"{safe_stem}.{output_format}"

    audio_dest = out_dir / (f"{safe_stem}.wav" if keep_audio else f".{safe_stem}.tmp.wav")

    try:
        track_arg = audio_track if audio_track and audio_track > 0 else None
        audio_info = extract_timeline_audio(tl, audio_dest, track_index=track_arg)

        chosen_provider = (provider or DEFAULT_PROVIDER).lower()
        transcript = transcribe_audio(audio_dest, provider=chosen_provider)
        words = [w.model_dump() for w in transcript.words]

        if output_format == "json":
            payload = {
                "timeline": tl_name,
                "duration_s": audio_info["duration_s"],
                "provider": chosen_provider,
                "words": words,
            }
            transcript_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            cues = _group_into_cues(words)
            if output_format == "srt":
                transcript_path.write_text(_render_srt(cues), encoding="utf-8")
            elif output_format == "vtt":
                transcript_path.write_text(_render_vtt(cues), encoding="utf-8")
            else:  # txt
                transcript_path.write_text(_render_txt(cues), encoding="utf-8")

        return json.dumps(
            {
                "path": str(transcript_path),
                "timeline": tl_name,
                "provider": chosen_provider,
                "duration_s": audio_info["duration_s"],
                "word_count": len(words),
                "audio_kept": bool(keep_audio),
                "audio_path": str(audio_dest) if keep_audio else None,
            },
            indent=2,
        )
    finally:
        if not keep_audio:
            try:
                audio_dest.unlink(missing_ok=True)
            except Exception:
                pass
