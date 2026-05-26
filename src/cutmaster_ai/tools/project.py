"""Project management tools — CRUD, settings, databases, folders."""

import json

from ..config import mcp
from ..errors import safe_resolve_call
from ..resolve import _boilerplate, _ser, get_resolve

# ---------------------------------------------------------------------------
# Version / status
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_get_version() -> str:
    """Get DaVinci Resolve product name, version, and current page."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    return json.dumps(
        {
            "product": resolve.GetProductName(),
            "version": resolve.GetVersionString(),
            "page": resolve.GetCurrentPage(),
        },
        indent=2,
    )


@mcp.tool
@safe_resolve_call
def cutmaster_switch_page(page: str) -> str:
    """Switch to a Resolve page.

    Valid pages: media, cut, edit, fusion, color, fairlight, deliver
    """
    from ..constants import PAGES

    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    page = page.lower()
    if page not in PAGES:
        return f"Error: Invalid page '{page}'. Valid: {', '.join(sorted(PAGES))}"
    result = resolve.OpenPage(page)
    return f"Switched to {page} page." if result else f"Failed to switch to {page} page."


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_list_projects() -> str:
    """List all projects in the current database folder."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    if not pm:
        return "Error: Could not access the Project Manager."
    projects = pm.GetProjectListInCurrentFolder() or []
    if not projects:
        return "No projects found in the current folder."
    return "Projects:\n" + "\n".join(f"  - {p}" for p in projects)


@mcp.tool
@safe_resolve_call
def cutmaster_get_current_project() -> str:
    """Get the name and details of the currently open project."""
    _, project, _ = _boilerplate()
    tl_count = project.GetTimelineCount() or 0
    current_tl = None
    try:
        tl = project.GetCurrentTimeline()
        current_tl = tl.GetName() if tl else None
    except (AttributeError, TypeError):
        pass
    return json.dumps(
        {
            "name": project.GetName(),
            "unique_id": project.GetUniqueId(),
            "timeline_count": tl_count,
            "current_timeline": current_tl,
        },
        indent=2,
    )


@mcp.tool
@safe_resolve_call
def cutmaster_create_project(name: str) -> str:
    """Create a new project with the given name."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    if not pm:
        return "Error: Could not access the Project Manager."
    project = pm.CreateProject(name)
    if project:
        return f"Project '{name}' created and opened."
    return f"Failed to create project '{name}'. A project with that name may already exist."


@mcp.tool
@safe_resolve_call
def cutmaster_open_project(name: str) -> str:
    """Open an existing project by name."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    if not pm:
        return "Error: Could not access the Project Manager."
    projects = pm.GetProjectListInCurrentFolder() or []
    if name not in projects:
        return (
            f"Error: Project '{name}' not found. "
            f"Available: {', '.join(projects) if projects else 'none'}"
        )
    result = pm.LoadProject(name)
    return f"Project '{name}' opened." if result else f"Failed to open project '{name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_save_project() -> str:
    """Save the current project."""
    _, project, _ = _boilerplate()
    name = project.GetName()
    result = project.SaveProject()  # type: ignore[attr-defined]
    # SaveProject is on ProjectManager in some API versions
    if not result:
        resolve = get_resolve()
        pm = resolve.GetProjectManager()  # type: ignore[union-attr]
        result = pm.SaveProject()
    return f"Project '{name}' saved." if result else f"Failed to save project '{name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_close_project() -> str:
    """Close the current project (returns to Project Manager)."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project:
        return "No project is open."
    name = project.GetName()
    result = pm.CloseProject(project)
    return f"Project '{name}' closed." if result else f"Failed to close project '{name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_delete_project(name: str) -> str:
    """Delete a project by name. The project must not be currently open."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.DeleteProject(name)
    return f"Project '{name}' deleted." if result else f"Failed to delete project '{name}'."


# ---------------------------------------------------------------------------
# Project import / export / archive
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_export_project(name: str, path: str, with_stills: bool = True) -> str:
    """Export a project to a .drp file.

    Args:
        name: Project name to export.
        path: Destination file path (should end with .drp).
        with_stills: Include gallery stills in the export.
    """
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.ExportProject(name, path, with_stills)
    return f"Project '{name}' exported to {path}." if result else f"Failed to export '{name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_import_project(path: str, name: str = "") -> str:
    """Import a project from a .drp file.

    Args:
        path: Path to the .drp file.
        name: Optional name for the imported project (uses file name if empty).
    """
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    if name:
        result = pm.ImportProject(path, name)
    else:
        result = pm.ImportProject(path)
    return f"Project imported from {path}." if result else f"Failed to import from {path}."


@mcp.tool
@safe_resolve_call
def cutmaster_archive_project(
    name: str,
    path: str,
    archive_src_media: bool = True,
    archive_render_cache: bool = False,
    archive_proxy_media: bool = False,
) -> str:
    """Archive a project to a .dra file with optional media.

    Args:
        name: Project name to archive.
        path: Destination archive path.
        archive_src_media: Include source media files.
        archive_render_cache: Include render cache.
        archive_proxy_media: Include proxy media.
    """
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.ArchiveProject(
        name, path, archive_src_media, archive_render_cache, archive_proxy_media
    )
    return f"Project '{name}' archived to {path}." if result else f"Failed to archive '{name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_restore_project(path: str, name: str = "") -> str:
    """Restore a project from a .dra archive.

    Args:
        path: Path to the .dra archive file.
        name: Optional name for the restored project.
    """
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    if name:
        result = pm.RestoreProject(path, name)
    else:
        result = pm.RestoreProject(path)
    return f"Project restored from {path}." if result else f"Failed to restore from {path}."


# ---------------------------------------------------------------------------
# Project folders (in Project Manager)
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_list_project_folders() -> str:
    """List folders in the current Project Manager location."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    folders = pm.GetFolderListInCurrentFolder() or []
    if not folders:
        return "No folders in the current location."
    return "Folders:\n" + "\n".join(f"  - {f}" for f in folders)


@mcp.tool
@safe_resolve_call
def cutmaster_open_project_folder(name: str) -> str:
    """Navigate into a Project Manager folder."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.OpenFolder(name)
    return f"Opened folder '{name}'." if result else f"Failed to open folder '{name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_goto_root_folder() -> str:
    """Navigate to the root of the Project Manager."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.GotoRootFolder()
    return "Navigated to root folder." if result else "Failed to navigate to root folder."


@mcp.tool
@safe_resolve_call
def cutmaster_goto_parent_folder() -> str:
    """Navigate up one level in the Project Manager."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.GotoParentFolder()
    return "Navigated to parent folder." if result else "Already at root folder."


@mcp.tool
@safe_resolve_call
def cutmaster_create_project_folder(name: str) -> str:
    """Create a new folder in the current Project Manager location."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.CreateFolder(name)
    return f"Folder '{name}' created." if result else f"Failed to create folder '{name}'."


@mcp.tool
@safe_resolve_call
def cutmaster_delete_project_folder(name: str) -> str:
    """Delete a folder in the Project Manager. Must be empty."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.DeleteFolder(name)
    return f"Folder '{name}' deleted." if result else f"Failed to delete folder '{name}'."


# ---------------------------------------------------------------------------
# Database management
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_get_current_database() -> str:
    """Get the currently active database."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    db = pm.GetCurrentDatabase()
    return json.dumps(_ser(db), indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_list_databases() -> str:
    """List all available databases."""
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    dbs = pm.GetDatabaseList() or []
    return json.dumps([_ser(d) for d in dbs], indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_switch_database(db_name: str, db_type: str = "Disk") -> str:
    """Switch to a different database.

    Args:
        db_name: Name of the database.
        db_type: Database type — 'Disk', 'PostgreSQL', or 'Cloud'.
    """
    resolve = get_resolve()
    if not resolve:
        return "Error: DaVinci Resolve is not running."
    pm = resolve.GetProjectManager()
    result = pm.SetCurrentDatabase({"DbType": db_type, "DbName": db_name})
    return f"Switched to database '{db_name}'." if result else f"Failed to switch to '{db_name}'."


# ---------------------------------------------------------------------------
# Project settings
# ---------------------------------------------------------------------------


@mcp.tool
@safe_resolve_call
def cutmaster_get_project_setting(key: str = "") -> str:
    """Get a project setting by key, or all settings if key is empty.

    Common keys: timelineResolutionWidth, timelineResolutionHeight,
    timelineFrameRate, colorScienceMode, audioCaptureNumChannels
    """
    _, project, _ = _boilerplate()
    if key:
        value = project.GetSetting(key)
        return json.dumps({key: value}, indent=2)
    # Get all settings — pass empty string
    settings = project.GetSetting("")
    return json.dumps(_ser(settings), indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_set_project_setting(key: str, value: str) -> str:
    """Set a project setting.

    Args:
        key: Setting key (e.g. 'timelineResolutionWidth').
        value: Setting value as string.
    """
    _, project, _ = _boilerplate()
    result = project.SetSetting(key, value)
    return f"Set {key} = {value}." if result else f"Failed to set {key}. Check key name and value."


# ---------------------------------------------------------------------------
# v5 · Project-level setup helpers (enum-normalising wrappers over SetSetting)
# ---------------------------------------------------------------------------
#
# Every wrapper below is a thin call to ``project.SetSetting(key, value)`` with
# (a) an LLM-friendly enum normalised to Resolve's exact string, and (b) the
# Resolve setting keys grouped by intent so an agent doesn't need to know the
# raw key names. Verified live on Resolve 21.0.0b.20 (see api_verification.md).

_COLOR_SCIENCE_MODES = {
    "davinciYRGB": "davinciYRGB",
    "yrgb": "davinciYRGB",
    "davinciYRGBColorManaged": "davinciYRGBColorManaged",
    "managed": "davinciYRGBColorManaged",
    "acescct": "acescct",
    "acescc": "acescc",
}

_PROXY_MODES = {
    "off": "0",
    "0": "0",
    "prefer_camera_originals": "1",
    "1": "1",
    "prefer_proxies": "2",
    "2": "2",
}


def _normalise_enum(value: str, table: dict[str, str], field: str) -> str:
    """Look up ``value`` (case-insensitive) in ``table``; raise on miss."""
    key = (value or "").strip().lower()
    for k, v in table.items():
        if k.lower() == key:
            return v
    raise ValueError(f"Invalid {field} '{value}'. Allowed: {sorted(set(table.values()))}.")


@mcp.tool
@safe_resolve_call
def cutmaster_set_color_science_mode(mode: str) -> str:
    """Set the project's color science mode.

    Args:
        mode: One of ``davinciYRGB`` / ``davinciYRGBColorManaged`` / ``acescct``
            / ``acescc``. Aliases ``yrgb`` (→ ``davinciYRGB``) and ``managed``
            (→ ``davinciYRGBColorManaged``) accepted for convenience.

    Some color-science changes only take effect after the project reloads.
    """
    _, project, _ = _boilerplate()
    canonical = _normalise_enum(mode, _COLOR_SCIENCE_MODES, "color science mode")
    if not project.SetSetting("colorScienceMode", canonical):
        return f"Failed to set colorScienceMode = {canonical}. Resolve refused the value."
    return f"Set colorScienceMode = {canonical}."


@mcp.tool
@safe_resolve_call
def cutmaster_set_color_space(
    input_space: str = "",
    timeline_space: str = "",
    output_space: str = "",
    input_gamma: str = "",
    timeline_gamma: str = "",
    output_gamma: str = "",
) -> str:
    """Set per-project input / timeline / output color spaces (and gammas).

    Each argument is optional — pass only the ones you want to change. Values
    are the exact Resolve labels (e.g. ``Rec.709 (Scene)``, ``Rec.2020``,
    ``DaVinci Wide Gamut``, ``ACES AP1``). Gamma examples: ``Rec.709``,
    ``Gamma 2.4``, ``Linear``.
    """
    _, project, _ = _boilerplate()
    pairs = [
        ("colorSpaceInput", input_space),
        ("colorSpaceTimeline", timeline_space),
        ("colorSpaceOutput", output_space),
        ("colorSpaceInputGamma", input_gamma),
        ("colorSpaceTimelineGamma", timeline_gamma),
        ("colorSpaceOutputGamma", output_gamma),
    ]
    applied: list[str] = []
    failed: list[str] = []
    for key, val in pairs:
        if not val:
            continue
        if project.SetSetting(key, val):
            applied.append(f"{key}={val}")
        else:
            failed.append(f"{key}={val}")
    if not applied and not failed:
        return "No color-space fields passed — nothing changed."
    return json.dumps({"applied": applied, "failed": failed}, indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_set_timeline_format(
    width: int,
    height: int,
    fps: float,
    pixel_aspect: str = "square",
) -> str:
    """Set the project-level timeline format defaults.

    Args:
        width: Pixels (e.g. 1920, 1080, 3840).
        height: Pixels (e.g. 1080, 1920, 2160).
        fps: Frame rate (e.g. 24, 25, 29.97, 30, 60).
        pixel_aspect: One of ``square``, ``16:9_anamorphic``, ``4:3_anamorphic``,
            ``cinemascope``. Defaults to ``square``.

    Affects future timeline creates. Existing timelines that explicitly set
    "Use Project Settings = Off" retain their own resolution.
    """
    _, project, _ = _boilerplate()
    pa_map = {
        "square": "Square",
        "16:9_anamorphic": "16:9 Anamorphic",
        "4:3_anamorphic": "4:3 Anamorphic",
        "cinemascope": "Cinemascope",
    }
    pa = pa_map.get(pixel_aspect.lower())
    if pa is None:
        raise ValueError(f"Invalid pixel_aspect '{pixel_aspect}'. Allowed: {sorted(pa_map)}.")
    results = {
        "timelineResolutionWidth": project.SetSetting("timelineResolutionWidth", str(width)),
        "timelineResolutionHeight": project.SetSetting("timelineResolutionHeight", str(height)),
        "timelineFrameRate": project.SetSetting("timelineFrameRate", str(fps)),
        "timelinePixelAspectRatio": project.SetSetting("timelinePixelAspectRatio", pa),
    }
    return json.dumps(results, indent=2)


@mcp.tool
@safe_resolve_call
def cutmaster_set_proxy_mode(mode: str) -> str:
    """Toggle the project's proxy-media playback mode.

    Args:
        mode: One of ``off``, ``prefer_camera_originals``, ``prefer_proxies``.
            Aliases ``0`` / ``1`` / ``2`` accepted for compatibility with raw
            Resolve setting values.
    """
    _, project, _ = _boilerplate()
    canonical = _normalise_enum(mode, _PROXY_MODES, "proxy mode")
    if not project.SetSetting("perfProxyMediaMode", canonical):
        return f"Failed to set perfProxyMediaMode = {canonical}."
    return f"Set perfProxyMediaMode = {canonical}."


@mcp.tool
@safe_resolve_call
def cutmaster_set_optimized_media_mode(enabled: bool) -> str:
    """Enable or disable optimized-media playback for the project.

    When enabled, Resolve plays back from optimized media when available and
    falls back to source otherwise. Optimized media is generated separately
    via the Media page; this setter only flips the playback-preference.
    """
    _, project, _ = _boilerplate()
    value = "1" if enabled else "0"
    if not project.SetSetting("perfOptimizedMediaMode", value):
        return f"Failed to set perfOptimizedMediaMode = {value}."
    return f"Set perfOptimizedMediaMode = {value} ({'enabled' if enabled else 'disabled'})."


@mcp.tool
@safe_resolve_call
def cutmaster_set_cache_mode(mode: str) -> str:
    """Set the project's render-cache mode.

    Args:
        mode: One of ``none``, ``smart``, ``user``. ``smart`` lets Resolve
            decide what to cache; ``user`` caches only explicitly-flagged
            clips/sections; ``none`` disables the render cache.
    """
    _, project, _ = _boilerplate()
    cache_map = {"none": "0", "smart": "1", "user": "2"}
    key = mode.strip().lower()
    if key not in cache_map:
        raise ValueError(f"Invalid cache mode '{mode}'. Allowed: {sorted(cache_map)}.")
    if not project.SetSetting("videoCacheMode", cache_map[key]):
        return f"Failed to set videoCacheMode = {cache_map[key]}."
    return f"Set videoCacheMode = {cache_map[key]} ({key})."


@mcp.tool
@safe_resolve_call
def cutmaster_set_superscale_settings(scale: int) -> str:
    """Set the project's default SuperScale upscaling factor.

    Args:
        scale: ``1`` (off, native) / ``2`` (2x) / ``3`` (3x) / ``4`` (4x).
            Applied to clips whose SuperScale property is set in the
            inspector; this setter only changes the project default.
    """
    _, project, _ = _boilerplate()
    if scale not in (1, 2, 3, 4):
        raise ValueError(f"Invalid superScale '{scale}'. Allowed: 1, 2, 3, 4.")
    if not project.SetSetting("superScale", str(scale)):
        return f"Failed to set superScale = {scale}."
    return f"Set superScale = {scale}."
