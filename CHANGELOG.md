# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] — 2026-05-26

v5 port — agent coverage catch-up across 12 clusters, shipped in 3 waves. 42
new MCP tools + 9 templates + Phase 0 version/Studio gate helpers. Verified
against Resolve 21.0.0b.20. See
[`Implementation/cutmaster_ai/v5/proposal.md`](Implementation/cutmaster_ai/v5/proposal.md)
and [`api_verification.md`](Implementation/cutmaster_ai/v5/api_verification.md).

### Added — v5 Wave 1 · Coverage catch-up (verified against Resolve 21.0.0b.20)

- **C10 project setters (`tools/project.py`)** — typed enum-normalising wrappers
  around `project.SetSetting()`. 7 new tools, each verified against live
  `GetSetting()` round-trip:
  - `cutmaster_set_color_science_mode` — `davinciYRGB` / `davinciYRGBColorManaged`
    / `acescct` / `acescc` (with `yrgb`, `managed` aliases).
  - `cutmaster_set_color_space` — set any of input / timeline / output color
    space + gammas in one call; pass only the fields you want to change.
  - `cutmaster_set_timeline_format` — width / height / fps / pixel-aspect.
  - `cutmaster_set_proxy_mode` — `off` / `prefer_camera_originals` /
    `prefer_proxies`.
  - `cutmaster_set_optimized_media_mode` — boolean toggle.
  - `cutmaster_set_cache_mode` — `none` / `smart` / `user`.
  - `cutmaster_set_superscale_settings` — 1× / 2× / 3× / 4× upscale factor.
- **C11 Fairlight mix presets (`tools/fairlight.py`)** — Resolve **20.2.2+**,
  version-gated via `_requires_method` so older builds get a clean error
  instead of `'NoneType' object is not callable`. 2 new tools:
  - `cutmaster_get_fairlight_presets` — lists installed presets via
    `resolve.GetFairlightPresets()`.
  - `cutmaster_apply_fairlight_preset` — applies a preset to the current
    timeline via `project.ApplyFairlightPresetToCurrentTimeline(name)`.
- **C12 per-clip grade reset (`tools/color.py`)** — `cutmaster_reset_clip_grade`
  via `item.GetNodeGraph(layer_index).ResetAllGrades()`. Snapshots the
  project before mutating; destructive-op hook matcher already covers it.
- **Phase 0 helpers (`errors.py`)** — `ResolveVersionTooOld` exception and
  `_requires_method(obj, name, min_version)` + `_parse_version()` helpers.
- **Verification log** at `Implementation/cutmaster_ai/v5/api_verification.md`
  — source of truth for every Resolve API surface v5 wraps, with Confirmed
  / Rejected sections.

### Deferred — v5 Wave 1

- **C1 keyframes** is not part of this release. The official Resolve Developer
  Scripting README documents only `Resolve.GetKeyframeMode()` /
  `SetKeyframeMode()` (the global page-mode toggle); there is no documented
  `AddKeyframe` / `DeleteKeyframe` / `GetKeyframes` on `TimelineItem`. Live
  probe on Resolve 21.0.0b.20 confirmed those methods return `None`.
  Revisit once Blackmagic publishes a documented keyframe-create surface
  or a stable Resolve 21 reintroduces them. Full investigation logged in
  `Implementation/cutmaster_ai/v5/api_verification.md`.

### Added — v5 Wave 2 · Resolve-native AI ops (Studio only, verified on Resolve 21.0.0b.20)

- **C5 Magic Mask (`tools/clip_ai.py`)** — 2 new tools:
  - `cutmaster_create_magic_mask` — wraps `TimelineItem.CreateMagicMask(mode)`.
    Mode enum: `"F"` (forward — default), `"B"` (backward), `"BI"`
    (bidirectional). Friendly aliases `forward` / `backward` /
    `bidirectional` accepted.
  - `cutmaster_regenerate_magic_mask` — wraps `TimelineItem.RegenerateMagicMask()`.
- **C6 Smart Reframe + Stabilize (`tools/clip_ai.py`)** — 2 new tools, both
  zero-arg wrappers (the proposal's two-step `SetProperty + trigger`
  assumption was wrong — Resolve does not expose stabilization/reframe
  tuning via scripting). Compose with `cutmaster_set_timeline_format` to
  drive the Smart Reframe target aspect.
  - `cutmaster_smart_reframe` — wraps `TimelineItem.SmartReframe()`.
  - `cutmaster_stabilize` — wraps `TimelineItem.Stabilize()`.
- **C8 Native captions + scene cuts (`tools/timeline_native_ai.py`)** — 2 new
  tools, both Studio-gated:
  - `cutmaster_create_subtitles_from_audio` — wraps
    `Timeline.CreateSubtitlesFromAudio({...})` with the documented
    `autoCaptionSettings` dict. Friendly enums for 17 languages, 3 caption
    presets (default / teletext / netflix), single / double line break,
    chars-per-line override, gap. Resolves the underlying `resolve.AUTO_CAPTION_*`
    constants at runtime so we don't hard-code numeric enum values.
  - `cutmaster_detect_scene_cuts` — wraps `Timeline.DetectSceneCuts()`.
    **Destructive** — snapshots the project first via
    `snapshot_project(... label="pre_detect_scene_cuts")`. Destructive-op
    hook matcher already covers it.
- **C9 Native media-pool transcription (`tools/native_transcription.py`)** —
  3 new tools, distinct from `intelligence/transcription.py`'s
  Deepgram/Gemini path. Resolve's native transcription embeds the result
  into clip metadata (visible in inspector + searchable via smart bins).
  - `cutmaster_transcribe_clip(clip_name)` — wraps
    `MediaPoolItem.TranscribeAudio()`.
  - `cutmaster_clear_clip_transcription(clip_name)` — wraps
    `MediaPoolItem.ClearTranscription()`.
  - `cutmaster_transcribe_folder(folder_name="")` — bulk variant wrapping
    `Folder.TranscribeAudio()`; recurses through nested folders.

### Added — v5 Wave 3 · Authoring surfaces + Fusion safety (verified on Resolve 21.0.0b.20)

- **C4 Fusion comp introspection (`tools/fusion_inspect.py`)** — 4 read-only
  tools that let agents probe a comp's structure before mutating it:
  - `cutmaster_fusion_boundary_report` — terse summary (tool counts, input/
    output tools, render range). Wraps `Comp.GetToolList()` +
    `Comp.GetAttrs()`.
  - `cutmaster_fusion_probe_comp(cursor, limit)` — paginated full graph
    snapshot for deep comps; opaque base64 cursor.
  - `cutmaster_fusion_list_animated_inputs` — finds inputs with
    expressions or modifier-tool connections.
  - `cutmaster_fusion_check_render_safe` — boolean "is this comp safe to
    render?" + reasons (no inputs / no outputs / empty comp).
- **C2 Fuse plugin authoring (`tools/fuse_plugins.py`)** — 9 tools + 4
  bundled `.fuse` templates (`pass_through`, `single_input_image_op`,
  `dual_input_blend`, `time_modulator`). Write ops confined to the
  user-level Fuses dir; traversal-safe path resolution. Source validator
  catches missing `FuRegisterClass`, missing `Create()`/`Process()`,
  unbalanced braces, and banned calls (`os.execute`, `io.popen`,
  `loadfile`, `dofile`). Override `CUTMASTER_FUSE_DIR` for tests.
- **C3 DCTL authoring (`tools/dctl.py`)** — 9 tools + 5 bundled `.dctl`
  templates (`identity`, `lift_gamma_gain`, `single_axis_curve`,
  `false_color`, `gamut_clip`). Same write-safety surface as C2.
  Validator checks for `__DEVICE__`, `transform(...)`, `make_float3`,
  balanced braces, no `system(` calls. `cutmaster_apply_dctl_to_node`
  bridges to `Graph.SetLUT` with name-resolution across user + system
  search paths.
- **C7 Multicam — partial (`workflows/multicam.py`)** — 1 tool:
  - `cutmaster_auto_sync_audio(clip_names, sync_mode, channel, ...)` —
    wraps `MediaPool.AutoSyncAudio([items], {settings})` with friendly
    sync-mode + channel enums (`auto` / `mix` / 1-based int). 4-key
    settings dict built with runtime constant lookup.

### Deferred — v5 Wave 3

- **`cutmaster_setup_multicam_timeline`** — proposal called for a multicam-
  timeline-creator wrapping `MediaPool.CreateMultiCamClipWithMediaItems`,
  but that method is **not documented in the Resolve scripting README
  and not callable on Resolve 21.0.0b.20** (live probe returned `None`).
  Samuel's port calls it; ours can't ship it. Re-evaluate when Blackmagic
  publishes a documented multicam-create method.

### Fixed

- Shot-tag cache miss for cut-timeline items with non-zero in-points.
  The writer (`shot_tagger.plan_samples`) cached at canonical
  source-time keys `{0.3, 5.0, 10.0, …, src_dur − 0.3}` because every
  source-timeline clip starts at `in_s == 0`. The reader (paint /
  stamp on a cut timeline) was naïvely calling the same `plan_samples`
  against the cut item, producing keys `{in_s + 0.3, in_s + 5.0, …}`
  the writer never visited. Result: cuts that used mid-clip ranges
  (the common case) missed every cached tag — a live verification on
  `Timeline 1_AI_Cut_17` showed 2/9 V1 items hit cache, the only two
  that happened to start at `in_s == 0`. Fix: new
  `shot_tagger.plan_canonical_read_samples()` reconstructs the
  writer-canonical grid from `manifest.json` (now reliably read back
  via `_resolve_source_duration`) and intersects it with `[in_s,
  out_s]`. New `iter_cached_tags_for_cut_item()` is the high-level
  helper the painter and stamper now call. Verified live: same cut
  goes 2/9 → **9/9 painted**, 9/9 stamped, with `marker_added=True`
  on every row. Falls back to legacy `plan_samples` when no manifest
  exists so caches from older runs don't break entirely. Covered by
  13 new hermetic tests in `test_shot_tagger_canonical_read.py`.

### Added

- `POST /cutmaster/stamp-shot-metadata` + `/clear-shot-metadata`
  endpoints + Review-screen "Stamp shot metadata" button. Two
  complementary writes:
  (1) per-cut **TimelineItem markers** at frame 0 (color: Lavender,
  structured shot record packed into `customData` namespaced as
  `cutmaster.shot.v1`) — scoped to the cut, idempotent, removable;
  (2) optional **MediaPoolItem.SetMetadata** writing `Keywords`
  (e.g. `closeup, speaker_centered, calm`) and a `[CutMaster]…`
  prefixed `Description` so Resolve smart bins can search by shot
  type. The "smart bins" toggle on the panel lets editors opt out
  of the source-clip write when they want per-cut-only stamping
  with no cross-timeline propagation. Lives in
  `cutmaster.analysis.shot_metadata_stamper`; covered by 8 hermetic
  tests. Probe-validated against Resolve 21 — `TimelineItem.SetMetadata`
  is a phantom (raises on call), `TimelineItem.AddMarker` with
  `customData` is the only viable per-item persistence surface.
- `POST /cutmaster/paint-shot-colors` endpoint + Review-screen
  "Paint shot colors" button. After a build succeeds, paints each
  cut-timeline item by its modal cached `shot_type` (closeup → Orange,
  medium → Lime, wide → Teal, over-shoulder → Violet, broll → Blue,
  title-card → Pink). Reuses the analyze-time tag cache so no new
  Gemini calls are made; idempotent. Editor-set manual colors are
  preserved by default (overrideable via `overwrite=true`). Lives in
  `cutmaster.analysis.shot_color_painter`; covered by 7 hermetic tests.
- Pre-merge CI workflow (`.github/workflows/ci.yml`) with four parallel
  jobs — ruff lint + format check, pytest matrix on Python 3.11 and 3.12,
  gitleaks secrets scan, and an absolute home-path hygiene grep to catch
  `/Users/<name>/` leaks before they ship.
- SURFACE.md snapshot enforcement (`tests/surface_snapshot.json` +
  `scripts/dump_surface.py`). A new `surface` CI job fails PRs that
  change a `@mcp.tool` name, parameter schema, or output schema without
  a matching entry under `## [Unreleased]` in the changelog — closing
  the silent-break risk that SURFACE.md previously only described.

## [0.3.0] — 2026-04-20

### BREAKING

- **Renamed Python distribution from `celavii-resolve` to `cutmaster-ai`.**
  Users must `pip uninstall celavii-resolve && pip install cutmaster-ai`.
  Imports change from `celavii_resolve` to `cutmaster_ai`.
  Entry-point groups for third-party plugins renamed to
  `cutmaster_ai.tools` and `cutmaster_ai.panel_routes`. Console scripts
  are `cutmaster-ai` and `cutmaster-ai-panel`.
- **MCP tool names renamed** from `celavii_*` prefix to `cutmaster_*`
  prefix (~280 tools). Downstream skills, agents, and hook matchers
  using `mcp__celavii-resolve__celavii_*` must update to
  `mcp__cutmaster-ai__cutmaster_*`.
- **Environment variables renamed** `CELAVII_PANEL_HOST` / `_PORT` / `_DB`
  → `CUTMASTER_PANEL_HOST` / `_PORT` / `_DB`. Same for all other
  `CELAVII_*` config (`_LOG_FORMAT`, `_STT_PROVIDER`, `_DEEPGRAM_*`,
  `_VISION_CONCURRENCY`, `_<AGENT>_MODEL`, etc.).
- **Default filesystem paths renamed** `~/.celavii/panel/state.db` →
  `~/.cutmaster/panel/state.db`; `~/.celavii/cutmaster/` cache roots
  → `~/.cutmaster/cutmaster/`; `~/Documents/celavii-*` → `~/Documents/cutmaster-*`.
- **launchd Label + plist filename** `com.celavii.resolve-mcp` →
  `ai.cutmaster.mcp`; plist file renamed accordingly. Existing users
  need `launchctl unload` the old plist and re-install the new one.
- **LUT vendor directory** renamed `~/Library/.../LUT/Celavii/` →
  `~/Library/.../LUT/CutMaster/`.
- **Claude Code plugin name** in `.claude-plugin/plugin.json` renamed
  to `cutmaster-ai` — users who installed the old plugin will see two
  entries until they uninstall the old one.

The Celavii (company / parent org) brand is retained for: author field,
contact emails (`engineering@celavii.com`, `security@celavii.com`),
GitHub organisation `CelaviiHQ`, and the SQLite table prefix `studio_`
reserved for the closed-source Studio bundle. See `docs/naming.md` in
the private `cutmaster-studio` repo for the full brand hierarchy.

### Added

- Plugin discovery via two entry-point groups: `cutmaster_ai.tools` (FastMCP)
  and `cutmaster_ai.panel_routes` (FastAPI). Third-party packages can
  register capabilities on either surface without touching OSS code. See
  [SURFACE.md](SURFACE.md) and `src/cutmaster_ai/plugins.py`.
- `GET /pro/status` endpoint on the Panel HTTP server reporting
  `{tier, plugins: {tools, panel_routes}}`.
- `cutmaster_ai.licensing.current_tier()` — returns `"oss"` or
  `"standard"` based on whether any plugin has registered.
- `cutmaster-ai-panel` emits `PANEL_READY http://host:port` as its
  first stdout line so supervisors can discover a randomly assigned port
  (`CUTMASTER_PANEL_PORT=0` picks a free port).
- Idempotent SQLite migration runner at
  `cutmaster_ai.migrations.runner.apply_migrations(db_path)` plus
  `0001_init.sql` creating the initial panel state tables
  (`recent_projects`, `custom_presets`, `cutmaster_sessions`,
  `panel_state`). Runs at Panel boot; path via `CUTMASTER_PANEL_DB`.
- Stable Pydantic model re-exports at `cutmaster_ai.http.models` —
  plugins should import from here instead of the private
  `http.routes.*._models`.
- `SURFACE.md` documenting the versioned consumption contract for
  plugin authors and embedders.
- GitHub Actions workflows: `publish.yml` (tag → PyPI via Trusted
  Publishing) and `changelog-check.yml` (PRs touching `src/` must add a
  bullet under `## [Unreleased]`).

### Changed

- README and CLAUDE.md updated from "two consumers" to "three consumers"
  — MCP, Panel, and CutMaster Studio (the paid macOS app built on top of
  this package).

## [0.2.0] — 2026-04-18

Major restructuring pass to prepare the repo for open-source release. No behaviour changes — all ~240 tools behave identically, but many import paths have changed.

### Changed

- **`ai/` → `intelligence/`**: the old `ai/` subpackage is renamed to `intelligence/` to make room for a broader distinction between *stateless LLM tools* (single MCP call → single LLM roundtrip) and *stateful AI products* (CutMaster and future siblings).
- **`cutmaster/llm.py` promoted to `intelligence/llm.py`**: the shared LLM dispatch layer now lives under `intelligence/` so future products can reuse it without cross-imports from CutMaster.
- **`cutmaster/` split into 6 subpackages** (`core/`, `stt/`, `analysis/`, `media/`, `resolve_ops/`, `data/`) — see [docs/CUTMASTER_ARCHITECTURE.md](docs/CUTMASTER_ARCHITECTURE.md).
- **`http/routes/cutmaster.py` (1,020 LOC) → `http/routes/cutmaster/` package** with feature-split modules (`analyze`, `presets`, `info`, `build`, `execute`). URL prefix `/cutmaster/*` preserved — no panel client changes.
- **`panel/` → `apps/panel/`** and **`panel/resolve-plugin/` → `apps/resolve-plugin/`**. Non-Python deliverables now live under `apps/`.
- **`install.py` / `build-plugin.sh` → `scripts/`**. Top-level is cleaner.
- **`src/cutmaster_ai/lut_registry.py` → `src/cutmaster_ai/tools/lut_registry.py`** — it's a tool module, belongs with its siblings.
- **`launchd/` → `scripts/launchd/`**.

### Added

- `intelligence/` subpackage as a named home for single-shot LLM tools.
- `.pre-commit-config.yaml` with hooks that block `/Users/`, `/home/`, and common API-key patterns.
- [SECURITY.md](SECURITY.md) — responsible disclosure policy.
- [.github/CODEOWNERS](.github/CODEOWNERS) — auto-assigned review on sensitive paths.
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — first-time setup + responsibility model.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — public-facing layer model.
- [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md) — auto-generated tool catalogue.
- [apps/README.md](apps/README.md) — describes the non-Python deliverables.

### Removed

- Duplicate `.claude/agents/` (canonical copies live in top-level `agents/` for plugin distribution).
- `.mcp.json.backup`.

### Security

- Repository history audited with trufflehog 3.94.3 and gitleaks 8.30.1 — 0 secrets found.
- Pre-commit hooks now block accidental commit of hardcoded local paths.

## [0.1.0] — 2026-04-10

Initial pre-release with ~240 tools, CutMaster v2-8 (per-clip STT, speakers, clip hunter), and React Workflow Integration panel.
