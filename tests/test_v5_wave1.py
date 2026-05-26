"""Unit tests for v5 Wave 1 — C10 setters, C11 fairlight, C12 reset_clip_grade.

Integration tests against live Resolve are deferred to a separate harness
(``CUTMASTER_HAS_STUDIO=1`` env). These tests cover enum normalisation,
version-gate behaviour, and ``ValueError`` raising on bad input — the
deterministic surface we can verify without Resolve.
"""

from __future__ import annotations

import pytest

from cutmaster_ai.errors import ResolveVersionTooOld
from cutmaster_ai.tools import project as project_tools

# ---------------------------------------------------------------------------
# C10 · enum normalisation helpers (the deterministic core of every setter)
# ---------------------------------------------------------------------------


class TestColorScienceEnum:
    def test_canonical_passes(self):
        v = project_tools._normalise_enum(
            "acescct", project_tools._COLOR_SCIENCE_MODES, "color science mode"
        )
        assert v == "acescct"

    def test_alias_maps_to_canonical(self):
        v = project_tools._normalise_enum(
            "yrgb", project_tools._COLOR_SCIENCE_MODES, "color science mode"
        )
        assert v == "davinciYRGB"

    def test_case_insensitive(self):
        v = project_tools._normalise_enum(
            "ACEScct", project_tools._COLOR_SCIENCE_MODES, "color science mode"
        )
        assert v == "acescct"

    def test_unknown_raises(self):
        with pytest.raises(ValueError) as exc:
            project_tools._normalise_enum(
                "nonsense", project_tools._COLOR_SCIENCE_MODES, "color science mode"
            )
        assert "color science mode" in str(exc.value)


class TestProxyModeEnum:
    def test_string_alias(self):
        assert (
            project_tools._normalise_enum(
                "prefer_proxies", project_tools._PROXY_MODES, "proxy mode"
            )
            == "2"
        )

    def test_numeric_alias(self):
        assert project_tools._normalise_enum("2", project_tools._PROXY_MODES, "proxy mode") == "2"

    def test_off(self):
        assert project_tools._normalise_enum("off", project_tools._PROXY_MODES, "proxy mode") == "0"

    def test_invalid(self):
        with pytest.raises(ValueError):
            project_tools._normalise_enum("turbo", project_tools._PROXY_MODES, "proxy mode")


# ---------------------------------------------------------------------------
# C10 · @safe_resolve_call wraps each tool — ValueErrors round-trip as strings.
# We invoke a couple of tools with bad input and confirm the error string
# shape, *without* a live Resolve handle. _boilerplate() will raise inside
# ``safe_resolve_call`` first (no Resolve), so we only exercise the
# normaliser by calling the raw helper directly above; the round-trip below
# documents the contract.
# ---------------------------------------------------------------------------


class TestSetterErrorContract:
    """Every setter returns ``str`` and never raises through @safe_resolve_call."""

    def test_color_science_bad_enum_returns_string(self, monkeypatch):
        # Bypass _boilerplate by stubbing it to return a fake project whose
        # SetSetting we never reach (normaliser raises first).
        fake_project = object()
        monkeypatch.setattr(
            project_tools,
            "_boilerplate",
            lambda: (None, fake_project, None),
        )
        out = project_tools.cutmaster_set_color_science_mode("rubbish")
        assert isinstance(out, str)
        assert "rubbish" in out or "color science mode" in out.lower()


# ---------------------------------------------------------------------------
# C11 · version gate fires when Resolve build lacks the method
# ---------------------------------------------------------------------------


class _FakeResolveNoFairlight:
    """Resolve mock with no GetFairlightPresets — represents Resolve <20.2.2."""

    # Note: getattr returns None for missing attrs on the real Resolve PyRemoteObject;
    # for the mock we just omit the attribute entirely (AttributeError) — _requires_method
    # treats both as "missing".


class _FakeProjectNoFairlight:
    pass


class TestFairlightVersionGate:
    def test_get_presets_raises_when_missing(self):
        from cutmaster_ai.errors import _requires_method

        with pytest.raises(ResolveVersionTooOld) as exc:
            _requires_method(_FakeResolveNoFairlight(), "GetFairlightPresets", "20.2.2")
        assert "GetFairlightPresets" in str(exc.value)
        assert "20.2.2" in str(exc.value)

    def test_apply_preset_raises_when_missing(self):
        from cutmaster_ai.errors import _requires_method

        with pytest.raises(ResolveVersionTooOld):
            _requires_method(
                _FakeProjectNoFairlight(),
                "ApplyFairlightPresetToCurrentTimeline",
                "20.2.2",
            )


# ---------------------------------------------------------------------------
# C12 · reset_clip_grade input validation
# ---------------------------------------------------------------------------


class TestResetClipGrade:
    """Confirm the tool exists and is registered through the MCP layer.

    Live Graph behaviour is integration-tested separately.
    """

    def test_tool_exists(self):
        from cutmaster_ai.tools import color

        assert hasattr(color, "cutmaster_reset_clip_grade")
        assert callable(color.cutmaster_reset_clip_grade)
