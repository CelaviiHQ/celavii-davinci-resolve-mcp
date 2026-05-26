"""Resolve-native media-pool transcription (Studio).

Distinct from ``cutmaster_transcribe_timeline`` in
``intelligence/transcription.py``:

- This module triggers Resolve's **own** transcription engine on a media-pool
  clip (or an entire folder), embedding the transcript into the clip's
  metadata where Resolve uses it for smart bins, captions-from-audio, and
  the inspector's transcript pane.
- ``cutmaster_transcribe_timeline`` extracts timeline audio to a WAV and
  ships it out to Deepgram or Gemini, returning a transcript *file* on disk.

Both are useful; agents pick the right one for the consumer.

API surface (README lines 266–267, 307–308):
- ``mediaPoolItem.TranscribeAudio()``  / ``mediaPoolItem.ClearTranscription()``
- ``folder.TranscribeAudio()``         / ``folder.ClearTranscription()`` (bulk)

Both methods return ``Bool``. Verified live on Resolve 21.0.0b.20 Studio.
"""

import json

from ..config import mcp
from ..errors import safe_resolve_call
from ..resolve import _boilerplate, _require_studio


def _find_clip(media_pool, clip_name: str):
    """Walk the media pool depth-first and return the first clip matching ``clip_name``."""
    queue = [media_pool.GetRootFolder()]
    while queue:
        folder = queue.pop(0)
        for clip in folder.GetClipList() or []:
            if (clip.GetName() or "") == clip_name:
                return clip
        for sub in folder.GetSubFolderList() or []:
            queue.append(sub)
    return None


def _find_folder(media_pool, folder_name: str):
    """Return the folder whose ``GetName()`` matches; ``""`` returns the root."""
    if not folder_name:
        return media_pool.GetRootFolder()
    queue = [media_pool.GetRootFolder()]
    while queue:
        folder = queue.pop(0)
        if (folder.GetName() or "") == folder_name:
            return folder
        for sub in folder.GetSubFolderList() or []:
            queue.append(sub)
    return None


@mcp.tool
@safe_resolve_call
def cutmaster_transcribe_clip(clip_name: str) -> str:
    """Trigger Resolve's transcription on a single media-pool clip (Studio).

    Args:
        clip_name: Exact name of the media-pool clip (e.g. ``waving.mp4``).
            The walker is depth-first across all bins; the first match
            wins. Pass the full filename to disambiguate.

    Returns the clip name + a success flag. The transcript is written
    into the clip's Resolve metadata (visible in the inspector's
    Transcript pane and surfaced by smart bins).
    """
    if not clip_name.strip():
        raise ValueError("clip_name is required.")
    _require_studio("TranscribeAudio")
    _, _, media_pool = _boilerplate()
    clip = _find_clip(media_pool, clip_name)
    if clip is None:
        return f"Clip '{clip_name}' not found in the media pool."
    ok = clip.TranscribeAudio()
    if not ok:
        return (
            f"Resolve refused to transcribe '{clip_name}'. "
            "Common causes: clip has no audio, or transcription engine is busy."
        )
    return json.dumps({"transcribed": True, "clip": clip_name}, indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_clear_clip_transcription(clip_name: str) -> str:
    """Clear Resolve's transcription from a media-pool clip (Studio).

    Args:
        clip_name: Exact name of the media-pool clip.

    Removes the transcript from the clip's metadata. Useful before
    re-transcribing with different settings.
    """
    if not clip_name.strip():
        raise ValueError("clip_name is required.")
    _require_studio("ClearTranscription")
    _, _, media_pool = _boilerplate()
    clip = _find_clip(media_pool, clip_name)
    if clip is None:
        return f"Clip '{clip_name}' not found in the media pool."
    ok = clip.ClearTranscription()
    if not ok:
        return f"Failed to clear transcription on '{clip_name}'."
    return f"Cleared transcription on '{clip_name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_transcribe_folder(folder_name: str = "") -> str:
    """Bulk-transcribe every clip in a media-pool folder (Studio).

    Args:
        folder_name: Folder name to transcribe. Empty = root folder
            (transcribes everything in the media pool, including
            nested folders).

    Folder-level ``TranscribeAudio`` recurses into nested folders.
    Useful for "transcribe all my dailies before I start cutting".
    """
    _require_studio("TranscribeAudio")
    _, _, media_pool = _boilerplate()
    folder = _find_folder(media_pool, folder_name)
    if folder is None:
        return f"Folder '{folder_name}' not found."
    ok = folder.TranscribeAudio()
    if not ok:
        return f"Resolve refused to transcribe folder '{folder.GetName()}'."
    return json.dumps(
        {"transcribed": True, "folder": folder.GetName() or "(root)"},
        indent=2,
    )
