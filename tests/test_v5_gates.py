"""Tests for the v5 version + Studio gate helpers in errors.py."""

import pytest

from cutmaster_ai.errors import (
    ResolveVersionTooOld,
    _parse_version,
    _requires_method,
)


class TestParseVersion:
    def test_simple(self):
        assert _parse_version("20.2.2") == (20, 2, 2)

    def test_two_segments(self):
        assert _parse_version("19.1") == (19, 1)

    def test_with_build_suffix_dropped(self):
        assert _parse_version("20.0.0-beta") == (20, 0, 0)

    def test_empty_returns_zero_tuple(self):
        assert _parse_version("") == (0,)


class _FakeObj:
    def known(self):
        return True


class TestRequiresMethod:
    def test_present_method_passes(self):
        _requires_method(_FakeObj(), "known", "20.2.2")  # no raise

    def test_missing_method_raises(self):
        with pytest.raises(ResolveVersionTooOld) as exc:
            _requires_method(_FakeObj(), "missing", "20.2.2")
        msg = str(exc.value)
        assert "missing()" in msg
        assert "≥20.2.2" in msg

    def test_non_callable_attribute_raises(self):
        class Holder:
            attr = "not callable"

        with pytest.raises(ResolveVersionTooOld):
            _requires_method(Holder(), "attr", "20.2.2")
