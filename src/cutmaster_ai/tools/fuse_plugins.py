"""Fuse plugin authoring — list / read / install / validate / template-render.

A Fuse is a Lua file (``.fuse``) Resolve picks up from a known directory.
This module provides:

- Read-only inspectors (``list_fuses`` / ``get_fuse_search_paths`` /
  ``read_fuse``).
- Write operations confined to the user-level Fuses directory
  (``install_fuse`` / ``remove_fuse``). The system directory is read-only.
- Source validation (``validate_fuse_source``) — checks for required
  ``FuRegisterClass`` block + bans known-bad calls (``os.execute``,
  ``io.popen``, ``loadfile``) before installing.
- Template rendering (``list_fuse_templates`` / ``render_fuse_template``)
  for the four bundled scaffolds.
- ``refresh_fuses`` returns the latest list after a write — Resolve hot-
  loads Fuses on next comp open.

All paths are resolved through the user-level dir to prevent traversal
attacks; nothing here writes to the system Fuses directory. Override
``CUTMASTER_FUSE_DIR`` for tests.

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

# ---------------------------------------------------------------------------
# Search paths
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).resolve().parent / "_fuse_templates"

_BUNDLED_TEMPLATES: dict[str, dict] = {
    "pass_through": {
        "file": "pass_through.fuse",
        "description": "Minimal pass-through Fuse — input → output, zero processing. Edit `Process()` to add work.",
        "params": ["NAME", "CLASS_ID", "CATEGORY", "DESCRIPTION"],
    },
    "single_input_image_op": {
        "file": "single_input_image_op.fuse",
        "description": "One image input + one float slider. Per-pixel processing via ProcessPixels.",
        "params": [
            "NAME",
            "CLASS_ID",
            "CATEGORY",
            "DESCRIPTION",
            "SLIDER_LABEL",
            "SLIDER_MIN",
            "SLIDER_MAX",
            "SLIDER_DEFAULT",
        ],
    },
    "dual_input_blend": {
        "file": "dual_input_blend.fuse",
        "description": "Two image inputs + blend slider. Demonstrates multi-input setup.",
        "params": ["NAME", "CLASS_ID", "CATEGORY", "DESCRIPTION"],
    },
    "time_modulator": {
        "file": "time_modulator.fuse",
        "description": "Time-driven modulation via req:GetTime() — animated effects without keyframes.",
        "params": ["NAME", "CLASS_ID", "CATEGORY", "DESCRIPTION"],
    },
}


def _user_fuse_dir() -> Path:
    """Return the user-level Fuses directory (override via env)."""
    override = os.environ.get("CUTMASTER_FUSE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Fusion"
            / "Fuses"
        )
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Fuses"
    return Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / "Fuses"


def _system_fuse_dir() -> Path:
    """Return the system-level Fuses directory (read-only for us)."""
    if sys.platform == "darwin":
        return Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Fuses")
    if sys.platform == "win32":
        program_data = os.environ.get("PROGRAMDATA", "C:/ProgramData")
        return Path(program_data) / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Fuses"
    return Path("/opt/resolve/Fusion/Fuses")


def _safe_user_path(name: str) -> Path:
    """Resolve ``name`` to a file inside the user Fuses dir. Rejects traversal."""
    if not name or name.endswith("/") or ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid fuse name '{name}'.")
    if not name.endswith(".fuse"):
        name = name + ".fuse"
    user_dir = _user_fuse_dir()
    target = (user_dir / name).resolve()
    # Re-anchor on user_dir to ensure target is inside it
    try:
        target.relative_to(user_dir.resolve())
    except ValueError as exc:
        raise ValueError("Refusing to write outside the user Fuses directory.") from exc
    return target


# ---------------------------------------------------------------------------
# Inspectors
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_get_fuse_search_paths() -> str:
    """Return the user + system Fuse directories for the current platform."""
    return json.dumps(
        {
            "user_dir": str(_user_fuse_dir()),
            "user_dir_exists": _user_fuse_dir().is_dir(),
            "system_dir": str(_system_fuse_dir()),
            "system_dir_exists": _system_fuse_dir().is_dir(),
            "platform": sys.platform,
        },
        indent=2,
    )


def _list_dir(directory: Path) -> list[dict]:
    if not directory.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(directory.iterdir()):
        if entry.suffix.lower() != ".fuse":
            continue
        out.append(
            {
                "name": entry.name,
                "path": str(entry),
                "size_bytes": entry.stat().st_size,
            }
        )
    return out


@mcp.tool
@safe_resolve_call
def cutmaster_list_fuses() -> str:
    """List every ``.fuse`` in the user + system search paths."""
    return json.dumps(
        {
            "user": _list_dir(_user_fuse_dir()),
            "system": _list_dir(_system_fuse_dir()),
        },
        indent=2,
    )


@mcp.tool
@safe_resolve_call
def cutmaster_read_fuse(name: str) -> str:
    """Return the Lua source of a Fuse by name.

    Looks in the user dir first, then the system dir. ``name`` may omit the
    ``.fuse`` extension.
    """
    if not name.strip():
        raise ValueError("name is required.")
    needle = name if name.endswith(".fuse") else name + ".fuse"
    for directory in (_user_fuse_dir(), _system_fuse_dir()):
        candidate = directory / needle
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="replace")
    return f"Fuse '{needle}' not found in user or system paths."


# ---------------------------------------------------------------------------
# Write ops (user dir only)
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_install_fuse(source_path: str, name: str = "") -> str:
    """Copy a ``.fuse`` from disk into the user-level Fuses directory.

    Args:
        source_path: Absolute path to the ``.fuse`` to install.
        name: Destination filename (without ``.fuse``). Empty = reuse the
            source filename.

    Refuses paths that contain directory separators or ``..`` traversal.
    The system Fuses directory is never written to.
    """
    src = Path(source_path).expanduser().resolve()
    if not src.is_file():
        return f"Source '{source_path}' not found."
    if src.suffix.lower() != ".fuse":
        return f"Source '{source_path}' is not a .fuse file."
    dest_name = name.strip() or src.stem
    dest = _safe_user_path(dest_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return json.dumps({"installed": True, "path": str(dest)}, indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_remove_fuse(name: str) -> str:
    """Remove a Fuse from the user-level Fuses directory.

    Refuses to touch the system directory. ``name`` may omit ``.fuse``.
    """
    target = _safe_user_path(name)
    if not target.is_file():
        return f"User-level Fuse '{target.name}' not found."
    target.unlink()
    return json.dumps({"removed": True, "path": str(target)}, indent=2)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_BANNED_LUA_CALLS = ("os.execute", "io.popen", "loadfile(", "dofile(")


def _validate_lua(source: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if "FuRegisterClass" not in source:
        issues.append("missing FuRegisterClass(...) call — Fuse will not register")
    if "function Create" not in source and "Create()" not in source:
        issues.append("missing Create() function — Fuse won't expose inputs/outputs")
    if "function Process" not in source and "Process(" not in source:
        issues.append("missing Process(req) function — Fuse will not produce output")
    open_braces = source.count("{")
    close_braces = source.count("}")
    if open_braces != close_braces:
        issues.append(
            f"unbalanced braces: {open_braces} '{{' vs {close_braces} '}}' — Lua will fail to load"
        )
    for banned in _BANNED_LUA_CALLS:
        if banned in source:
            issues.append(f"banned call '{banned}' present — shell execution refused")
    return (not issues, issues)


@mcp.tool
@safe_resolve_call
def cutmaster_validate_fuse_source(lua_source: str) -> str:
    """Lint a Fuse Lua source string before installing.

    Checks: required tables/functions present, balanced braces, no banned
    calls (``os.execute``, ``io.popen``, ``loadfile``, ``dofile``).
    """
    if not lua_source:
        raise ValueError("lua_source is empty.")
    valid, issues = _validate_lua(lua_source)
    return json.dumps({"valid": valid, "issues": issues}, indent=2)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_list_fuse_templates() -> str:
    """List the bundled Fuse scaffolds you can render via ``render_fuse_template``."""
    payload = {
        tid: {"description": meta["description"], "params": meta["params"]}
        for tid, meta in _BUNDLED_TEMPLATES.items()
    }
    return json.dumps({"templates": payload, "count": len(payload)}, indent=2)


def _render_template(tid: str, params: dict) -> str:
    if tid not in _BUNDLED_TEMPLATES:
        raise ValueError(f"Unknown template '{tid}'. Allowed: {sorted(_BUNDLED_TEMPLATES.keys())}.")
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
def cutmaster_render_fuse_template(
    template_id: str,
    params: dict,
    output_path: str = "",
) -> str:
    """Render a bundled Fuse scaffold with ``params`` substituted in.

    Args:
        template_id: One of ``pass_through`` / ``single_input_image_op`` /
            ``dual_input_blend`` / ``time_modulator``. List the full
            param set via ``cutmaster_list_fuse_templates``.
        params: Dict of ``{{TOKEN}}`` substitutions. ``NAME`` / ``CLASS_ID`` /
            ``CATEGORY`` / ``DESCRIPTION`` are required on every template;
            some templates require extras.
        output_path: Optional absolute path to write to. Empty = return
            source only. Tip: pair with ``cutmaster_install_fuse`` when
            you've vetted the rendered source.
    """
    source = _render_template(template_id, params)
    valid, issues = _validate_lua(source)
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


@mcp.tool
@safe_resolve_call
def cutmaster_refresh_fuses() -> str:
    """Re-list user-level Fuses — useful after an install/remove.

    Resolve hot-loads Fuses when a comp is reopened; this tool doesn't
    *trigger* the reload, it just confirms the on-disk state.
    """
    return json.dumps({"user": _list_dir(_user_fuse_dir())}, indent=2)
