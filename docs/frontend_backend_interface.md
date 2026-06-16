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
.venv\Scripts\python -m millikan_ai.cli detect-platforms --video <video_path> --config configs\default.yaml --count 3
```

For non-interactive CLI integration, a caller can create or request manual platform rows and run:

```powershell
.venv\Scripts\python -m millikan_ai.cli analyze --video <video_path> --config <generated_config.yaml> --run-dir <run_dir>
```

For downstream scientific validation after upstream trajectory extraction/filtering has already accepted trajectories, use the standalone API:

```python
from millikan_ai.downstream import run_downstream_analysis

result = run_downstream_analysis(
    trajectories=accepted_trajectories,
    platforms=voltage_platforms,
    scale_y_m_per_px=scale_y_m_per_px,
    config=config,
    run_dir=run_dir,
)
```

This standalone path does not require a video path and must not call tracking, candidate generation, or overlays. Raw-video runs remain diagnostic integration checks, not elementary-charge scientific validation.
The downstream entry point assumes trajectories have already been accepted by upstream extraction/filtering. Future upstream experiments may provide a longest grid-line-avoiding segment or an upstream-associated multi-segment trajectory, but this contract does not add a stitching API in the downstream branch.

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
- `best_track_segments.csv`: per-platform terminal-velocity fits for the selected/default droplet.
- `drop_track_segments.csv`: per-platform terminal-velocity fits for all selected droplets.
- `candidate_tracks_summary.csv`: ranked candidate droplet quality table.
- `platforms.csv`: voltage platform boundaries and values.
- `auto_platform_suggestions.csv`: visual voltage-display boundary suggestions before user voltage values are bound.
- `drop_results.json`: physical `q` calculation result.
- `multi_drop_results.json`: per-drop physical `q` results and valid drop counts.
- `platform_velocity_results.csv`: normalized per-platform terminal velocity results for downstream physics UI panels.
- `drop_charge_results.csv`: one row per successfully computed q; every row enters elementary-charge estimation.
- `drop_charge_failures.json`: explicit physics failure records for drops that did not produce a formal q, including `point_estimate_only` rows when q and radius exist but finite positive random q uncertainty is unavailable.
- `model_comparison.json`: elementary-charge quantized-vs-continuous predictive comparison summary.
- `uncertainty_details.json`: current uncertainty summary and implemented/pending uncertainty methods.
- `plots_data.json`: machine-readable data for downstream scientific plots.
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
- voltage platform time intervals and auto platform suggestions when available
- selected droplet marker
- selected droplet trajectory
- all selected droplet trajectories in the `drop_tracks` layer when more than one track is selected
- Trackpy segment diagnostics on trajectory points when present, including `segment_id`, `blocked_by_grid`, and `end_reason`

Standalone downstream runs write a concise debugging report and machine outputs without video visualization layers. Use `drop_charge_results.csv`, `elementary_charge_result.json`, `model_comparison.json`, `uncertainty_details.json`, and `plots_data.json` for those panels.

Elementary-charge output is a predeclared bounded inversion over the fixed internal interval `[1.35e-19, 1.90e-19] C`. This interval is not a user setting. `elementary_charge_result.json.valid` is retained only as numeric-fit compatibility; UI validity must use `fundamental_spacing_identified`.
The estimator also exposes `optimizer.profile_optimization_incomplete`, `optimizer.failed_optimizations`, `optimizer.local_modes_omitted`, and `optimizer.important_local_modes_omitted`. A run with `profile_optimization_incomplete=true` must be displayed as a bounded diagnostic candidate only, even if `valid=true`.

`diagnostic_overlay.jpg` is a rendered preview of the same concepts. The UI should prefer `visualization_layers.json` for interactive overlays and use the image as a quick preview or fallback.

## Run Manifest Schema

`run_manifest.json` contains:

- `schema_version`: integer contract version.
- `run_dir`: run output directory.
- `status`: `video_readable`, `valid_for_q`, `valid_for_elementary_charge`, `elementary_estimation_ready`, `bounded_estimate_available`, `quantization_supported`, `elementary_status`, `drop_valid`, `ml_training`, and combined `flags`.
- `counts`: platform, selected drop, physically valid drop, selected/default track row, and selected/default segment counts.
- `coordinate_system`: pixel and time conventions for frontend rendering.
- `video`: metadata copied from `diagnostics.json`.
- `roi`: microscope, tracking, and voltage ROI.
- `grid`: detected grid lines, measurement lines, and scale.
- `visualizations`: static diagnostic image and overlay video paths.
- `primary_results`: charge, uncertainty, radius, and elementary-charge fields when available.
- `files`: all output artifact paths keyed by config output name.
- `frontend_panels`: ordered panel suggestions for the desktop UI.

The UI should not infer validity from file existence. Use `status.valid_for_q`, `status.valid_for_elementary_charge`, and `status.flags`. `status.valid_for_elementary_charge` is true only when `fundamental_spacing_identified=true`; a bounded candidate alone should be displayed as diagnostic/partial, not as a successful elementary-charge result.

## Validity Report

`validity_report.json` is the detailed checklist behind `manifest.status.valid_for_q`.

Important fields:

- `overall_valid_for_q`: whether the current run satisfies q calculation requirements.
- `overall_valid_for_elementary_charge`: whether bounded elementary-charge estimation identified a primitive fundamental spacing with calibrated support.
- `elementary_estimation_ready`: whether enough successful q values exist to attempt the estimator; this is not final validity.
- `bounded_estimate_available`, `quantization_supported`, and `elementary_status`: compact estimator state for UI badges and warnings.
- `combined_flags`: includes scientific guard flags such as `profile_optimization_incomplete`, `prior_boundary_hit`, `integer_assignments_nonprimitive`, and `evidence_not_calibrated`.
- `blocking_failed_checks`: check ids that block q validity.
- `checks`: detailed pass/fail objects with `id`, `passed`, `message`, and `details`.

The UI should show failed checks directly instead of hiding the reason behind a generic invalid state.

## Frontend Display Checklist

The desktop UI should show these panels for each run:

1. Video validity summary from `analysis_report.md` or `drop_results.json`.
2. Annotated screenshot from `diagnostic_overlay.jpg`.
3. Interactive layer overlay from `visualization_layers.json`.
4. Track overlay video from `overlay_best_track.mp4`.
5. Platform editor table backed by `platforms.csv`.
6. Candidate ranking table backed by `candidate_tracks_summary.csv`.
7. Per-platform terminal-velocity fits backed by `best_track_segments.csv`.
8. Physics calculation backed by `drop_results.json`.
9. Multi-drop track and segment tables backed by `drop_tracks.csv`, `drop_track_segments.csv`, and `multi_drop_results.json`.
10. Flags and failure reasons from `diagnostics.json`, `drop_results.json`, and `elementary_charge_result.json`.
11. Detailed legality checklist from `validity_report.json`.

## Manual Platform UI Contract

Voltage OCR is not part of the current `develop`/`main` backend flow. The UI should ask:

- number of voltage platforms
- start frame and end frame, or accept auto-detected boundary suggestions
- voltage in volts

The backend can detect visual voltage-display changes with the user-provided platform count and write `auto_platform_suggestions.csv`. The UI should show suggested stable intervals and transition windows, then ask the user to enter or confirm voltage values. Accepted rows are written to `platforms.csv` with `source=auto_boundary_manual_voltage`.

The backend validates frame ranges and records manual entries as non-OCR sources. The UI must not label manually entered voltages as automatic OCR. If no manual platforms are provided, the backend writes `requires_manual_platforms`; if suggestions exist without accepted voltage values, it writes `requires_manual_platform_voltages`.

## Candidate Quality Fields

`candidate_tracks_summary.csv` may include extra diagnostic columns beyond the required schema. The UI should surface them when present:

- `num_points` and `duration_s`: reliable detected points and total candidate segment duration.
- `blocked_by_grid_count` and `end_reason`: whether/why the Trackpy single-drop segment ended, such as `grid_occlusion`, `missing_limit`, `roi_exit`, `jump_rejected`, or `video_end`.
- `max_step_px`, `step_p95_px`, and `path_efficiency`: motion continuity diagnostics.
- `vy_px_s`, `vx_px_s`, `r2_y`, and `rmse_y`: whole-segment linear motion diagnostics used for ranking.
- `mass_cv`: Trackpy mass stability diagnostic.
- `grid_clear_fraction`: fraction of valid detections not too close to detected grid lines.
- `roi_clear_fraction`: fraction of valid detections not too close to the tracking ROI edge.
- `reject_reason`: comma-separated hard-rule reasons such as `too_close_to_grid_lines`, `too_close_to_tracking_roi_edge`, or `insufficient_stable_platform_fits`.
- `duplicate_of`: the retained candidate id when this row was rejected as `duplicate_track`.
- `selected_for_multi_drop`: whether this candidate was tracked through the multi-drop q evaluation path.
- `drop_id`: per-drop result id when the candidate was selected for multi-drop evaluation.
- `q_valid`: whether the candidate produced a physically valid q result.
- `physics_flags`: q calculation failure reasons such as `non_positive_alpha`.
- `charge_abs_C` and `radius_m`: post-physics values when `q_valid` is true.

These fields explain why bright grid intersections, watermarks, borders, edge highlights, or physically impossible tracks are not counted as valid droplets.

## Downstream Scientific Output Units

Standalone downstream reports display radius in micrometres and charge/sigma charge in `1e-19 C`. Machine CSV/JSON files keep SI values such as `radius_m`, `charge_abs_C`, and `sigma_charge_random_C`, and may include display columns such as `radius_um`, `charge_1e_minus_19_C`, and `sigma_charge_total_1e_minus_19_C`.

`uncertainty_details.json` reports random per-drop uncertainty, optional shared systematic Monte Carlo, combined charge intervals, and e-level systematic intervals. Shared systematic draws reuse one sampled set of scale, plate distance, voltage calibration, viscosity/temperature, pressure, oil density, and Cunningham `b` values across all drops, then rerun the elementary estimator on the full sampled q set.

## Multi-Drop Contract

The current default tracks up to `tracking.max_drops: 20` distinct trajectories and computes q per selected track. Existing selected/default drop fields remain stable:

- keep `run_manifest.json.schema_version` versioned
- keep `primary_results` for the selected/default drop
- choose the selected/default drop as the highest-ranked physically valid q result; if no selected result is valid, fall back to the highest-ranked evaluated candidate with explicit flags
- keep `best_track.csv`, `best_track_segments.csv`, and `drop_results.json` for that selected/default drop
- use `drop_tracks.csv`, `drop_track_segments.csv`, and `multi_drop_results.json` for all selected drops
- use `run_manifest.json.counts.valid_drops` and `multi_drop_results.json.valid_drop_count` for the valid-droplet count
- use `elementary_charge_result.json` for the estimator over every successfully computed q in standalone downstream analysis; video-pipeline `keep` remains a diagnostic quality-adapter field
- keep single-drop reports valid when only one droplet is found

## Current Quality Scope

The backend uses the Trackpy single-droplet local tracker as the main tracking base. Multiple candidate seeds are tracked independently, grid-line neighborhoods terminate the current reliable segment, duplicate trajectories are removed before q evaluation, and no cross-grid reconnection is attempted. The deterministic quality adapter remains untrained and exposes `mode=mock_rule_adapter`, `trained=false`. The UI should display `quality_score`, `keep`, `q_valid`, and `reject_reasons`.
