"""Unit tests for v5 Wave 3 — C4 fusion intel, C2 Fuse, C3 DCTL, C7 multicam.

Most of Wave 3 is file-IO + validators, which we can test fully without a
live Resolve. Tools that need Resolve are smoke-tested for existence only.
"""

from __future__ import annotations

import json

import pytest

from cutmaster_ai.tools import dctl, fuse_plugins, fusion_inspect
from cutmaster_ai.workflows import multicam

# ---------------------------------------------------------------------------
# C4 · Fusion inspector — module shape + cursor encoding
# ---------------------------------------------------------------------------


class TestFusionInspectorShape:
    def test_all_tools_exist(self):
        for name in (
            "cutmaster_fusion_boundary_report",
            "cutmaster_fusion_probe_comp",
            "cutmaster_fusion_list_animated_inputs",
            "cutmaster_fusion_check_render_safe",
        ):
            assert callable(getattr(fusion_inspect, name))

    def test_cursor_roundtrip(self):
        cur = fusion_inspect._encode_cursor(42)
        assert fusion_inspect._decode_cursor(cur) == 42

    def test_cursor_empty_returns_zero(self):
        assert fusion_inspect._decode_cursor(None) == 0
        assert fusion_inspect._decode_cursor("") == 0

    def test_cursor_invalid_raises(self):
        with pytest.raises(ValueError):
            fusion_inspect._decode_cursor("not-a-cursor")


# ---------------------------------------------------------------------------
# C2 · Fuse plugins
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_fuse_dir(monkeypatch, tmp_path):
    """Override the user-level Fuse dir so write tests don't touch ~/Library."""
    fuse_dir = tmp_path / "Fuses"
    fuse_dir.mkdir()
    monkeypatch.setenv("CUTMASTER_FUSE_DIR", str(fuse_dir))
    return fuse_dir


class TestFuseSearchPaths:
    def test_search_paths_returns_json(self):
        out = fuse_plugins.cutmaster_get_fuse_search_paths()
        data = json.loads(out)
        assert "user_dir" in data
        assert "system_dir" in data
        assert "platform" in data


class TestFuseValidator:
    def test_valid_source_passes(self):
        src = (
            'FuRegisterClass("x", CT_Tool, {})\n'
            "function Create() end\n"
            "function Process(req) end\n"
            "{ } { }"
        )  # balanced braces from FuRegisterClass body
        out = json.loads(fuse_plugins.cutmaster_validate_fuse_source(src))
        assert out["valid"] is True
        assert out["issues"] == []

    def test_missing_register_class_fails(self):
        src = "function Create() end\nfunction Process(req) end\n"
        out = json.loads(fuse_plugins.cutmaster_validate_fuse_source(src))
        assert out["valid"] is False
        assert any("FuRegisterClass" in issue for issue in out["issues"])

    def test_banned_calls_caught(self):
        src = (
            'FuRegisterClass("x", CT_Tool, {})\n'
            "function Create() end\n"
            "function Process(req) os.execute('rm -rf /') end\n"
            "{ }"
        )
        out = json.loads(fuse_plugins.cutmaster_validate_fuse_source(src))
        assert out["valid"] is False
        assert any("os.execute" in issue for issue in out["issues"])


class TestFuseTemplates:
    def test_list_templates_returns_4(self):
        out = json.loads(fuse_plugins.cutmaster_list_fuse_templates())
        assert out["count"] == 4
        assert "pass_through" in out["templates"]
        assert "single_input_image_op" in out["templates"]
        assert "dual_input_blend" in out["templates"]
        assert "time_modulator" in out["templates"]

    def test_render_pass_through(self):
        result = json.loads(
            fuse_plugins.cutmaster_render_fuse_template(
                "pass_through",
                {
                    "NAME": "MyFuse",
                    "CLASS_ID": "Fuse.MyFuse",
                    "CATEGORY": "Custom",
                    "DESCRIPTION": "A test fuse",
                },
            )
        )
        assert "MyFuse" in result["source"]
        assert "{{NAME}}" not in result["source"]
        assert "FuRegisterClass" in result["source"]
        assert result["written"] is False

    def test_render_missing_params(self):
        # raise → @safe_resolve_call → ValueError → string return
        out = fuse_plugins.cutmaster_render_fuse_template("pass_through", {"NAME": "x"})
        assert isinstance(out, str)
        assert "Missing params" in out

    def test_render_unknown_template(self):
        out = fuse_plugins.cutmaster_render_fuse_template("nope", {})
        assert isinstance(out, str)
        assert "Unknown template" in out


class TestFuseInstallRemove:
    def test_install_round_trip(self, tmp_fuse_dir, tmp_path):
        # Write a tiny .fuse to a temp src then install it
        src = tmp_path / "foo.fuse"
        src.write_text("FuRegisterClass('Foo', CT_Tool, {})\n")
        installed_out = json.loads(fuse_plugins.cutmaster_install_fuse(str(src), name="MyFoo"))
        assert installed_out["installed"] is True
        # List should show it
        listing = json.loads(fuse_plugins.cutmaster_list_fuses())
        names = [e["name"] for e in listing["user"]]
        assert "MyFoo.fuse" in names
        # Read it back
        read = fuse_plugins.cutmaster_read_fuse("MyFoo")
        assert "FuRegisterClass" in read
        # Remove
        removed = json.loads(fuse_plugins.cutmaster_remove_fuse("MyFoo"))
        assert removed["removed"] is True

    def test_install_rejects_non_fuse(self, tmp_fuse_dir, tmp_path):
        bad = tmp_path / "foo.txt"
        bad.write_text("not a fuse")
        out = fuse_plugins.cutmaster_install_fuse(str(bad))
        assert "not a .fuse" in out

    def test_install_rejects_traversal(self, tmp_fuse_dir, tmp_path):
        src = tmp_path / "foo.fuse"
        src.write_text("FuRegisterClass('x', CT_Tool, {})")
        out = fuse_plugins.cutmaster_install_fuse(str(src), name="../escape")
        assert isinstance(out, str)
        assert "Invalid" in out or "escape" in out


# ---------------------------------------------------------------------------
# C3 · DCTL
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dctl_dir(monkeypatch, tmp_path):
    dctl_dir = tmp_path / "LUT"
    dctl_dir.mkdir()
    monkeypatch.setenv("CUTMASTER_DCTL_DIR", str(dctl_dir))
    return dctl_dir


class TestDCTLValidator:
    def test_valid_source(self):
        src = (
            "__DEVICE__ float3 transform(int p_W, int p_H, int p_X, int p_Y, "
            "float p_R, float p_G, float p_B) { return make_float3(p_R, p_G, p_B); }"
        )
        out = json.loads(dctl.cutmaster_validate_dctl_source(src))
        assert out["valid"] is True

    def test_missing_transform(self):
        src = "__DEVICE__ float foo() { return 1.0f; }"
        out = json.loads(dctl.cutmaster_validate_dctl_source(src))
        assert out["valid"] is False
        assert any("transform" in i for i in out["issues"])

    def test_unbalanced_braces(self):
        src = "__DEVICE__ float3 transform(...) { return make_float3(1,1,1);"
        out = json.loads(dctl.cutmaster_validate_dctl_source(src))
        assert out["valid"] is False
        assert any("brace" in i.lower() for i in out["issues"])

    def test_banned_system_call(self):
        src = (
            "__DEVICE__ float3 transform(int p_W, int p_H, int p_X, int p_Y, "
            "float p_R, float p_G, float p_B) { system('ls'); return make_float3(p_R, p_G, p_B); }"
        )
        out = json.loads(dctl.cutmaster_validate_dctl_source(src))
        assert out["valid"] is False
        assert any("system" in i for i in out["issues"])


class TestDCTLTemplates:
    def test_list_5_templates(self):
        out = json.loads(dctl.cutmaster_list_dctl_templates())
        assert out["count"] == 5
        for tid in (
            "identity",
            "lift_gamma_gain",
            "single_axis_curve",
            "false_color",
            "gamut_clip",
        ):
            assert tid in out["templates"]

    def test_render_lift_gamma_gain(self):
        out = json.loads(dctl.cutmaster_render_dctl_template("lift_gamma_gain"))
        assert "transform" in out["source"]
        assert "DEFINE_UI_PARAMS(lift" in out["source"]
        assert out["valid"] is True

    def test_render_identity_with_ui_params(self):
        out = json.loads(
            dctl.cutmaster_render_dctl_template(
                "identity",
                {"UI_PARAMS": "amount, Amount, DCTLUI_SLIDER_FLOAT, 0.5, 0.0, 1.0, 0.001"},
            )
        )
        assert "{{UI_PARAMS}}" not in out["source"]
        assert "amount" in out["source"]


class TestDCTLInstallRemove:
    def test_install_round_trip(self, tmp_dctl_dir, tmp_path):
        src = tmp_path / "MyLUT.dctl"
        src.write_text(
            "__DEVICE__ float3 transform(int p_W, int p_H, int p_X, int p_Y, "
            "float p_R, float p_G, float p_B) { return make_float3(p_R, p_G, p_B); }"
        )
        installed = json.loads(dctl.cutmaster_install_dctl(str(src), subfolder="Custom"))
        assert installed["installed"] is True
        listing = json.loads(dctl.cutmaster_list_dctls())
        names = [e["name"] for e in listing["user"]]
        assert "MyLUT.dctl" in names
        removed = json.loads(dctl.cutmaster_remove_dctl("MyLUT", subfolder="Custom"))
        assert removed["removed"] is True

    def test_install_traversal_blocked(self, tmp_dctl_dir, tmp_path):
        src = tmp_path / "foo.dctl"
        src.write_text("__DEVICE__ float3 transform() { return make_float3(0,0,0); }")
        out = dctl.cutmaster_install_dctl(str(src), subfolder="../escape")
        assert isinstance(out, str)
        assert "Invalid" in out or "escape" in out or "outside" in out.lower()


# ---------------------------------------------------------------------------
# C7 · multicam input validation
# ---------------------------------------------------------------------------


class TestMulticamValidation:
    def test_too_few_clips_returns_string(self):
        out = multicam.cutmaster_auto_sync_audio(["only_one.mp4"])
        assert isinstance(out, str)
        assert "at least 2" in out

    def test_invalid_sync_mode(self):
        out = multicam.cutmaster_auto_sync_audio(["a.mp4", "b.wav"], sync_mode="cosmic")
        assert isinstance(out, str)
        assert "cosmic" in out or "Invalid sync_mode" in out

    def test_tool_exists(self):
        assert callable(multicam.cutmaster_auto_sync_audio)
