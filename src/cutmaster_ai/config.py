"""FastMCP server instance and shared configuration."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

# Load the repo-root .env regardless of cwd so MCP clients (Claude Code /
# Desktop / Cursor) that spawn the server from a foreign working directory
# still pick up API keys. cwd-based `.env` still wins via the default call.
load_dotenv()
_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"
if _REPO_ENV.is_file():
    load_dotenv(_REPO_ENV, override=False)

log = logging.getLogger("cutmaster-ai")

# ---------------------------------------------------------------------------
# Optional AI client (Gemini) — lazy init to avoid crash on bad key
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
_gemini_client = None


def get_gemini_client():
    """Return a google-genai Client, creating it on first call.

    Returns None when GEMINI_API_KEY is not set.
    """
    global _gemini_client
    if GEMINI_API_KEY is None:
        return None
    if _gemini_client is None:
        from google import genai  # deferred import — package is optional

        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


# ---------------------------------------------------------------------------
# FastMCP server singleton — tools register via @mcp.tool in other modules
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "cutmaster-ai",
    instructions=(
        "MCP server for DaVinci Resolve Studio (v18.5+). Provides ~280 tools "
        "covering the complete Resolve Scripting API plus AI-enhanced tools.\n\n"
        "PREREQUISITES:\n"
        "  - DaVinci Resolve Studio must be running (free edition has no scripting API)\n"
        "  - External scripting must be enabled in Resolve Preferences\n\n"
        "CONVENTIONS:\n"
        "  - All indices are 1-based (timeline, track, node indices)\n"
        "  - Track types: 'video', 'audio', 'subtitle'\n"
        "  - Marker colors: Blue, Cyan, Green, Yellow, Red, Pink, Purple, "
        "Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream\n"
        "  - Clip colors: Orange, Apricot, Yellow, Lime, Olive, Green, Teal, "
        "Navy, Blue, Purple, Violet, Pink, Tan, Beige, Brown, Chocolate\n"
        "  - Pages: media, cut, edit, fusion, color, fairlight, deliver\n"
    ),
)

# ---------------------------------------------------------------------------
# Media constants
# ---------------------------------------------------------------------------
VIDEO_EXTS = frozenset(
    {
        ".mp4",
        ".mov",
        ".mxf",
        ".avi",
        ".webm",
        ".mkv",
        ".r3d",
        ".braw",
        ".ari",
        ".dpx",
        ".exr",
        ".tif",
        ".tiff",
    }
)
AUDIO_EXTS = frozenset(
    {
        ".mp3",
        ".wav",
        ".aac",
        ".flac",
        ".ogg",
        ".m4a",
        ".aif",
        ".aiff",
    }
)
IMAGE_EXTS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".bmp",
        ".dpx",
        ".exr",
    }
)
SAFE_CODECS = frozenset({"h264", "avc", "avc1", "hevc", "h265", "hev1"})
GEMINI_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB ceiling for Files API
