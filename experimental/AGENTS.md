# AGENTS.md — Experimental

## Scope

`experimental/` is a standalone research desktop application. It must not import
from `normal/`, and its worker must not expose any `normal.*` operation.

- `src/millikan_ai/video/` — OpenCV metadata, frame sampling, diagnostic frames.
- `src/millikan_ai/api.py` — public backend API for the CLI and the worker.
- `src/millikan_ai/calibration/` — screen/ROI/grid calibration and scale.
- `src/millikan_ai/tracking/` — Trackpy multi-drop tracking, masks, seeding,
  segment cutoffs, deduplication, overlays.
- `src/millikan_ai/quality/` — deterministic runtime quality adapter. Training
  stays under `training_quality_filter/`.
- `src/millikan_ai/segments/` — platform segmentation and terminal-velocity fits.
- `src/millikan_ai/physics/` — single-drop charge inversion.
- `src/millikan_ai/elementary/` — bounded elementary-charge estimation.
- `src/millikan_ai/downstream.py` — standalone downstream API for accepted
  trajectories and platforms. It must not require a video path or tracker.
- `src/millikan_ai/desktop_worker.py` — the only IPC entry point.

## Pipeline Rules

- No voltage OCR. Boundaries may be auto-detected from visual display changes,
  but voltage values remain user/API supplied.
- Auto platform detection uses the expected platform count as a validation
  constraint. Rejected suggestions must fall back to manual input.
- Do not silently output physical results when fewer than two usable voltage
  platforms exist.
- Single-drop physics uses `+Y` downward and fits `v = alpha - gamma U`.
  Cunningham radius solving uses the closed-form positive root.
- Every successfully computed `q_valid=true` drop enters elementary estimation.
  Computation failures are excluded; the quality adapter is not a second gate.
- A successful q requires finite positive radius, finite positive charge, and a
  finite positive random q uncertainty. Missing uncertainty is
  `point_estimate_only` and does not enter the e model.
- Shared systematic uncertainty samples one common physical-parameter draw
  across all drops and reruns the estimator on each draw.
- Elementary estimation is a predeclared bounded inversion over `[1.35e-19,
  1.90e-19] C`. Do not expose the interval as editable config/CLI/UI state.
- `elementary_charge_result.json.valid` is a legacy numeric-fit field. Use
  `fundamental_spacing_identified` for the scientific conclusion.
- Candidate tracking rejects stationary grid/bright-spot candidates, stays
  inside the tracking ROI, and cuts segments with `end_reason=grid_occlusion`
  instead of reconnecting across grid lines.
- Process each video frame once for shared preprocessing; each active Trackpy
  state runs only a local search around its predicted point.
- Tracking defaults to `tracking.max_drops: 20`.
- Do not claim a trained ML filter is implemented. The adapter reports
  `mode=mock_rule_adapter`, `trained=false`.
- Keep the backend CPU-only. GPU/CUDA work needs a separately approved plan.

## Output Contracts

- `run_manifest.json` is the frontend entry point for a completed run.
- `plots_data.json` is renderer-neutral chart data: no PNG/SVG/HTML/Plotly/
  ECharts options.
- `validity_report.json` is the legality/reasonableness checklist.
- `visualization_layers.json` is the structured drawing contract.
- `diagnostic_overlay.jpg` shows pixel axes, ROIs, grid lines, measurement
  lines, the selected droplet, and its trajectory.
- `analysis_report.md` is the user-facing report; CSV/JSON/MP4 remain the
  machine-readable contract.
- Update `docs/frontend_backend_interface.md` whenever an artifact or panel
  contract changes.

## Runtime Paths

- The packaged worker embeds `configs/default.yaml` through PyInstaller
  `--add-data` and resolves it from `sys._MEIPASS`. Do not rely on a `configs/`
  folder placed next to the EXE.
- Packaged runs write under `MILLIKAN_RUN_ROOT`: Electron `userData/runs` when
  launched by the app, or `%LOCALAPPDATA%\MillikanAI\Experimental\runs` when the
  worker starts directly. `config.load_config` applies this override to
  `project.run_root`.
- Never write analysis output into `resources/worker` or another portable
  unpack directory.

## Commands

```powershell
cd experimental
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python run_millikan.py
.venv\Scripts\python -m millikan_ai.cli inspect ..\media\videos\2u.mp4
.venv\Scripts\python -m millikan_ai.cli analyze --video ..\media\videos\2u.mp4 --config configs\default.yaml --auto-platform-count 3 --platform-value 0 --platform-value 175 --platform-value 239
```

Media files live in `../media/`, not in this directory. Tests resolve them with
`MILLIKAN_MEDIA_ROOT` or by walking up to the repository `media/` folder.

## Encoding

- Worker IPC is UTF-8 JSON Lines without BOM.
- `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` are mandatory.
- Keep `tests/test_text_encoding.py` passing.

## Versioning

The app version lives in `pyproject.toml`, `apps/desktop/package.json`, and
`apps/desktop/package-lock.json`. `tests/test_version_consistency.py` enforces
the match.
