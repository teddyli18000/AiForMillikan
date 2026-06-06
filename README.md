# AiForMillikan

Python backend and CLI for Millikan oil drop experiment video analysis.

This stage implements a non-ML backend framework:

- OpenCV video inspection and diagnostic frames
- automatic microscope ROI and grid scale calibration
- local template-based voltage OCR with strict confidence filtering
- voltage platform segmentation
- non-ML bright-blob droplet tracking and best-candidate selection
- terminal velocity fitting
- physics-based single-drop charge inversion
- opt-in multi-drop backend outputs while preserving the selected/default drop contract
- non-ML elementary charge grid-search estimator
- run output validation and summaries

ML-based trajectory filtering is intentionally left to `training_quality_filter/`.

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

The test suite uses synthetic images/videos for deterministic OCR, grid, platform, tracking, velocity, charge, elementary-charge, and CLI behavior.

## CLI

Inspect a raw video:

```powershell
.venv\Scripts\python -m millikan_ai.cli inspect raw_data\single.mp4 --save-frame runs\single_first.jpg
```

Run the backend pipeline:

```powershell
.venv\Scripts\python -m millikan_ai.cli run --video raw_data\2u.mp4 --config configs\default.yaml --non-interactive
```

Generate the user-facing single-drop analysis report:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml
```

Validate and summarize a run:

```powershell
.venv\Scripts\python -m millikan_ai.cli validate --run-dir runs\<run_dir>
.venv\Scripts\python -m millikan_ai.cli summarize --run-dir runs\<run_dir>
```

## Output Contract

Each run directory writes:

- `run_config.yaml`
- `voltage_samples.csv`
- `platforms.csv`
- `best_track.csv`
- `drop_tracks.csv`
- `best_track_segments.csv`
- `drop_track_segments.csv`
- `candidate_tracks_summary.csv`
- `diagnostics.json`
- `drop_results.json`
- `multi_drop_results.json`
- `quality_scores.json`
- `elementary_charge_result.json`
- `validity_report.json`
- `visualization_layers.json`
- `diagnostic_overlay.jpg`
- `overlay_best_track.mp4`
- `run_manifest.json`
- `summary.txt`
- `analysis_report.md`

If automatic voltage OCR cannot produce reliable platform voltages, `diagnostics.json` includes `requires_manual_platforms`. The run still records video metadata, grid calibration, candidate tracking, overlay, and validation-safe output files.

## Manual Platform Input

For reliable physical `q` calculation, add `manual_platforms` to a config file when OCR confidence is low:

For quick CLI testing, pass frame ranges directly. The format is `START_FRAME:END_FRAME:VOLTAGE`, and the CLI writes a reproducible config under `runs\manual_configs\`.

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --platform 0:180:0 --platform 181:468:175
```

For guided input, use:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --interactive-platforms
```

The guided flow asks for the number of voltage platforms, then each platform's start frame, end frame, and voltage. This is the preferred current workflow because raw video OCR is not trusted yet.

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

The backend records `source=manual` or `source=manual_cli` in `platforms.csv`; it does not pretend manual corrections came from OCR.

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

## Current Raw Video Behavior

`raw_data/2u.mp4` currently runs end-to-end with automatic ROI/grid/tracking/overlay and writes `analysis_report.md`, but voltage OCR is rejected as low confidence, so physical charge output is invalid until manual platforms are supplied. With CLI manual platforms, the backend can select a stable single droplet and compute a real physics-based `q`. This OCR rejection is intentional safety behavior.

Tracking is constrained to the detected grid area so watermarks, manufacturer text, and border highlights are excluded from candidate droplet selection. Candidate ranking also penalizes tracks that stay too close to grid lines or tracking ROI edges, which reduces false positives from grid intersections and edge highlights.

For frontend review, each run writes `run_manifest.json`, `validity_report.json`, `visualization_layers.json`, and `diagnostic_overlay.jpg`. The manifest is the desktop UI entry point; the validity report lists pass/fail checks; the layer JSON provides structured drawing data for interactive frontend overlays, including multi-drop tracks when `tracking.max_drops > 1`; the diagnostic image is a rendered preview. See `docs/frontend_backend_interface.md` for the desktop UI contract.

Raw smoke-test findings for `2u.mp4`, `3u1.mp4`, and `3u2.mp4` are recorded in `docs/raw_video_smoke.md`.

With reliable platform data, the single-drop calculation uses:

```text
time_s = frame_idx / fps
v_y_m_s = v_y_px_s * scale_y_m_per_px
E = voltage_sign * U / d
v = alpha + beta * E
eta_eff(r) = eta / (1 + b / (p * r))
r = sqrt(9 * eta_eff(r) * alpha / (2 * rho * g))
q = 6 * pi * eta_eff(r) * r * beta
```

Within each voltage platform, the backend fits the best stable sub-window after dropping the transient interval. It does not blindly fit the whole platform when early motion is unstable.

For a single oil drop, elementary-charge blind estimation is intentionally reported as underdetermined because it needs multiple independent `q_i` values.

By default, `tracking.max_drops` is `1` so raw-video smoke tests stay conservative. Raising it enables multi-drop candidate selection and per-track q calculation outputs in `drop_tracks.csv`, `drop_track_segments.csv`, and `multi_drop_results.json`. `drop_results.json` remains the selected/default drop result for backward compatibility.

Tracked droplets and physically valid droplets are distinct. `candidate_tracks_summary.csv` records post-physics fields such as `q_valid`, `physics_flags`, `charge_abs_C`, and `radius_m`; `run_manifest.json.counts.valid_drops` and `multi_drop_results.json.valid_drop_count` are the authoritative valid-droplet counts for reports and frontend display.

When multiple selected tracks are evaluated, `best_track.csv`, `best_track_segments.csv`, and `drop_results.json` use the highest-ranked physically valid drop. If no selected drop has valid q, they fall back to the highest-ranked evaluated candidate and report explicit physics flags.
