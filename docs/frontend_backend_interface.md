# Frontend Backend Interface

This document defines the current backend contract for the future portable desktop UI.

## CLI/API Entry Point

The backend entry point for a single video run is:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video <video_path> --config configs\default.yaml --interactive-platforms
```

For non-interactive UI integration, the frontend should create or request manual platform rows and run:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video <video_path> --config <generated_config.yaml> --run-dir <run_dir>
```

`manual_platforms` rows use the schema written to `platforms.csv`:

```yaml
manual_platforms:
  - platform_id: P001
    start_frame: 0
    end_frame: 180
    start_time_s: 0.0
    end_time_s: 6.0
    voltage_V: 0.0
    voltage_confidence: 1.0
    source: manual_ui
```

## Coordinate Convention

- Pixel origin is the top-left corner of the video frame.
- `+X` points right.
- `+Y` points down.
- `time_s = frame_idx / fps`.
- Physical vertical velocity is `vy_m_s = vy_px_s * scale_y_m_per_px`.

The frontend must display this convention when showing the analyzed screenshot.

## Required Visualization Outputs

Each run should expose `run_manifest.json`. The desktop UI should treat it as the primary entry point for a completed run, then load the referenced files from `manifest.files` and `manifest.frontend_panels`.

Each run should also expose:

- `run_manifest.json`: machine-readable run status, paths, coordinate convention, counts, and UI panel sources.
- `diagnostic_overlay.jpg`: first-frame diagnostic image for UI review.
- `overlay_best_track.mp4`: full-video overlay of the selected track.
- `diagnostics.json`: machine-readable ROI, grid, timing, and visualization paths.
- `best_track.csv`: per-frame selected droplet coordinates.
- `best_track_segments.csv`: fitted stable velocity windows.
- `candidate_tracks_summary.csv`: ranked candidate droplet quality table.
- `platforms.csv`: voltage platform boundaries and values.
- `drop_results.json`: physical `q` calculation result.
- `analysis_report.md`: user-facing full report.

`diagnostic_overlay.jpg` currently draws:

- microscope ROI
- tracking ROI
- detected vertical and horizontal grid lines
- measurement start/end lines
- `+X` and `+Y` pixel axes
- selected droplet marker
- selected droplet trajectory

## Run Manifest Schema

`run_manifest.json` contains:

- `schema_version`: integer contract version.
- `run_dir`: run output directory.
- `status`: `video_readable`, `valid_for_q`, `drop_valid`, `ml_training`, and combined `flags`.
- `counts`: platform, track row, and stable segment counts.
- `coordinate_system`: pixel and time conventions for frontend rendering.
- `video`: metadata copied from `diagnostics.json`.
- `roi`: microscope, tracking, and voltage ROI.
- `grid`: detected grid lines, measurement lines, and scale.
- `visualizations`: static diagnostic image and overlay video paths.
- `primary_results`: charge, uncertainty, radius, and elementary-charge fields when available.
- `files`: all output artifact paths keyed by config output name.
- `frontend_panels`: ordered panel suggestions for the desktop UI.

The UI should not infer validity from file existence. Use `status.valid_for_q` and `status.flags`.

## Frontend Display Checklist

The desktop UI should show these panels for each run:

1. Video validity summary from `analysis_report.md` or `drop_results.json`.
2. Annotated screenshot from `diagnostic_overlay.jpg`.
3. Track overlay video from `overlay_best_track.mp4`.
4. Platform editor table backed by `platforms.csv`.
5. Candidate ranking table backed by `candidate_tracks_summary.csv`.
6. Stable velocity segments backed by `best_track_segments.csv`.
7. Physics calculation backed by `drop_results.json`.
8. Flags and failure reasons from `diagnostics.json`, `drop_results.json`, and `elementary_charge_result.json`.

## Manual Platform UI Contract

Voltage OCR is not trusted for current raw videos. The UI should ask:

- number of voltage platforms
- start frame
- end frame
- voltage in volts

The backend validates frame ranges and records manual entries as non-OCR sources. The UI must not label manually entered voltages as automatic OCR.

## Current Non-ML Scope

The backend performs non-ML hard-rule quality filtering and single-droplet tracking. ML trajectory filtering remains out of scope for the current backend and should be represented as disabled or future work in the UI.
