"""Unit tests for v5 Wave 2 — C5 Magic Mask, C6 reframe/stabilize, C8 captions/scene cuts, C9 transcription.

Integration tests against live Resolve Studio are deferred to Phase 4. These
tests cover enum normalisation, input validation, and module registration —
the deterministic surface we can verify without Resolve.
"""

from __future__ import annotations

import pytest

from cutmaster_ai.tools import clip_ai, native_transcription, timeline_native_ai

# ---------------------------------------------------------------------------
# C5 · Magic Mask mode enum
# ---------------------------------------------------------------------------


class TestMagicMaskMode:
    def test_forward_canonical(self):
        assert clip_ai._normalise_mask_mode("F") == "F"

    def test_forward_alias(self):
        assert clip_ai._normalise_mask_mode("forward") == "F"

    def test_backward_alias(self):
        assert clip_ai._normalise_mask_mode("backward") == "B"

    def test_bidirectional_alias(self):
        assert clip_ai._normalise_mask_mode("BI") == "BI"
        assert clip_ai._normalise_mask_mode("bidirectional") == "BI"

    def test_case_insensitive(self):
        assert clip_ai._normalise_mask_mode("FORWARD") == "F"

    def test_invalid_raises(self):
        with pytest.raises(ValueError) as exc:
            clip_ai._normalise_mask_mode("sideways")
        assert "sideways" in str(exc.value) or "Allowed" in str(exc.value)


# ---------------------------------------------------------------------------
# C6 · module registration (no per-call enum to test — methods take 0 args)
# ---------------------------------------------------------------------------


class TestClipAITools:
    def test_create_magic_mask_exists(self):
        assert callable(clip_ai.cutmaster_create_magic_mask)

    def test_regenerate_magic_mask_exists(self):
        assert callable(clip_ai.cutmaster_regenerate_magic_mask)

    def test_smart_reframe_exists(self):
        assert callable(clip_ai.cutmaster_smart_reframe)

    def test_stabilize_exists(self):
        assert callable(clip_ai.cutmaster_stabilize)


# ---------------------------------------------------------------------------
# C8 · caption enum validation
# ---------------------------------------------------------------------------


class TestCaptionEnums:
    def test_language_table_complete(self):
        # 17 supported languages in README
        assert len(timeline_native_ai._LANGUAGES) >= 16
        assert "english" in timeline_native_ai._LANGUAGES
        assert "auto" in timeline_native_ai._LANGUAGES

    def test_preset_table(self):
        assert "default" in timeline_native_ai._PRESETS
        assert "netflix" in timeline_native_ai._PRESETS
        assert "teletext" in timeline_native_ai._PRESETS

    def test_line_break_table(self):
        assert timeline_native_ai._LINE_BREAKS == {
            "single": "AUTO_CAPTION_LINE_SINGLE",
            "double": "AUTO_CAPTION_LINE_DOUBLE",
        }


class TestCaptionsValidation:
    """Validation runs before any Resolve call — ValueErrors should round-trip via @safe_resolve_call."""

    def test_invalid_language_returns_string(self):
        out = timeline_native_ai.cutmaster_create_subtitles_from_audio(language="klingon")
        assert isinstance(out, str)
        assert "klingon" in out or "Invalid language" in out

    def test_invalid_preset_returns_string(self):
        out = timeline_native_ai.cutmaster_create_subtitles_from_audio(caption_preset="rubbish")
        assert isinstance(out, str)
        assert "rubbish" in out or "caption_preset" in out

    def test_chars_per_line_out_of_range(self):
        out = timeline_native_ai.cutmaster_create_subtitles_from_audio(chars_per_line=999)
        assert isinstance(out, str)
        assert "chars_per_line" in out

    def test_gap_out_of_range(self):
        out = timeline_native_ai.cutmaster_create_subtitles_from_audio(gap_frames=99)
        assert isinstance(out, str)
        assert "gap_frames" in out


# ---------------------------------------------------------------------------
# C9 · transcription input validation + module shape
# ---------------------------------------------------------------------------


class TestTranscriptionTools:
    def test_transcribe_clip_requires_name(self):
        out = native_transcription.cutmaster_transcribe_clip("")
        assert isinstance(out, str)
        assert "clip_name" in out

    def test_clear_clip_requires_name(self):
        out = native_transcription.cutmaster_clear_clip_transcription("   ")
        assert isinstance(out, str)
        assert "clip_name" in out

    def test_transcribe_folder_allows_empty_name(self):
        # Folder transcribe with empty folder_name targets the root.
        # We can't assert success without Resolve, but we can assert the
        # tool exists and returns a string.
        assert callable(native_transcription.cutmaster_transcribe_folder)
