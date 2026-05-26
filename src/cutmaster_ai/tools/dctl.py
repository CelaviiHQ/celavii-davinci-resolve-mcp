"""DCTL authoring — list / read / install / validate / template-render.

A DCTL is a CUDA-flavoured C source file (``.dctl``) Resolve picks up
from a known LUT/DCTL directory. Same shape as the Fuse plugin module:

- Read-only inspectors (``list_dctls`` / ``get_dctl_search_paths`` /
  ``read_dctl``).
- Write ops confined to the user-level DCTL directory.
- Source validation (``validate_dctl_source``) — checks for the required
  ``transform`` signature.
- Five bundled templates (``identity``, ``lift_gamma_gain``,
  ``single_axis_curve``, ``false_color``, ``gamut_clip``).
- ``apply_dctl_to_node`` — bridges to Resolve's LUT setter by resolving
  a DCTL by name and calling ``cutmaster_set_lut`` under the hood.

Verified live on macOS — see ``api_verification.md``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from ..config import mcp
from ..errors import safe_resolve_call
from ..resolve import _boilerplate

_TEMPLATE_DIR = Path(__file__).resolve().parent / "_dctl_templates"

_BUNDLED_TEMPLATES: dict[str, dict] = {
    "identity": {
        "file": "identity.dctl",
        "description": "Identity pass-through. Replace `transform()` with real math.",
        "params": ["UI_PARAMS"],
    },
    "lift_gamma_gain": {
        "file": "lift_gamma_gain.dctl",
        "description": "ASC Lift / Gamma / Gain primary — three sliders.",
        "params": [],
    },
    "single_axis_curve": {
        "file": "single_axis_curve.dctl",
        "description": "Smoothstep luminance curve with strength slider.",
        "params": [],
    },
    "false_color": {
        "file": "false_color.dctl",
        "description": "Exposure-zone false-colour overlay; toggle via checkbox.",
        "params": [],
    },
    "gamut_clip": {
        "file": "gamut_clip.dctl",
        "description": "Last-stop RGB ceiling + desaturation clipper.",
        "params": [],
    },
}


def _user_dctl_dir() -> Path:
    override = os.environ.get("CUTMASTER_DCTL_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "LUT"
        )
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "LUT"
    return Path.home() / ".local" / "share" / "DaVinciResolve" / "LUT"


def _system_dctl_dir() -> Path:
    if sys.platform == "darwin":
        return Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT")
    if sys.platform == "win32":
        program_data = os.environ.get("PROGRAMDATA", "C:/ProgramData")
        return Path(program_data) / "Blackmagic Design" / "DaVinci Resolve" / "LUT"
    return Path("/opt/resolve/LUT")


def _safe_user_path(name: str, subfolder: str = "") -> Path:
    """Resolve ``name`` (optionally inside ``subfolder``) to a path inside the user LUT dir."""
    if not name or ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid dctl name '{name}'.")
    if not name.endswith(".dctl"):
        name = name + ".dctl"
    if subfolder and (".." in subfolder or subfolder.startswith("/") or "\\" in subfolder):
        raise ValueError(f"Invalid subfolder '{subfolder}'.")
    user_dir = _user_dctl_dir()
    if subfolder:
        target_dir = (user_dir / subfolder).resolve()
    else:
        target_dir = user_dir.resolve()
    try:
        target_dir.relative_to(user_dir.resolve())
    except ValueError as exc:
        raise ValueError("Refusing to write outside the user DCTL directory.") from exc
    return target_dir / name


# ---------------------------------------------------------------------------
# Inspectors
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_get_dctl_search_paths() -> str:
    """Return the user + system DCTL directories for the current platform."""
    return json.dumps(
        {
            "user_dir": str(_user_dctl_dir()),
            "user_dir_exists": _user_dctl_dir().is_dir(),
            "system_dir": str(_system_dctl_dir()),
            "system_dir_exists": _system_dctl_dir().is_dir(),
            "platform": sys.platform,
        },
        indent=2,
    )


def _list_dir(directory: Path) -> list[dict]:
    if not directory.is_dir():
        return []
    out: list[dict] = []
    for entry in directory.rglob("*.dctl"):
        out.append(
            {
                "name": entry.name,
                "relative": str(entry.relative_to(directory)),
                "path": str(entry),
                "size_bytes": entry.stat().st_size,
            }
        )
    out.sort(key=lambda x: x["relative"])
    return out


@mcp.tool
@safe_resolve_call
def cutmaster_list_dctls() -> str:
    """List every ``.dctl`` in the user + system search paths (recursive)."""
    return json.dumps(
        {
            "user": _list_dir(_user_dctl_dir()),
            "system": _list_dir(_system_dctl_dir()),
        },
        indent=2,
    )


@mcp.tool
@safe_resolve_call
def cutmaster_read_dctl(name: str) -> str:
    """Return the C source of a DCTL by name.

    Looks in user dir then system dir. Supports nested filenames via
    ``subfolder/name`` — but no ``..`` traversal.
    """
    if not name.strip():
        raise ValueError("name is required.")
    if ".." in name:
        raise ValueError("'..' not allowed in name.")
    needle = name if name.endswith(".dctl") else name + ".dctl"
    for directory in (_user_dctl_dir(), _system_dctl_dir()):
        candidate = directory / needle
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="replace")
    return f"DCTL '{needle}' not found in user or system paths."


# ---------------------------------------------------------------------------
# Write ops (user dir only)
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_install_dctl(source_path: str, subfolder: str = "", name: str = "") -> str:
    """Copy a ``.dctl`` from disk into the user-level LUT directory.

    Args:
        source_path: Absolute path to the source ``.dctl``.
        subfolder: Optional subdirectory under the user LUT dir
            (e.g. ``Custom``). Must not contain ``..``.
        name: Destination filename without ``.dctl``. Empty = source stem.
    """
    src = Path(source_path).expanduser().resolve()
    if not src.is_file():
        return f"Source '{source_path}' not found."
    if src.suffix.lower() != ".dctl":
        return f"Source '{source_path}' is not a .dctl file."
    dest = _safe_user_path(name.strip() or src.stem, subfolder)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return json.dumps({"installed": True, "path": str(dest)}, indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_remove_dctl(name: str, subfolder: str = "") -> str:
    """Remove a user-level DCTL. System DCTLs are untouchable."""
    target = _safe_user_path(name, subfolder)
    if not target.is_file():
        return f"User-level DCTL '{target.name}' not found at '{target.parent}'."
    target.unlink()
    return json.dumps({"removed": True, "path": str(target)}, indent=2)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_dctl(source: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if "__DEVICE__" not in source:
        issues.append(
            "missing __DEVICE__ qualifier — DCTL requires at least one __DEVICE__ function"
        )
    if "transform" not in source:
        issues.append(
            "missing transform(...) function — DCTL needs a transform() that returns float3"
        )
    if "make_float3" not in source:
        issues.append("missing make_float3 return — transform() must return a float3")
    open_braces = source.count("{")
    close_braces = source.count("}")
    if open_braces != close_braces:
        issues.append(
            f"unbalanced braces: {open_braces} '{{' vs {close_braces} '}}' — DCTL will fail to compile"
        )
    if "#include" in source or "#define" in source:
        # not banned, just informative
        pass
    if "system(" in source:
        issues.append("banned call 'system(' present — DCTL must be pure compute")
    return (not issues, issues)


@mcp.tool
@safe_resolve_call
def cutmaster_validate_dctl_source(c_source: str) -> str:
    """Lint DCTL C source before installing.

    Checks: required ``transform`` function, ``__DEVICE__`` qualifier,
    ``make_float3`` return, balanced braces, no ``system(`` calls.
    """
    if not c_source:
        raise ValueError("c_source is empty.")
    valid, issues = _validate_dctl(c_source)
    return json.dumps({"valid": valid, "issues": issues}, indent=2)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_list_dctl_templates() -> str:
    """List the bundled DCTL scaffolds you can render via ``render_dctl_template``."""
    payload = {
        tid: {"description": meta["description"], "params": meta["params"]}
        for tid, meta in _BUNDLED_TEMPLATES.items()
    }
    return json.dumps({"templates": payload, "count": len(payload)}, indent=2)


def _render_template(tid: str, params: dict) -> str:
    if tid not in _BUNDLED_TEMPLATES:
        raise ValueError(f"Unknown template '{tid}'. Allowed: {sorted(_BUNDLED_TEMPLATES)}.")
    meta = _BUNDLED_TEMPLATES[tid]
    required = meta["params"]
    missing = [p for p in required if p not in params]
    if missing:
        raise ValueError(f"Missing params for '{tid}': {missing}")
    body = (_TEMPLATE_DIR / meta["file"]).read_text(encoding="utf-8")
    for key in required:
        body = body.replace("{{" + key + "}}", str(params[key]))
    return body


@mcp.tool
@safe_resolve_call
def cutmaster_render_dctl_template(
    template_id: str,
    params: dict | None = None,
    output_path: str = "",
) -> str:
    """Render a bundled DCTL scaffold with ``params`` substituted in.

    Most templates take zero ``params``; ``identity`` accepts an
    optional ``UI_PARAMS`` substitution if you want to declare custom
    sliders on top of the pass-through.

    Args:
        template_id: ``identity`` / ``lift_gamma_gain`` /
            ``single_axis_curve`` / ``false_color`` / ``gamut_clip``.
        params: Substitution dict (empty for most templates).
        output_path: Optional absolute path. Empty = return source only.
    """
    source = _render_template(template_id, params or {})
    valid, issues = _validate_dctl(source)
    written = False
    written_path = None
    if output_path:
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        written = True
        written_path = str(path)
    return json.dumps(
        {
            "template": template_id,
            "valid": valid,
            "issues": issues,
            "source": source,
            "written": written,
            "path": written_path,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Resolve bridge — apply a DCTL to a node
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_apply_dctl_to_node(
    node_index: int,
    dctl_name: str,
    track_type: str = "video",
    track_index: int = 1,
    item_index: int = 0,
    layer_index: int = 1,
) -> str:
    """Apply a DCTL to a specific colour-graph node via ``Graph.SetLUT``.

    Resolves the DCTL by name across user + system search dirs, then
    calls ``Graph.SetLUT(node_index, relative_dctl_path)``. The path
    Resolve expects is relative to its LUT-discovery roots, so we hand
    it the absolute path and let Resolve match.

    Args:
        node_index: 1-based node index on the clip's colour graph.
        dctl_name: DCTL filename (with or without ``.dctl``). Searched
            recursively under user + system DCTL dirs.
        track_type / track_index / item_index / layer_index: target clip
            + node-stack layer.
    """
    from .timeline_edit import _get_timeline_item

    needle = dctl_name if dctl_name.endswith(".dctl") else dctl_name + ".dctl"
    found_path: Path | None = None
    for directory in (_user_dctl_dir(), _system_dctl_dir()):
        for candidate in directory.rglob(needle):
            found_path = candidate
            break
        if found_path is not None:
            break
    if found_path is None:
        return f"DCTL '{needle}' not found in user or system search paths."

    _, project, _ = _boilerplate()
    _, item = _get_timeline_item(project, track_type, track_index, item_index)
    graph = item.GetNodeGraph(layer_index)
    if graph is None:
        return f"No node graph at layer {layer_index} on '{item.GetName()}'."
    ok = graph.SetLUT(node_index, str(found_path))
    if not ok:
        return (
            f"Resolve refused SetLUT({node_index}, '{found_path.name}'). "
            "Confirm the node index is valid and the DCTL is reachable."
        )
    return json.dumps(
        {
            "applied": True,
            "node_index": node_index,
            "dctl": found_path.name,
            "path": str(found_path),
        },
        indent=2,
    )
