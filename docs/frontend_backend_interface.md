# Frontend Backend Interface

This document defines the current backend contract for the future portable desktop UI.

## CLI/API Entry Point

The preferred backend entry point for the future desktop app is the Python API:

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
```

The CLI remains the test harness for the same backend flow:

```powershell
.venv\Scripts\python run_millikan.py
.venv\Scripts\python -m millikan_ai.cli analyze --video <video_path> --config configs\default.yaml --interactive-platforms
```

For non-interactive CLI integration, a caller can create or request manual platform rows and run:

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
- `visualization_layers.json`: structured drawing layers for frontend rendering.
- `diagnostic_overlay.jpg`: first-frame diagnostic image for UI review.
- `overlay_best_track.mp4`: full-video overlay of the selected track.
- `diagnostics.json`: machine-readable ROI, grid, timing, and visualization paths.
- `validity_report.json`: machine-readable legality and reasonableness checks.
- `best_track.csv`: per-frame selected droplet coordinates.
- `drop_tracks.csv`: per-frame coordinates for all selected droplets when multi-drop tracking is enabled.
- `best_track_segments.csv`: fitted stable velocity windows.
- `drop_track_segments.csv`: fitted stable velocity windows for all selected droplets.
- `candidate_tracks_summary.csv`: ranked candidate droplet quality table.
- `platforms.csv`: voltage platform boundaries and values.
- `drop_results.json`: physical `q` calculation result.
- `multi_drop_results.json`: per-drop physical `q` results and valid drop counts.
- `quality_scores.json`: deterministic quality-adapter metadata and aggregate counts.
- `trajectory_quality_scores.csv`: per-track trajectory score, physics score, keep decision, and reject reasons.
- `analysis_report.md`: user-facing full report.

`visualization_layers.json` currently contains layers for:

- microscope ROI
- tracking ROI
- voltage ROI
- detected vertical and horizontal grid lines
- measurement start/end lines
- `+X` and `+Y` pixel axes
- voltage platform time intervals
- selected droplet marker
- selected droplet trajectory
- all selected droplet trajectories in the `drop_tracks` layer when more than one track is selected

`diagnostic_overlay.jpg` is a rendered preview of the same concepts. The UI should prefer `visualization_layers.json` for interactive overlays and use the image as a quick preview or fallback.

## Run Manifest Schema

`run_manifest.json` contains:

- `schema_version`: integer contract version.
- `run_dir`: run output directory.
- `status`: `video_readable`, `valid_for_q`, `valid_for_elementary_charge`, `drop_valid`, `ml_training`, and combined `flags`.
- `counts`: platform, selected drop, physically valid drop, selected/default track row, and selected/default segment counts.
- `coordinate_system`: pixel and time conventions for frontend rendering.
- `video`: metadata copied from `diagnostics.json`.
- `roi`: microscope, tracking, and voltage ROI.
- `grid`: detected grid lines, measurement lines, and scale.
- `visualizations`: static diagnostic image and overlay video paths.
- `primary_results`: charge, uncertainty, radius, and elementary-charge fields when available.
- `files`: all output artifact paths keyed by config output name.
- `frontend_panels`: ordered panel suggestions for the desktop UI.

The UI should not infer validity from file existence. Use `status.valid_for_q`, `status.valid_for_elementary_charge`, and `status.flags`.

## Validity Report

`validity_report.json` is the detailed checklist behind `manifest.status.valid_for_q`.

Important fields:

- `overall_valid_for_q`: whether the current run satisfies q calculation requirements.
- `overall_valid_for_elementary_charge`: whether blind elementary-charge estimation produced a valid result.
- `blocking_failed_checks`: check ids that block q validity.
- `checks`: detailed pass/fail objects with `id`, `passed`, `message`, and `details`.
- `combined_flags`: flags collected from diagnostics, q calculation, and elementary-charge estimation.

The UI should show failed checks directly instead of hiding the reason behind a generic invalid state.

## Frontend Display Checklist

The desktop UI should show these panels for each run:

1. Video validity summary from `analysis_report.md` or `drop_results.json`.
2. Annotated screenshot from `diagnostic_overlay.jpg`.
3. Interactive layer overlay from `visualization_layers.json`.
4. Track overlay video from `overlay_best_track.mp4`.
5. Platform editor table backed by `platforms.csv`.
6. Candidate ranking table backed by `candidate_tracks_summary.csv`.
7. Stable velocity segments backed by `best_track_segments.csv`.
8. Physics calculation backed by `drop_results.json`.
9. Multi-drop track and segment tables backed by `drop_tracks.csv`, `drop_track_segments.csv`, and `multi_drop_results.json`.
10. Flags and failure reasons from `diagnostics.json`, `drop_results.json`, and `elementary_charge_result.json`.
11. Detailed legality checklist from `validity_report.json`.

## Manual Platform UI Contract

Voltage OCR is not part of the current `develop`/`main` backend flow. The UI should ask:

- number of voltage platforms
- start frame
- end frame
- voltage in volts

The backend validates frame ranges and records manual entries as non-OCR sources. The UI must not label manually entered voltages as automatic OCR. If no manual platforms are provided, the backend writes `requires_manual_platforms` and the run is not valid for q calculation.

## Candidate Quality Fields

`candidate_tracks_summary.csv` may include extra diagnostic columns beyond the required schema. The UI should surface them when present:

- `grid_clear_fraction`: fraction of valid detections not too close to detected grid lines.
- `roi_clear_fraction`: fraction of valid detections not too close to the tracking ROI edge.
- `reject_reason`: comma-separated hard-rule reasons such as `too_close_to_grid_lines`, `too_close_to_tracking_roi_edge`, or `insufficient_stable_platform_fits`.
- `selected_for_multi_drop`: whether this candidate was tracked through the multi-drop q evaluation path.
- `drop_id`: per-drop result id when the candidate was selected for multi-drop evaluation.
- `q_valid`: whether the candidate produced a physically valid q result.
- `physics_flags`: q calculation failure reasons such as `non_positive_alpha`.
- `charge_abs_C` and `radius_m`: post-physics values when `q_valid` is true.

These fields explain why bright grid intersections, watermarks, borders, edge highlights, or physically impossible tracks are not counted as valid droplets.

## Multi-Drop Contract

The current default tracks up to `tracking.max_drops: 20` distinct trajectories and computes q per selected track. Existing selected/default drop fields remain stable:

- keep `run_manifest.json.schema_version` versioned
- keep `primary_results` for the selected/default drop
- choose the selected/default drop as the highest-ranked physically valid q result; if no selected result is valid, fall back to the highest-ranked evaluated candidate with explicit flags
- keep `best_track.csv`, `best_track_segments.csv`, and `drop_results.json` for that selected/default drop
- use `drop_tracks.csv`, `drop_track_segments.csv`, and `multi_drop_results.json` for all selected drops
- use `run_manifest.json.counts.valid_drops` and `multi_drop_results.json.valid_drop_count` for the valid-droplet count
- use `elementary_charge_result.json` for the estimator over independent results with both `keep=true` and `q_valid=true`
- keep single-drop reports valid when only one droplet is found

## Current Quality Scope

The backend uses Kalman + bidirectional LK + detection fusion and an explainable rule adapter. The adapter is not trained and exposes `mode=mock_rule_adapter`, `trained=false`. The UI should display `quality_score`, `keep`, `q_valid`, and `reject_reasons`.
