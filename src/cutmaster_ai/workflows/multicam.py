"""Multicam helpers — currently just ``AutoSyncAudio``.

The proposal called for two tools (multicam-timeline-creator + audio-sync),
but live verification on Resolve 21.0.0b.20 showed that
``MediaPool.CreateMultiCamClipWithMediaItems`` is not callable on this
build — it's not in the documented API. Only ``AutoSyncAudio`` (README
line 254) survives the verification cut, so this module ships one tool.

When Blackmagic publishes a documented multicam-create method, add the
``cutmaster_setup_multicam_timeline`` wrapper alongside.

Verified live on Resolve 21.0.0b.20 — see ``api_verification.md``.
"""

from __future__ import annotations

import json

from ..config import mcp
from ..errors import safe_resolve_call
from ..resolve import _boilerplate

# Friendly-name → Resolve constant suffix
_SYNC_MODES: dict[str, str] = {
    "waveform": "AUDIO_SYNC_WAVEFORM",
    "timecode": "AUDIO_SYNC_TIMECODE",
}

_CHANNEL_KEYWORDS: dict[str, str] = {
    "auto": "AUDIO_SYNC_CHANNEL_AUTOMATIC",
    "automatic": "AUDIO_SYNC_CHANNEL_AUTOMATIC",
    "mix": "AUDIO_SYNC_CHANNEL_MIX",
}


def _walk_media_pool(media_pool, names: list[str]):
    """Depth-first find the first ``MediaPoolItem`` for each name in ``names``.

    Returns ``(found_items, missing_names)``.
    """
    targets = {name: None for name in names}
    queue = [media_pool.GetRootFolder()]
    remaining = set(names)
    while queue and remaining:
        folder = queue.pop(0)
        for clip in folder.GetClipList() or []:
            cname = clip.GetName() or ""
            if cname in remaining:
                targets[cname] = clip
                remaining.discard(cname)
                if not remaining:
                    break
        for sub in folder.GetSubFolderList() or []:
            queue.append(sub)
    found = [targets[n] for n in names if targets[n] is not None]
    missing = [n for n in names if targets[n] is None]
    return found, missing


def _resolve_constant(resolve, suffix: str, label: str) -> int | float:
    """Look up a Resolve constant at runtime; raise on miss."""
    value = getattr(resolve, suffix, None)
    if value is None:
        raise ValueError(
            f"Resolve constant '{suffix}' (for {label}) is not exposed on this Resolve build."
        )
    return value


@mcp.tool
@safe_resolve_call
def cutmaster_auto_sync_audio(
    clip_names: list[str],
    sync_mode: str = "timecode",
    channel: int | str = "auto",
    retain_embedded_audio: bool = False,
    retain_video_metadata: bool = False,
) -> str:
    """Sync audio across a list of media-pool clips.

    Wraps ``MediaPool.AutoSyncAudio([items], {audioSyncSettings})``
    (README line 254). The list must contain at least one video clip and
    one audio clip, and a minimum of two items total.

    Args:
        clip_names: Names of media-pool clips (exact match, e.g.
            ``["cam_a.mp4", "lavalier.wav"]``). The walker is depth-first
            across all bins; first match per name wins.
        sync_mode: ``timecode`` (default — matches by source TC) or
            ``waveform`` (matches audio waveforms).
        channel: For waveform mode, which audio channel to compare on.
            ``auto`` (default), ``mix``, or a positive int (1-based
            channel offset). Ignored in timecode mode.
        retain_embedded_audio: Keep the embedded audio on the video
            clip after sync (default False — embedded audio is removed
            after replacement).
        retain_video_metadata: Carry the source video's metadata onto
            the sync result (default False).

    Returns JSON with sync result + counts. Raises ``ValueError`` (caught
    by ``@safe_resolve_call``) when clips can't be found or
    sync_mode/channel values are invalid.
    """
    if not clip_names or len(clip_names) < 2:
        raise ValueError("clip_names must contain at least 2 entries (≥1 video + ≥1 audio).")

    mode_key = sync_mode.strip().lower()
    if mode_key not in _SYNC_MODES:
        raise ValueError(f"Invalid sync_mode '{sync_mode}'. Allowed: waveform / timecode.")

    resolve, _, media_pool = _boilerplate()
    found, missing = _walk_media_pool(media_pool, clip_names)
    if missing:
        return json.dumps(
            {"error": "clips_not_found", "missing": missing, "found": [c.GetName() for c in found]},
            indent=2,
        )

    # Build settings dict using runtime constant lookup.
    settings: dict = {
        _resolve_constant(resolve, "AUDIO_SYNC_MODE", "sync mode key"): _resolve_constant(
            resolve, _SYNC_MODES[mode_key], "sync mode value"
        ),
        _resolve_constant(
            resolve, "AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO", "retain audio key"
        ): retain_embedded_audio,
        _resolve_constant(
            resolve, "AUDIO_SYNC_RETAIN_VIDEO_METADATA", "retain metadata key"
        ): retain_video_metadata,
    }

    # Channel — only meaningful for waveform mode but README doesn't say the
    # key is rejected in timecode mode, so always pass it.
    channel_value: int | float
    if isinstance(channel, str):
        ch_key = channel.strip().lower()
        if ch_key in _CHANNEL_KEYWORDS:
            channel_value = _resolve_constant(
                resolve, _CHANNEL_KEYWORDS[ch_key], f"channel keyword '{ch_key}'"
            )
        else:
            try:
                channel_value = int(ch_key)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid channel '{channel}'. Allowed: 'auto', 'mix', or a 1-based int."
                ) from exc
    else:
        channel_value = int(channel)

    if (
        isinstance(channel_value, int)
        and channel_value <= 0
        and channel_value
        not in (
            int(getattr(resolve, "AUDIO_SYNC_CHANNEL_AUTOMATIC", -1)),
            int(getattr(resolve, "AUDIO_SYNC_CHANNEL_MIX", -2)),
        )
    ):
        raise ValueError("Numeric channel must be >= 1 (or 'auto'/'mix').")

    settings[_resolve_constant(resolve, "AUDIO_SYNC_CHANNEL_NUMBER", "channel key")] = channel_value

    ok = media_pool.AutoSyncAudio(found, settings)
    return json.dumps(
        {
            "synced": bool(ok),
            "clip_count": len(found),
            "clips": [c.GetName() for c in found],
            "sync_mode": mode_key,
        },
        indent=2,
    )
