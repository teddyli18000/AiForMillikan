# AGENTS.md — Normal

## Scope

`normal/` is a standalone desktop application. It must not import from
`experimental/`, and it must not expose Experimental worker operations.

- `src/millikan_ai/normal/` — Normal backend: video inspection, `0 V` suggestion,
  grid detection, local single-drop tracking, crossing review, q calculation,
  transient sessions, export, and blind inversion.
- `src/millikan_ai/desktop_worker.py` — the only IPC entry point. It exposes
  exactly the twelve `normal.*` operations.
- `apps/desktop/` — Electron main/preload plus the React workspace.
- `tests/` — Normal-only tests. Do not reintroduce Experimental ops or fixtures.

The backend package name remains `millikan_ai` so import paths stay stable, but
this project's `src/` contains only `millikan_ai/__init__.py`,
`millikan_ai/desktop_worker.py`, and `millikan_ai/normal/`.

## Contract Rules

- `normal.inspectVideo` is pure: metadata and a playable URL only. It must not
  create a session or run `0 V`, grid, tracking, or q calculation.
- `normal.prepareVideo` is the expensive step and emits Normal progress events.
- `active_video.state` is limited to `video_prepared`, `boundary_confirmed`,
  `target_selected`, and `tracking`. Record `status` owns
  `pending_crossing_review`, `pending_user_confirmation`, `accepted`,
  `diagnostic`, `rejected_crossing_identity`, and `rejected_by_user`.
- Worker operations must enforce predecessor states; disabled buttons are not a
  contract.
- `normal.confirmBoundary` is a second-based API. Seconds are authoritative even
  when stale frame indices are present.
- Target selection is restricted to the confirmed `0V_start_s ± 0.5 s` window,
  enforced by both backend and renderer.
- Stages are reversible. Boundary changes invalidate target/tracking/review/q
  candidate state; target/time/box changes invalidate tracking/review/q
  candidate state. Existing records stay immutable unless explicitly excluded.
- Sessions are transient per launch. `normal.initialize` without an explicit
  `session_root` must create a fresh session. The Electron shell cleans
  implicit transient roots on exit. Export is the only retention mechanism.
- At least three user-kept valid q records are required before blind inversion.
- After acceptance, "next droplet" must call a worker operation: same video
  resets `active_video.state` to `boundary_confirmed`, different video clears
  `active_video` while keeping accepted records.

## Physics and UI Rules

- Balance voltage is required. Other physical parameters default from
  `millikan_ai/normal/config.py` and are editable in a collapsed advanced panel.
- Pressure is `pressure_kPa` in the Normal contract. Do not persist new
  `pressure_Pa` fields.
- `sigma_q_C` comes from slope uncertainty and q(v) propagation, not an
  RMSE/R2 heuristic or a q-level percentage floor.
- Normal uses its own weighted integer-residual grid-search inversion. It must
  not call the Experimental elementary estimator.
- Without a fitted continuous baseline, do not output `quantized_favored`,
  `continuous_favored`, or any model-win claim.
- `reference_comparison` uses `1.602176634e-19 C` for display only. It must not
  influence search, ranking, assignments, or flags.
- All user-facing time controls are in seconds. Frame indices are internal.
- The target preview is the main video player paused at the selection frame; do
  not add a separate screenshot preview.
- The full-trajectory review plays backend-generated frames. The renderer must
  not redraw or infer track coordinates.
- Stage 5 formula values come from the record's calculation trace. The renderer
  formats but does not recompute radius, viscosity, q, or sigma_q.
- Stage 6 has one canonical result card in the main content area; the inspector
  must not duplicate it.

## Packaged Acceptance

- `scripts/probe_packaged_worker.py` must pass against the packaged worker. It
  drives the full Normal sequence on a synthetic video and checks exported
  artifacts, not physical accuracy.
- `apps/desktop/tests/electron-smoke.mjs` must pass against `release/win-unpacked`.
  It is the only check that exercises the real preload/IPC path; React tests use
  the demo API and do not replace it.
- Do not remove these checks from CI. They are the release acceptance loop.

## Commands

```powershell
cd normal
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python scripts\probe_packaged_worker.py --worker apps\desktop\dist-worker\millikan-normal-worker.exe
cd apps\desktop
npm test
npm run build
npm run worker:build
node tests\electron-smoke.mjs
```

## Encoding

- Worker IPC is UTF-8 JSON Lines without BOM.
- `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` are mandatory for development and
  packaged workers.
- Node decodes stdout/stderr with the streaming UTF-8 decoder in
  `electron/utf8StreamDecoder.ts`.
- Keep `tests/test_text_encoding.py` passing for Chinese labels, superscripts,
  and scientific symbols.

## Versioning

The app version lives in three places and must match:
`pyproject.toml`, `apps/desktop/package.json`, and
`apps/desktop/package-lock.json`. `tests/test_version_consistency.py` enforces
this.
