# AiForMillikan

Python backend and CLI for Millikan oil drop experiment video analysis.

This stage implements a non-ML backend framework:

- OpenCV video inspection and diagnostic frames
- automatic microscope ROI and grid scale calibration
- manual voltage platform input for trusted voltage/time ranges
- multi-keyframe droplet seeding with Trackpy-based local single-drop tracking, grid-neighborhood cutoffs, segment scoring, and deduplication
- terminal velocity fitting
- physics-based single-drop charge inversion
- adaptive multi-drop q inversion and explainable rule-based quality filtering
- non-ML elementary charge grid-search estimator
- standalone downstream analysis for already accepted trajectories
- run output validation and summaries

ML-based trajectory filtering is intentionally left to `training_quality_filter/`.

Current tracking scope: the backend uses the teammate Trackpy single-droplet local tracker as the upstream tracking base. Multiple seeds are tracked independently, a track segment is cut when the predicted droplet enters a grid-line neighborhood, and grid-crossing reconnection is intentionally not attempted.

## Setup

Use a project-local virtual environment.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e . pytest
```

Do not install dependencies globally or into the base Conda environment. Use `.venv\Scripts\python -m pip ...` from this project directory.

## Test

```powershell
.venv\Scripts\python -m pytest tests -q --basetemp runs\pytest_tmp_work -o cache_dir=runs\pytest_cache_work
```

The test suite uses synthetic images/videos for deterministic grid, manual platform, tracking, velocity, charge, elementary-charge, and CLI behavior. It includes a three-droplet pipeline case that reaches `elementary_charge_result.json.valid=true` as a numeric bounded fit while keeping `fundamental_spacing_identified=false` until calibrated evidence is available.

## CLI

Start the guided interactive workflow from the repository root:

```powershell
.venv\Scripts\python run_millikan.py
```

The wizard asks for the video path, config path, measurement distance, plate distance, and manual voltage platform ranges. The backend uses the fixed experiment convention `+Y` downward and positive voltage pushing droplets upward; it no longer asks for a configurable voltage sign. It shows stage progress while running and prints the final run directory, report path, manifest path, and overlay path.

Inspect a raw video:

```powershell
.venv\Scripts\python -m millikan_ai.cli inspect raw_data\single.mp4 --save-frame runs\single_first.jpg
```

Run the backend pipeline with manual platform ranges:

```powershell
.venv\Scripts\python -m millikan_ai.cli run --video raw_data\2u.mp4 --config configs\default.yaml --platform 0:180:0 --platform 181:468:175
```

Generate the user-facing single-drop analysis report:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --platform 0:180:0 --platform 181:468:175
```

For the current `raw_data\2.mp4` demo video, use the guide voltages with automatic platform-boundary suggestions:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2.mp4 --config configs\default.yaml --auto-platform-count 3 --platform-value 0 --platform-value 239 --platform-value 362
```

The `run` and `analyze` commands print stage progress while the backend is working.

Validate and summarize a run:

```powershell
.venv\Scripts\python -m millikan_ai.cli validate --run-dir runs\<run_dir>
.venv\Scripts\python -m millikan_ai.cli summarize --run-dir runs\<run_dir>
```

## Output Contract

Each run directory writes:

- `run_config.yaml`
- `voltage_samples.csv`
- `auto_platform_suggestions.csv`
- `platforms.csv`
- `best_track.csv`
- `drop_tracks.csv`
- `best_track_segments.csv`
- `drop_track_segments.csv`
- `candidate_tracks_summary.csv`
- `diagnostics.json`
- `drop_results.json`
- `multi_drop_results.json`
- `platform_velocity_results.csv`
- `drop_charge_results.csv`
- `drop_charge_failures.json`
- `model_comparison.json`
- `uncertainty_details.json`
- `plots_data.json`
- `quality_scores.json`
- `trajectory_quality_scores.csv`
- `elementary_charge_result.json`
- `validity_report.json`
- `visualization_layers.json`
- `diagnostic_overlay.jpg`
- `overlay_best_track.mp4`
- `run_manifest.json`
- `summary.txt`
- `analysis_report.md`

Current `develop`/`main` does not run voltage OCR. It can automatically suggest voltage-platform boundaries by detecting visual changes in the voltage display, but the user still supplies the actual voltage values. If no usable platform rows are supplied, `diagnostics.json` includes `requires_manual_platforms` or `requires_manual_platform_voltages`. The run still records video metadata, grid calibration, candidate tracking, overlay, and validation-safe output files.

## Manual Platform Input

For reliable physical `q` calculation, provide manual voltage platforms through the root wizard, CLI flags, API, or config file:

For quick CLI testing, pass frame ranges directly. The format is `START_FRAME:END_FRAME:VOLTAGE`, and the CLI writes a reproducible config under `runs\manual_configs\`.

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --platform 0:180:0 --platform 181:468:175
```

For guided input, use:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --interactive-platforms
```

The guided flow asks for the number of voltage platforms, then each platform's start frame, end frame, and voltage.

For videos with a visible voltage display, the root wizard first asks for the expected platform count, tries to detect stable platform boundaries, discards short/unstable transition intervals, and then asks only for the voltage value of each accepted platform. If the detected count does not match the user-provided count, or a suggested platform is too short, the wizard falls back to manual frame ranges.

To inspect automatic boundary suggestions without running the full droplet pipeline:

```powershell
.venv\Scripts\python -m millikan_ai.cli detect-platforms --video raw_data\5.mp4 --config configs\default.yaml --count 3
```

To run non-interactively with auto-detected boundaries and user-provided voltage values:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\5.mp4 --config configs\default.yaml --auto-platform-count 3 --platform-value 0 --platform-value 150 --platform-value 259
```

You can also add `manual_platforms` to a config file:

```yaml
manual_platforms:
  - platform_id: P001
    start_frame: 0
    end_frame: 180
    start_time_s: 0.0
    end_time_s: 6.0
    voltage_V: 0.0
    voltage_confidence: 1.0
    source: manual
  - platform_id: P002
    start_frame: 181
    end_frame: 468
    start_time_s: 6.033
    end_time_s: 15.633
    voltage_V: 200.0
    voltage_confidence: 1.0
    source: manual
```

The backend records `source=manual`, `source=manual_cli`, `source=manual_ui`, or `source=auto_boundary_manual_voltage` in `platforms.csv`; it does not pretend manually entered voltages came from OCR. Automatic boundary evidence is written to `auto_platform_suggestions.csv`.

## Backend API

The future desktop app should call the backend API directly instead of shelling out through the CLI when possible:

```python
from millikan_ai.api import AnalysisRequest, ManualPlatformInput, analyze_video

result = analyze_video(
    AnalysisRequest(
        video_path="raw_data/2u.mp4",
        config_path="configs/default.yaml",
        manual_platforms=(
            ManualPlatformInput(0, 180, 0.0),
            ManualPlatformInput(181, 468, 175.0),
        ),
    )
)

print(result.run_dir)
print(result.manifest["status"])
```

The API writes the same output contract as the CLI, including `run_manifest.json`.

## Standalone Downstream API

For scientific validation of the downstream physics/e pipeline, use prepared accepted trajectories instead of raw videos:

```python
from millikan_ai.downstream import run_downstream_analysis

result = run_downstream_analysis(
    trajectories=accepted_trajectories,
    platforms=voltage_platforms,
    scale_y_m_per_px=scale_y_m_per_px,
    config=config,
    run_dir="runs/downstream_case",
)
```

This path does not call the tracker or read video frames. It writes `platform_velocity_results.csv`, `drop_charge_results.csv`, `drop_charge_failures.json`, `elementary_charge_result.json`, `model_comparison.json`, `uncertainty_details.json`, `plots_data.json`, and `analysis_report.md`.

Elementary-charge estimation is a predeclared bounded inversion, not an unconstrained blind search. The fixed internal prior interval is `[1.35e-19, 1.90e-19] C`; it is not user configurable, and old `e_search_min_C/e_search_max_C` keys are ignored with provenance recorded in `elementary_charge_result.json`. The legacy `valid` field means only that the numeric fit produced a bounded candidate. Scientific success must use `fundamental_spacing_identified`, which additionally requires no boundary hit, complete profile optimization, stable modes, primitive integer assignments, and calibrated quantization support. Profile optimization now retries tau/lambda nuisance fits from multiple starts and reports `profile_optimization_incomplete` when a required candidate still fails or an important local mode is omitted.

For shared systematic uncertainty, set `physics.systematic_mc_samples` and `physics.systematic_uncertainty` in the config. Each systematic draw uses one common set of sampled physical parameters across all drops, while per-drop random errors remain independent.
Each shared systematic draw also recomputes the full set of q values and reruns the elementary-charge estimator, so `uncertainty_details.json` includes `sigma_e_systematic_C`, systematic e intervals, and combined e intervals.

Slow estimator validation can be run on synthetic known-truth data:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python scripts\validate_estimator_simulation.py --preset smoke --replicates 3 --null-samples 20 --output runs\estimator_simulation_validation.json
```

For artificial review before scientific use, run at least:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python scripts\validate_estimator_simulation.py --preset quick_validation --profile-points 80 --null-samples 20 --output runs\estimator_simulation_validation.json
```

`smoke` uses a small default matrix for sanity checks. `quick_validation` enforces at least 50 replicates across N = 10, 15, 20, and 40; `full_validation` enforces at least 200. The script also accepts `--n-values`, `--noise-values`, `--bootstrap-samples`, `--measurement-mc-samples`, and `--difficult-replicates` for targeted benchmark slices, and writes both JSON and Markdown summaries. The summary separates numeric fit rates, bounded-candidate rates, final `fundamental_spacing_identified` rates, boundary hits, profile incompleteness, primitive-assignment failures, catastrophic errors, continuous-data false identification, and difficult harmonic/boundary cases. Raw-video smoke runs must not be used as elementary-charge scientific validation.

## Current Raw Video Behavior

`raw_data/2.mp4` currently runs end-to-end with automatic ROI/grid/tracking/overlay and writes `analysis_report.md` when auto-detected platform boundaries are combined with the guide voltage values. With platform values supplied, the backend can select stable droplets and compute real physics-based `q`. Without platform values, the run is explicitly invalid for q calculation.

Tracking is constrained to the detected grid area so watermarks, manufacturer text, and border highlights are excluded from candidate droplet selection. Candidate ranking also penalizes tracks that stay too close to grid lines or tracking ROI edges, which reduces false positives from grid intersections and edge highlights. The tracker samples multiple keyframes for seeds, then processes each video frame once and passes the shared preprocessed gray frame to all active Trackpy single-drop states. Each state searches only a local window around its predicted position.

For frontend review, each run writes `run_manifest.json`, `validity_report.json`, `visualization_layers.json`, `plots_data.json`, and `diagnostic_overlay.jpg`. The manifest is the desktop UI entry point; the validity report lists pass/fail checks; the layer JSON provides structured drawing data for interactive frontend overlays, `plots_data.json` provides renderer-neutral elementary-charge chart data, and the diagnostic image is a rendered preview. See `docs/frontend_backend_interface.md` for the desktop UI contract.

`plots_data.json` uses `schema_version: 2` and does not contain PNG, SVG, HTML, Plotly, or ECharts options. It contains four backend-computed chart datasets: charge distribution with quantized and continuous predictive density curves, integer assignment comb, phase residuals, and per-droplet quantized-vs-continuous predictive score contributions. These charts remain diagnostic when `fundamental_spacing_identified=false`; formal support still depends on `quantization_supported` and `evidence_label`.

Raw smoke-test findings for the current `1.mp4` through `8.mp4` samples and older archived videos are recorded in `docs/raw_video_smoke.md`.

Raw-video smoke runs are diagnostic integration checks only; they are not scientific validation of the elementary-charge estimator.

With reliable platform data, the downstream physics path uses the fixed sign convention:

```text
time_s = frame_idx / fps
v_y_m_s = v_y_px_s * scale_y_m_per_px
v = alpha - gamma * U
eta(T) = Sutherland air viscosity from viscosity.air_temperature_C, unless direct viscosity is configured
eta_eff(r) = eta / (1 + b / (p * r))
r and |q| are computed from alpha, gamma, eta_eff, and plate distance d
```

Within each voltage platform, the downstream velocity fitter uses the whole confirmed constant-voltage platform by default. It may apply `segment.boundary_guard_frames` when configured, but it no longer drops a fixed mechanical transient interval or chooses the highest-R2 sub-window as the default calculation path. R2, first/second-half slopes, residual autocorrelation, and fit warnings are diagnostics rather than universal hard filters.

For a single oil drop, elementary-charge blind estimation is intentionally reported as underdetermined because it needs multiple independent `q_i` values.

By default, `tracking.max_drops` is `20`. The tracker samples multiple keyframes, deduplicates trajectories, and evaluates each selected track through the real q pipeline. `drop_results.json` remains the selected/default drop result for backward compatibility. Track rows may include `segment_id`, `pred_x_px`, `pred_y_px`, `blocked_by_grid`, `missed_count`, `mass`, and `end_reason`; these fields expose the Trackpy local tracker diagnostics while preserving the existing required columns.

Tracked droplets and physically valid droplets are distinct. `candidate_tracks_summary.csv` records post-physics fields such as `q_valid`, `physics_flags`, `charge_abs_C`, and `radius_m`; `run_manifest.json.counts.valid_drops` and `multi_drop_results.json.valid_drop_count` are the authoritative valid-droplet counts for reports and frontend display.

The quality adapter is deterministic and reports `trained=false`. It is diagnostic/frontend-facing; elementary-charge estimation consumes every successfully computed `q_valid=true` drop rather than applying a second `keep=true` quality gate.

When multiple selected tracks are evaluated, `best_track.csv`, `best_track_segments.csv`, and `drop_results.json` use the highest-ranked physically valid drop. If no selected drop has valid q, they fall back to the highest-ranked evaluated candidate and report explicit physics flags.
