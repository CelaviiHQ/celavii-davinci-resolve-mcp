"""Resolve-native timeline-level AI ops — auto-captions + scene-cut detection.

Studio-only. Each wrapper triggers a documented timeline method:

- ``CreateSubtitlesFromAudio({autoCaptionSettings})`` — README line 395, settings
  spec at lines 720–760. Returns ``Bool``.
- ``DetectSceneCuts()``                              — README line 398. Returns
  ``Bool``. **Destructive** — inserts scene cuts into the current timeline; we
  snapshot the project first via ``snapshot_project``.

Caption settings constants are looked up at runtime from the live ``resolve``
handle (e.g. ``resolve.AUTO_CAPTION_ENGLISH``) so we don't hard-code the
numeric enum values — they can shift between Resolve builds. Verified live on
Resolve 21.0.0b.20 Studio. See ``api_verification.md``.
"""

import json

from ..config import mcp
from ..errors import safe_resolve_call
from ..resolve import _boilerplate, _require_studio

# Caption language friendly-name → Resolve constant suffix
_LANGUAGES: dict[str, str] = {
    "auto": "AUTO_CAPTION_AUTO",
    "danish": "AUTO_CAPTION_DANISH",
    "dutch": "AUTO_CAPTION_DUTCH",
    "english": "AUTO_CAPTION_ENGLISH",
    "french": "AUTO_CAPTION_FRENCH",
    "german": "AUTO_CAPTION_GERMAN",
    "italian": "AUTO_CAPTION_ITALIAN",
    "japanese": "AUTO_CAPTION_JAPANESE",
    "korean": "AUTO_CAPTION_KOREAN",
    "mandarin": "AUTO_CAPTION_MANDARIN_SIMPLIFIED",
    "mandarin-simplified": "AUTO_CAPTION_MANDARIN_SIMPLIFIED",
    "mandarin-traditional": "AUTO_CAPTION_MANDARIN_TRADITIONAL",
    "norwegian": "AUTO_CAPTION_NORWEGIAN",
    "portuguese": "AUTO_CAPTION_PORTUGUESE",
    "russian": "AUTO_CAPTION_RUSSIAN",
    "spanish": "AUTO_CAPTION_SPANISH",
    "swedish": "AUTO_CAPTION_SWEDISH",
}

_PRESETS: dict[str, str] = {
    "default": "AUTO_CAPTION_SUBTITLE_DEFAULT",
    "subtitle": "AUTO_CAPTION_SUBTITLE_DEFAULT",
    "teletext": "AUTO_CAPTION_TELETEXT",
    "netflix": "AUTO_CAPTION_NETFLIX",
}

_LINE_BREAKS: dict[str, str] = {
    "single": "AUTO_CAPTION_LINE_SINGLE",
    "double": "AUTO_CAPTION_LINE_DOUBLE",
}


def _resolve_constant(resolve, suffix: str, label: str) -> float | int:
    """Look up a constant on the live resolve object; raise if missing."""
    value = getattr(resolve, suffix, None)
    if value is None:
        raise ValueError(
            f"Resolve constant '{suffix}' (for {label}) is not exposed on this "
            "Resolve build — likely a version mismatch."
        )
    return value


@mcp.tool
@safe_resolve_call
def cutmaster_create_subtitles_from_audio(
    language: str = "auto",
    caption_preset: str = "default",
    chars_per_line: int = 0,
    line_break: str = "single",
    gap_frames: int = 0,
) -> str:
    """Generate a subtitle track on the current timeline via Resolve's AI.

    Args:
        language: ``auto`` (Resolve detects), or one of: ``english`` /
            ``spanish`` / ``french`` / ``german`` / ``italian`` /
            ``portuguese`` / ``japanese`` / ``korean`` /
            ``mandarin`` (simplified) / ``mandarin-traditional`` /
            ``russian`` / ``dutch`` / ``danish`` / ``swedish`` /
            ``norwegian``.
        caption_preset: ``default`` (Subtitle Default) / ``teletext`` /
            ``netflix``. Netflix forces 16 chars-per-line if you don't
            override; default is 42.
        chars_per_line: 1–60. ``0`` = use Resolve's default for the
            chosen preset.
        line_break: ``single`` (one line per caption) or ``double``.
        gap_frames: 0–10. ``0`` = no gap between cues.

    Studio only. Inserts a new subtitle track on the current timeline.
    """
    _require_studio("CreateSubtitlesFromAudio")
    lang_key = language.strip().lower()
    preset_key = caption_preset.strip().lower()
    break_key = line_break.strip().lower()
    if lang_key not in _LANGUAGES:
        raise ValueError(f"Invalid language '{language}'. Allowed: {sorted(_LANGUAGES)}.")
    if preset_key not in _PRESETS:
        raise ValueError(f"Invalid caption_preset '{caption_preset}'. Allowed: {sorted(_PRESETS)}.")
    if break_key not in _LINE_BREAKS:
        raise ValueError(f"Invalid line_break '{line_break}'. Allowed: single / double.")
    if not (0 <= gap_frames <= 10):
        raise ValueError("gap_frames must be 0..10.")
    if chars_per_line and not (1 <= chars_per_line <= 60):
        raise ValueError("chars_per_line must be 0 (default) or 1..60.")

    resolve, project, _ = _boilerplate()
    tl = project.GetCurrentTimeline()
    if tl is None:
        return "No current timeline."

    # Build the autoCaptionSettings dict using live constant lookups.
    settings = {
        _resolve_constant(resolve, "SUBTITLE_LANGUAGE", "language key"): _resolve_constant(
            resolve, _LANGUAGES[lang_key], "language value"
        ),
        _resolve_constant(
            resolve, "SUBTITLE_CAPTION_PRESET", "caption preset key"
        ): _resolve_constant(resolve, _PRESETS[preset_key], "caption preset value"),
        _resolve_constant(resolve, "SUBTITLE_LINE_BREAK", "line break key"): _resolve_constant(
            resolve, _LINE_BREAKS[break_key], "line break value"
        ),
        _resolve_constant(resolve, "SUBTITLE_GAP", "gap key"): gap_frames,
    }
    if chars_per_line:
        settings[_resolve_constant(resolve, "SUBTITLE_CHARS_PER_LINE", "chars-per-line key")] = (
            chars_per_line
        )

    ok = tl.CreateSubtitlesFromAudio(settings)
    if not ok:
        return (
            "Resolve refused to generate subtitles. Common causes: timeline "
            "audio missing, no speech detected, or transcription engine not yet "
            "ready (try again in a moment)."
        )
    return json.dumps(
        {
            "created": True,
            "timeline": tl.GetName(),
            "language": lang_key,
            "preset": preset_key,
        },
        indent=2,
    )


@mcp.tool
@safe_resolve_call
def cutmaster_detect_scene_cuts(timeline_name: str = "") -> str:
    """Run Resolve's AI scene-cut detector on a timeline.

    Args:
        timeline_name: Timeline to operate on. Empty = current timeline.

    **Destructive** — inserts cuts directly into the timeline. The
    wrapper snapshots the project first via
    ``snapshot_project(... label="pre_detect_scene_cuts")`` so the
    operation is reversible via existing snapshot tooling. Studio only.
    """
    from ..cutmaster.core.snapshot import snapshot_project  # local import

    _require_studio("DetectSceneCuts")
    resolve, project, _ = _boilerplate()

    if timeline_name:
        tl = None
        count = int(project.GetTimelineCount() or 0)
        for i in range(1, count + 1):
            candidate = project.GetTimelineByIndex(i)
            if candidate is not None and (candidate.GetName() or "") == timeline_name:
                tl = candidate
                break
        if tl is None:
            return f"Timeline '{timeline_name}' not found."
        # Make it current — DetectSceneCuts operates on the current timeline.
        project.SetCurrentTimeline(tl)
    else:
        tl = project.GetCurrentTimeline()
        if tl is None:
            return "No current timeline."

    snap = snapshot_project(resolve, project, label="pre_detect_scene_cuts")
    ok = tl.DetectSceneCuts()
    if not ok:
        return f"Resolve refused to detect scene cuts on '{tl.GetName()}'."
    return json.dumps(
        {
            "detected": True,
            "timeline": tl.GetName(),
            "snapshot": snap.get("path"),
        },
        indent=2,
    )
