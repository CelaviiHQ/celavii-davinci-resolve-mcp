"""Resolve-native clip-level AI ops — Magic Mask, Smart Reframe, Stabilize.

Studio-only. Every wrapper is a thin pass-through to a single Resolve
``TimelineItem`` method documented at:

- ``CreateMagicMask(mode)``     — README line 479 (mode ∈ "F" / "B" / "BI")
- ``RegenerateMagicMask()``     — README line 480
- ``SmartReframe()``            — README line 482
- ``Stabilize()``               — README line 481

All four take zero or one args. The proposal's two-step
``SetProperty + trigger`` patterns for SmartReframe / Stabilize are not
needed — Resolve does not expose stabilization tuning via scripting (the
property keys ``StabilizationMethod`` / ``Smooth`` etc. are not in the
documented `SetProperty` allowlist). Users tune in the inspector first;
these wrappers just trigger.

Verified live on Resolve 21.0.0b.20 Studio. See ``api_verification.md``.
"""

from ..config import mcp
from ..errors import safe_resolve_call
from ..resolve import _boilerplate, _require_studio
from .timeline_edit import _get_timeline_item

_MAGIC_MASK_MODES: dict[str, str] = {
    "f": "F",
    "forward": "F",
    "b": "B",
    "backward": "B",
    "bi": "BI",
    "bidirectional": "BI",
    "bidir": "BI",
}


def _normalise_mask_mode(mode: str) -> str:
    """Accept friendly names + Resolve's single-letter codes; raise on miss."""
    key = (mode or "").strip().lower()
    if key in _MAGIC_MASK_MODES:
        return _MAGIC_MASK_MODES[key]
    raise ValueError(
        f"Invalid magic-mask mode '{mode}'. "
        f"Allowed: 'F'/'forward', 'B'/'backward', 'BI'/'bidirectional'."
    )


@mcp.tool
@safe_resolve_call
def cutmaster_create_magic_mask(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
    mode: str = "F",
) -> str:
    """Create a Magic Mask on a timeline item (Resolve Studio).

    Args:
        track_type: ``video`` (typical) / ``audio`` / ``subtitle``.
        track_index: 1-based track index.
        item_index: 0-based item index within the track.
        mode: Tracking direction. ``F`` (forward — default), ``B`` (backward),
            or ``BI`` (bidirectional). Friendly names ``forward`` /
            ``backward`` / ``bidirectional`` accepted.

    Magic Mask generates a subject-isolating mask via Resolve's AI on the
    selected item. The clip's color page gets a new mask node; the item
    itself is not modified destructively.
    """
    _require_studio("CreateMagicMask")
    resolve_mode = _normalise_mask_mode(mode)
    _, project, _ = _boilerplate()
    _, item = _get_timeline_item(project, track_type, track_index, item_index)
    ok = item.CreateMagicMask(resolve_mode)
    if not ok:
        return f"Failed to create Magic Mask (mode={resolve_mode}) on '{item.GetName()}'."
    return f"Created Magic Mask (mode={resolve_mode}) on '{item.GetName()}'."


@mcp.tool
@safe_resolve_call
def cutmaster_regenerate_magic_mask(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
) -> str:
    """Regenerate an existing Magic Mask on a timeline item (Resolve Studio).

    Re-runs the AI tracker on the existing mask. Useful after the user has
    nudged a tracking point in the inspector. No-op if no mask exists on
    the clip.
    """
    _require_studio("RegenerateMagicMask")
    _, project, _ = _boilerplate()
    _, item = _get_timeline_item(project, track_type, track_index, item_index)
    ok = item.RegenerateMagicMask()
    if not ok:
        return (
            f"Failed to regenerate Magic Mask on '{item.GetName()}'. "
            "Confirm a mask already exists on this clip."
        )
    return f"Regenerated Magic Mask on '{item.GetName()}'."


@mcp.tool
@safe_resolve_call
def cutmaster_smart_reframe(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
) -> str:
    """Trigger Smart Reframe on a timeline item (Resolve Studio).

    Smart Reframe uses Resolve's AI to track the subject and reframe the
    clip to the project's **timeline aspect ratio**. To control the target
    aspect (e.g. 9:16), set the project's timeline format first via
    ``cutmaster_set_timeline_format(width=1080, height=1920, fps=...)``,
    then call this tool. Resolve does not expose a per-call target-aspect
    parameter — reframing always uses the active timeline aspect.

    Blocks the calling thread for the full clip duration on this Resolve
    version (no scripting-side cancellation). Plan accordingly for long
    clips.
    """
    _require_studio("SmartReframe")
    _, project, _ = _boilerplate()
    _, item = _get_timeline_item(project, track_type, track_index, item_index)
    ok = item.SmartReframe()
    if not ok:
        return f"Failed to Smart Reframe '{item.GetName()}'."
    return f"Smart Reframed '{item.GetName()}'."


@mcp.tool
@safe_resolve_call
def cutmaster_stabilize(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
) -> str:
    """Stabilize a timeline item (Resolve Studio).

    Runs Resolve's stabilization analysis on the clip using whatever
    stabilization settings are currently set on the item's inspector
    (StabilizationMode, CameraLock, Zoom, Smooth, Strength, etc.).
    Resolve does **not** expose those tuning parameters via scripting on
    this version — users adjust them in the inspector before triggering.

    Blocks the calling thread for the full clip duration. No
    scripting-side cancellation.
    """
    _require_studio("Stabilize")
    _, project, _ = _boilerplate()
    _, item = _get_timeline_item(project, track_type, track_index, item_index)
    ok = item.Stabilize()
    if not ok:
        return f"Failed to stabilize '{item.GetName()}'."
    return f"Stabilized '{item.GetName()}'."
