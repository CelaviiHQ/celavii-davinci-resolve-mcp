"""Fusion comp introspection — pre-flight inspection of comps before mutation.

Pure-read wrappers around ``Comp.GetToolList()`` / ``Tool.GetAttrs()`` /
``Tool.GetInputList()`` so a vfx agent can probe a Fusion comp's structure
*before* calling any of the mutating fusion tools. Two flavours:

- ``cutmaster_fusion_boundary_report`` — terse summary: tool count, input
  tools, output tool, sources, named tools, render range. Use this first.
- ``cutmaster_fusion_probe_comp`` — full graph snapshot with pagination
  cursor for deep comps. Use this when the boundary report flags something
  worth investigating.

Two-helpers (``list_animated_inputs``, ``check_render_safe``) layer on top
of those for common questions.

Verified live on Resolve 21.0.0b.20 — see ``api_verification.md``.
"""

from __future__ import annotations

import base64
import json

from ..config import mcp
from ..errors import safe_resolve_call
from ..resolve import _boilerplate
from .timeline_edit import _get_timeline_item

# Tool IDs that act as inputs/outputs in a Fusion comp graph.
_INPUT_TOOL_IDS: frozenset[str] = frozenset(
    {"MediaIn", "Background", "FastNoise", "PlasmaNoise", "Text", "TextPlus", "Loader"}
)
_OUTPUT_TOOL_IDS: frozenset[str] = frozenset({"MediaOut", "Saver"})


def _get_comp(project, track_type: str, track_index: int, item_index: int, comp_index: int):
    """Return the requested Fusion comp on a timeline item.

    Raises ``ValueError`` (caught by ``@safe_resolve_call``) when the item
    has no comps or the index is out of range.
    """
    _, item = _get_timeline_item(project, track_type, track_index, item_index)
    count = int(item.GetFusionCompCount() or 0)
    if count <= 0:
        raise ValueError(f"Item '{item.GetName()}' has no Fusion comps.")
    if comp_index < 1 or comp_index > count:
        raise ValueError(
            f"comp_index {comp_index} out of range (1..{count}) on '{item.GetName()}'."
        )
    comp = item.GetFusionCompByIndex(comp_index)
    if comp is None:
        raise ValueError(f"Comp at index {comp_index} on '{item.GetName()}' could not be loaded.")
    return item, comp


def _tools_iter(comp):
    """Resolve ``Comp.GetToolList()`` regardless of dict-vs-list return shape."""
    tools = comp.GetToolList() or {}
    if isinstance(tools, dict):
        # Resolve hands back a 1-based dict; preserve order by sorted key.
        for k in sorted(tools.keys()):
            yield tools[k]
    else:
        yield from tools


def _tool_summary(tool) -> dict:
    """Minimal tool fingerprint — name + id + a couple of useful attrs."""
    try:
        attrs = tool.GetAttrs() or {}
    except Exception:
        attrs = {}
    tid = attrs.get("TOOLS_RegID", attrs.get("TOOLS_Name", "?"))
    name = attrs.get("TOOLS_Name", tid)
    return {
        "name": name,
        "id": tid,
        "is_input": tid in _INPUT_TOOL_IDS,
        "is_output": tid in _OUTPUT_TOOL_IDS,
    }


def _encode_cursor(index: int) -> str:
    return base64.urlsafe_b64encode(f"i:{index}".encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {exc}") from None
    if not raw.startswith("i:"):
        raise ValueError("Invalid cursor format.")
    return int(raw[2:])


@mcp.tool
@safe_resolve_call
def cutmaster_fusion_boundary_report(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
    comp_index: int = 1,
) -> str:
    """Summarise a Fusion comp before any mutation.

    Returns counts + sources + the output tool name + render range. Useful
    as a pre-flight check before `cutmaster_fusion_add_tool` or
    `cutmaster_fusion_render` so the agent can spot "this comp has 3
    MediaOuts, my AddTool will go nowhere" before making a mess.

    Args:
        track_type: ``video`` (typical) / ``audio`` / ``subtitle``.
        track_index: 1-based track index.
        item_index: 0-based item index.
        comp_index: 1-based comp index (most items have 1).
    """
    _, project, _ = _boilerplate()
    item, comp = _get_comp(project, track_type, track_index, item_index, comp_index)

    tools = list(_tools_iter(comp))
    summaries = [_tool_summary(t) for t in tools]
    inputs = [s["name"] for s in summaries if s["is_input"]]
    outputs = [s["name"] for s in summaries if s["is_output"]]

    attrs = {}
    try:
        attrs = comp.GetAttrs() or {}
    except Exception:
        pass

    return json.dumps(
        {
            "item": item.GetName(),
            "comp_index": comp_index,
            "tool_count": len(tools),
            "input_tools": inputs,
            "output_tools": outputs,
            "render_start": attrs.get("COMPN_RenderStart"),
            "render_end": attrs.get("COMPN_RenderEnd"),
            "global_start": attrs.get("COMPN_GlobalStart"),
            "global_end": attrs.get("COMPN_GlobalEnd"),
        },
        indent=2,
    )


@mcp.tool
@safe_resolve_call
def cutmaster_fusion_probe_comp(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
    comp_index: int = 1,
    cursor: str = "",
    limit: int = 100,
) -> str:
    """Walk every tool in a Fusion comp; paginated for deep graphs.

    Returns each tool's name, id, and input list (input IDs only — values
    aren't expanded to keep payload small). Pass back the ``next_cursor``
    field in subsequent calls to continue.

    Args:
        track_type / track_index / item_index / comp_index: target comp.
        cursor: opaque cursor from a prior call. Empty for first page.
        limit: max tools per page (1..500, default 100). Use larger pages
            for fast surveys, smaller for memory-conscious clients.
    """
    if not (1 <= limit <= 500):
        raise ValueError("limit must be 1..500.")
    start = _decode_cursor(cursor or None)

    _, project, _ = _boilerplate()
    _, comp = _get_comp(project, track_type, track_index, item_index, comp_index)

    tools = list(_tools_iter(comp))
    page = tools[start : start + limit]
    next_idx = start + len(page)
    next_cursor = _encode_cursor(next_idx) if next_idx < len(tools) else None

    entries = []
    for t in page:
        info = _tool_summary(t)
        try:
            input_list = t.GetInputList() or {}
            info["inputs"] = (
                list(input_list.keys()) if isinstance(input_list, dict) else list(input_list)
            )
        except Exception:
            info["inputs"] = []
        entries.append(info)

    return json.dumps(
        {
            "page": entries,
            "page_size": len(page),
            "total": len(tools),
            "next_cursor": next_cursor,
        },
        indent=2,
    )


@mcp.tool
@safe_resolve_call
def cutmaster_fusion_list_animated_inputs(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
    comp_index: int = 1,
) -> str:
    """List inputs that have a keyframe / bezier / expression modifier attached.

    Walks every tool's input list and reports the ones with a modifier
    (Resolve marks animated inputs via ``GetExpression()`` returning a
    non-empty string or ``GetConnectedOutput()`` returning a BezierSpline
    /modifier tool). Useful as a "what's animated in this comp" overview
    before editing values.

    Best-effort: ``GetExpression`` is not on every Resolve build; we fall
    back to a connected-output check.
    """
    _, project, _ = _boilerplate()
    _, comp = _get_comp(project, track_type, track_index, item_index, comp_index)

    animated: list[dict] = []
    for tool in _tools_iter(comp):
        try:
            tool_name = (tool.GetAttrs() or {}).get("TOOLS_Name", "?")
        except Exception:
            tool_name = "?"
        try:
            input_list = tool.GetInputList() or {}
        except Exception:
            input_list = {}
        for _, inp in input_list.items() if isinstance(input_list, dict) else enumerate(input_list):
            try:
                expr = inp.GetExpression() if callable(getattr(inp, "GetExpression", None)) else ""
            except Exception:
                expr = ""
            try:
                connected = (
                    inp.GetConnectedOutput()
                    if callable(getattr(inp, "GetConnectedOutput", None))
                    else None
                )
            except Exception:
                connected = None
            if expr or connected is not None:
                try:
                    iname = (
                        inp.Name
                        if hasattr(inp, "Name")
                        else ((inp.GetAttrs() or {}).get("INPS_Name", "?"))
                    )
                except Exception:
                    iname = "?"
                animated.append(
                    {
                        "tool": tool_name,
                        "input": iname,
                        "expression": expr or None,
                        "connected": bool(connected),
                    }
                )

    return json.dumps({"animated_inputs": animated, "count": len(animated)}, indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_fusion_check_render_safe(
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
    comp_index: int = 1,
) -> str:
    """Boolean check + reasons: is this comp safe to render right now?

    Returns ``{"safe": bool, "reasons": [...]}``. Reasons populated when:

    - Comp has zero output tools (no `MediaOut`/`Saver`).
    - Comp has zero input tools (nothing to render).
    - Comp has zero tools.

    Doesn't catch every failure mode (Resolve's render path has more
    checks), but flags the structural ones an agent can fix before
    triggering a render that's guaranteed to fail.
    """
    _, project, _ = _boilerplate()
    _, comp = _get_comp(project, track_type, track_index, item_index, comp_index)

    tools = list(_tools_iter(comp))
    summaries = [_tool_summary(t) for t in tools]
    reasons: list[str] = []
    if not tools:
        reasons.append("Comp has no tools.")
    if not any(s["is_input"] for s in summaries):
        reasons.append("Comp has no input tools (MediaIn / Background / etc.).")
    if not any(s["is_output"] for s in summaries):
        reasons.append("Comp has no output tools (MediaOut / Saver).")

    return json.dumps({"safe": not reasons, "reasons": reasons, "tool_count": len(tools)}, indent=2)
