# v5 Port Notes

Engineering notes for the v0.6.0 port — patterns, gotchas, and cookbook
entries that future contributors should know before extending the
Resolve API surface.

## 1. Verification before code

The v5 port enforced a *verify-first* rule (proposal § "Design
principles" #8). Every Resolve method named in the proposal was
confirmed callable on a live Resolve 21.0.0b.20 session **before** a
wrapper was written. This caught 5 invented methods that looked
plausible from secondary sources but did not exist:

- `TimelineItem.ModifyKeyframe`
- `TimelineItem.SetKeyframeInterpolation`
- `TimelineItem.EnableKeyframes`
- `Resolve.GetFairlightAudioMixPresets`
- `Project.ApplyFairlightAudioMixPreset` (correct name omits "Audio Mix")

If you are adding a wrapper:

1. Open Resolve, run `python -m cutmaster_ai`.
2. From a Python REPL with the Resolve scripting env loaded, call
   `getattr(obj, "MethodName", None)` and check it is **callable**, not
   merely truthy. `hasattr()` on Resolve's `PyRemoteObject` returns
   `True` even for phantom methods.
3. Round-trip the call (set → get) when the method has an obvious
   observable.
4. Record the result in
   `Implementation/cutmaster_ai/v5/api_verification.md`.

## 2. Version gating cookbook

Resolve gained several methods in 20.2.2 and 21.0. Wrap them with
`_requires_method` so older builds get a clean
`ResolveVersionTooOld` error instead of the cryptic
`'NoneType' object is not callable`:

```python
from ..errors import _requires_method, ResolveVersionTooOld

@mcp.tool
@safe_resolve_call
def cutmaster_get_fairlight_presets() -> str:
    """List installed Fairlight mix presets (Resolve 20.2.2+)."""
    resolve, _, _ = _boilerplate()
    _requires_method(resolve, "GetFairlightPresets", "20.2.2")
    presets = resolve.GetFairlightPresets() or []
    return json.dumps({"presets": list(presets), "count": len(presets)}, indent=2)
```

`_requires_method` is in `errors.py`. It raises a uniform error string
the existing `safe_resolve_call` decorator turns into a JSON error.

## 3. Studio-edition gating

Use the existing `_require_studio(feature_name)` from `resolve.py` —
**do not add a second one**. Every Wave 2 wrapper calls it because all
of Magic Mask / Smart Reframe / Stabilize / native subtitles / native
transcription / scene-cut detect are Studio-only.

## 4. Destructive ops + snapshots

Any tool that mutates project state irreversibly must:

1. Call `snapshot_project(resolve, project, label="pre_<op>")` *before*
   the mutation, so agents can roll back via existing snapshot tooling.
2. Be added to the destructive-op `.claude/settings.json` hook matcher.

Examples in v0.6.0: `cutmaster_reset_clip_grade`,
`cutmaster_detect_scene_cuts`.

## 5. Path-traversal safety for authoring tools

Both Fuse (`tools/fuse_plugins.py`) and DCTL (`tools/dctl.py`) accept
user-supplied names. Use the `_safe_user_path(name)` pattern:

```python
def _safe_user_path(name: str) -> Path:
    if not name or ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid name '{name}'.")
    user_dir = _user_dir()
    target = (user_dir / name).resolve()
    target.relative_to(user_dir.resolve())  # raises if outside
    return target
```

System-level dirs are **read-only** for us — never write to them.
Override the user dir via env var for tests
(`CUTMASTER_FUSE_DIR`, `CUTMASTER_DCTL_DIR`).

## 6. Source validators

Both authoring surfaces ship a `_validate_*` source-linter that runs:

- on installs (to refuse obviously-broken files)
- on template renders (so the response includes `valid` + `issues`)
- standalone via `cutmaster_validate_*_source`

Checks include:

| Surface | Required tokens | Banned tokens |
|---|---|---|
| `.fuse` | `FuRegisterClass`, `Create()`, `Process()` | `os.execute`, `io.popen`, `loadfile(`, `dofile(` |
| `.dctl` | `__DEVICE__`, `transform(`, `make_float3` | `system(` |

Plus balanced-brace check on both.

## 7. Pagination — opaque base64 cursors

`cutmaster_fusion_probe_comp` and any future deep-tree walker should
use the cursor pattern from `tools/fusion_inspect.py`:

```python
def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()

def _decode_cursor(cursor: str) -> int:
    if not cursor:
        return 0
    return int(base64.urlsafe_b64decode(cursor.encode()).decode())
```

Cursors are opaque to the caller; agents pass them through verbatim.

## 8. Runtime constant lookup

Resolve exposes some enum constants as attributes on the `resolve`
object (e.g. `resolve.AUTO_CAPTION_ENGLISH`). The numeric values are
**not stable** across Resolve versions. Always resolve them at call
time via `_resolve_constant(resolve, suffix, label)`. See
`tools/timeline_native_ai.py` for the canonical implementation.

## 9. Test layers

| Layer | Resolve required? | Where |
|---|---|---|
| L1 unit | no | most v5 tests (`tests/test_v5_*.py`) |
| L2 integration | yes — live Resolve | manual agent scenarios at release |
| L3 record/replay | no — replays a captured Resolve session | future work |

The v5 push covered L1 thoroughly (84 v5-specific tests). L2 was
deferred to Phase 4 agent-scenario smoke tests so that one engineer
with one Resolve session can validate the whole release in a single
pass.

## 10. Module placement (responsibility model)

Per `CLAUDE.md` § Responsibility model:

| Bucket | v5 example |
|---|---|
| Atomic Resolve op | `tools/color.py::cutmaster_reset_clip_grade` |
| Deterministic compound | `workflows/multicam.py::cutmaster_auto_sync_audio` |
| Stateless LLM tool | (none added in v5) |
| Stateful AI product | (none added in v5) |

If a new tool doesn't fit one of these, it's two tools.
