"""Exception hierarchy and @safe_resolve_call decorator.

All Resolve tool functions should be decorated with @safe_resolve_call so that
Python exceptions are converted into MCP-friendly error strings.  The LLM
receives actionable feedback instead of a traceback.
"""

import functools
import logging

log = logging.getLogger("cutmaster-ai")


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class ResolveError(Exception):
    """Base error for Resolve API failures."""


class ResolveNotRunning(ResolveError):
    """Resolve is not running or the scripting API is unreachable."""


class ProjectNotOpen(ResolveError):
    """No project is currently open in Resolve."""


class TimelineNotFound(ResolveError):
    """The requested timeline does not exist or no timeline is active."""


class BinNotFound(ResolveError):
    """The requested media pool bin does not exist."""


class ClipNotFound(ResolveError):
    """The requested clip does not exist in the media pool."""


class ItemNotFound(ResolveError):
    """The timeline item at the given track/index does not exist."""


class StudioRequired(ResolveError):
    """The feature requires DaVinci Resolve Studio."""


class ResolveVersionTooOld(ResolveError):
    """The required Resolve scripting method is missing on this Resolve build."""


class RenderError(ResolveError):
    """A render operation failed."""


# ---------------------------------------------------------------------------
# Version + edition gates
# ---------------------------------------------------------------------------


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted version string like ``"20.2.2"`` into a tuple.

    Non-numeric trailing fragments (e.g. build suffixes) are dropped.
    """
    parts: list[int] = []
    for chunk in version.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def _requires_method(obj, method_name: str, min_version: str) -> None:
    """Raise ``ResolveVersionTooOld`` if ``obj`` lacks ``method_name``.

    Mirrors the version-gate pattern from
    `samuelgursky/davinci-resolve-mcp/src/granular/common.py`. The accepted
    shape is a dotted string (``"20.2.2"``) — matches samuel so docstrings
    copy-paste cleanly — and the comparison is done as an integer tuple
    internally for monotonic ordering.

    The check is purely existential (``hasattr``); we don't introspect the
    actual Resolve version because Resolve's scripting API doesn't expose
    one reliably. The ``min_version`` argument is documentation that gets
    surfaced to the caller when the method is absent.
    """
    if hasattr(obj, method_name) and callable(getattr(obj, method_name)):
        return
    _ = _parse_version(min_version)  # validate format eagerly
    raise ResolveVersionTooOld(
        f"{method_name}() is missing on this Resolve build — requires Resolve ≥{min_version}."
    )


# Studio-edition gate lives in ``resolve._require_studio(feature_name)`` —
# Wave 2 wrappers import it from there. No second helper here.


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def safe_resolve_call(func):
    """Catch exceptions from Resolve API and return error strings.

    Converts Python exceptions into MCP-friendly error strings so the LLM
    gets actionable feedback instead of a traceback.

    ``ValueError`` raised by ``_boilerplate()`` is passed through as-is
    because it already contains a clean, human-readable message.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            # From _boilerplate() — already a clean error message
            return str(exc)
        except ResolveError as exc:
            return f"Error: {exc}"
        except (AttributeError, TypeError) as exc:
            log.warning("Resolve API error in %s: %s", func.__name__, exc)
            return (
                f"Error: Resolve API returned an unexpected result in "
                f"{func.__name__}. This may indicate an API version mismatch "
                f"or that the required object is not available. Detail: {exc}"
            )
        except Exception as exc:
            log.exception("Unexpected error in %s", func.__name__)
            return f"Error: Unexpected failure in {func.__name__}: {exc}"

    return wrapper
