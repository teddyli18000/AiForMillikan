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

## Test

```powershell
.venv\Scripts\python -m pytest tests -q
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
- `best_track_segments.csv`
- `candidate_tracks_summary.csv`
- `diagnostics.json`
- `drop_results.json`
- `quality_scores.json`
- `elementary_charge_result.json`
- `overlay_best_track.mp4`
- `summary.txt`
- `analysis_report.md`

If automatic voltage OCR cannot produce reliable platform voltages, `diagnostics.json` includes `requires_manual_platforms`. The run still records video metadata, grid calibration, candidate tracking, overlay, and validation-safe output files.

## Manual Platform Input

For reliable physical `q` calculation, add `manual_platforms` to a config file when OCR confidence is low:

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

The backend records `source=manual` in `platforms.csv`; it does not pretend manual corrections came from OCR.

## Current Raw Video Behavior

`raw_data/2u.mp4` currently runs end-to-end with automatic ROI/grid/tracking/overlay and writes `analysis_report.md`, but voltage OCR is rejected as low confidence, so physical charge output is invalid until manual platforms are supplied. This is intentional safety behavior.

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

For a single oil drop, elementary-charge blind estimation is intentionally reported as underdetermined because it needs multiple independent `q_i` values.
