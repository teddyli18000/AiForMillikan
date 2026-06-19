# Frontend Backend Interface

This document defines the current backend contract for the future portable desktop UI.

## CLI/API Entry Point

The Electron desktop app talks to a Python worker over newline-delimited JSON.
The worker is implemented in `millikan_ai.desktop_worker` and wraps the same
public APIs described below. In development Electron starts
`.venv\Scripts\python -m millikan_ai.desktop_worker`; production packages a
PyInstaller onefile worker beside the Electron app.

Supported worker operations:

- `video.inspect`: inspect video metadata and optional diagnostic frame data.
- `platform.detectBoundaries`: suggest voltage-platform frame ranges from visual display changes; voltage values still come from the user.
- `analysis.run`: run the backend with explicit manual voltage platforms.
- `analysis.runAuto`: run with auto-detected boundaries plus user-supplied voltage values.
- `analysis.loadRun`: load `run_manifest.json` and frontend-facing artifacts for an existing run.
- `analysis.validate`: validate a run directory and return checklist/report artifacts.
- `downstream.run`: run standalone downstream physics/e analysis from accepted trajectories.
- `report.export`: copy Markdown, CSV/JSON, overlay, plots data, and a reproducibility manifest into a user-selected package folder or zip.

Normal-mode operations use a separate `normal.*` namespace and must not call the
Experimental `analysis.*` flow as a shortcut. Current Normal operations are:

- `normal.initialize`: create a fresh transient Normal session for this app
  launch and return backend defaults. It must not auto-load records from a
  previous launch unless an explicit `session_root` is provided by an in-flight
  operation from the same session.
- `normal.inspectVideo`: inspect a video and return metadata plus a playable
  file URL. It must not create or modify a session, detect `0 V`, detect grid
  lines, track, or calculate q.
- `normal.prepareVideo`: after the user clicks start, suggest `0V_start_s` and
  `0V_end_s`, detect grid lines, update the active video to `video_prepared`,
  and emit Normal-only progress events.
- `normal.confirmBoundary`: persist the user-confirmed second-based `0 V`
  window and advance the active video to `boundary_confirmed`.
- `normal.selectTarget`: persist balance-voltage confirmation, sparse
  per-record parameter overrides, and the user rectangle selection; advance to
  `target_selected`.
- `normal.saveMeasurement`: from `target_selected`, run the Normal-only local
  Trackpy single-drop tracker from the actual selected frame, fit the `0 V`
  falling velocity, compute `q_i ± sigma_q_i`, and create a record in
  `pending_crossing_review`, `pending_user_confirmation`, or `diagnostic`.
- `normal.prepareCrossingReview`: generate and cache one local magnified
  crossing clip on demand.
- `normal.reviewCrossing`: save `same_drop` or `different_drop`. Unreviewed
  crossings block acceptance; `different_drop` moves the record to
  `rejected_crossing_identity`.
- `normal.updateRecordSelection`: user-confirm or exclude a q record.
  `kept=true` is allowed only from `pending_user_confirmation`; it moves the
  record to `accepted`.
- `normal.runInversion`: run the Normal-only weighted integer residual grid
  search over accepted q records.
- `normal.exportSession`: export the Normal session report, q table, inversion
  JSON, and review artifacts.

Experimental/current-backend operations remain available for the Experimental
mode only. The renderer must not mix Normal session records into Experimental
run manifests or feed Experimental candidate tracks into Normal inversion.

The renderer must not read arbitrary files directly. It should use Electron IPC
for file dialogs, run loading, artifact reads, PDF generation, and export.
Backend output files remain internal run artifacts for reproducibility, while
the user-facing report is rendered in the app. The UI may offer an export action
that saves PDF/Markdown plus selected machine-readable files to a chosen path.

## Normal Mode Contract

Normal is the main recommended workflow for the physics-themed experiment. It is
not a fully automatic video-to-e pipeline. The app supplies AI assistance and
blind inversion, while the user confirms the physical measurements that are
ambiguous in real videos.

### Normal Session

A Normal session is transient and starts fresh on every application launch.
Within one launch it may contain q records from multiple videos, because the
experiment needs several independent droplets and a single short video may not
contain enough usable measurements. Long-term persistence is not implicit:
records are durable only when the user explicitly exports the session.
The Electron shell owns cleanup for implicit transient sessions created during
the launch: on application exit it must delete those tracked session roots so
unexported cache/session directories do not survive as future experiments.

Session-level fields:

```json
{
  "schema_version": 1,
  "session_id": "normal_...",
  "created_at": "...",
  "updated_at": "...",
  "transient": true,
  "records": [],
  "counts": {
    "total": 0,
    "valid": 0,
    "kept_valid": 0
  },
  "eligible_for_inversion": false,
  "inversion": null
}
```

`eligible_for_inversion` is true only when at least three kept records have
`status=accepted`, finite positive `q_C`, finite positive `sigma_q_C`, and no
unreviewed or rejected crossing identity.

Normal state is split but must stay consistent:

- frontend `video_imported` is local UI state after a pure
  `normal.inspectVideo`; the backend session is not mutated by inspect.
- backend `active_video.state` owns video-level states through tracking setup:
  `video_prepared`, `boundary_confirmed`, `target_selected`, `tracking`.
- record `status` owns post-tracking outcomes: `pending_crossing_review`,
  `pending_user_confirmation`, `accepted`, `diagnostic`,
  `rejected_crossing_identity`, `rejected_by_user`.

Backend code must never copy a record status into `active_video.state`.
After `normal.saveMeasurement`, `normal.reviewCrossing`, or
`normal.updateRecordSelection`, the active video remains in a video-level state
unless a rejected record is restored for adjustment. Adjustment restore sets
`active_video.state=boundary_confirmed` and carries the record's original video,
metadata, URL, grid, boundary, target, balance voltage, and parameter overrides.

The combined user-visible state machine is:

```text
video_imported
→ video_prepared
→ boundary_confirmed
→ target_selected
→ tracking
→ pending_crossing_review
→ pending_user_confirmation
→ accepted
```

Exceptional states are:

```text
diagnostic
rejected_crossing_identity
rejected_by_user
```

Worker operations must check predecessor state. The frontend may disable
buttons for usability, but the worker remains the authority.

Rejected or diagnostic records remain in the transient session for adjustment
and evidence. They are never eligible for inversion. When the user chooses
"return/adjust", the UI restores the record's previous video, preview URL,
metadata, grid, boundary, selection time, target rectangle, balance voltage,
and parameter overrides, then returns to the boundary-confirmation stage so the
user can adjust `0V_start_s`/`0V_end_s` before selecting and retracking. Retrying
creates a new record linked to the previous record with `retry_of_record_id`;
the old record remains immutable evidence.

### Normal Video Preparation

`normal.inspectVideo` returns only video metadata and a playable file URL.

`normal.prepareVideo` returns:

- video metadata: path, fps, frame count, width, height, duration in seconds
- suggested `0V_start_s` and `0V_end_s`
- equivalent frame indices for reproducible artifacts
- detected horizontal grid lines
- effective measurement region from the second line to the penultimate line
- `scale_y_m_per_px`
- warnings/flags when voltage-operation or grid detection confidence is low

Normal progress events are separate from Experimental progress:

```json
{
  "request_id": "req_...",
  "operation": "prepare_video",
  "stage": "sample_voltage_region",
  "label": "正在采样电压显示区域",
  "current": 36,
  "total": 120,
  "unit": "frames",
  "fraction": 0.3,
  "indeterminate": false
}
```

`fraction` is present only when it is derived from real `current / total`.
Unquantified stages must set `indeterminate=true`.

All user-facing time controls in Normal use seconds. The UI should offer coarse
`±1 s` and fine `±0.1 s` nudges for both `0V_start_s` and `0V_end_s`. The UI may
display frame numbers as secondary provenance, not as the primary editing unit.

After boundary confirmation, target selection is limited to a small window near
the user-confirmed `0V_start_s`. The window is centered on the value confirmed
by the user, not the original auto suggestion and not the beginning of the
video:

```json
{
  "selection_window": {
    "start_s": "max(0, confirmed_0V_start_s - 0.5)",
    "end_s": "min(video_duration_s, confirmed_0V_start_s + 0.5)",
    "source": "normal_v1_default"
  }
}
```

The frontend must clamp `selection_time_s` to this range and show the range to
the user. The backend must reject target frames outside the same range.
Tracking must start from the actual selected frame, never from an earlier
`0V_start_s` frame with coordinates taken from a later selection frame.

The main video player is the selection-frame preview. When the UI enters target
selection, it must pause the main video and seek to `selection_time_s`, which
defaults to the backend-confirmed `zero_v_start_s`. The `selection_time_s`
input, `±1 s` / `±0.1 s` nudges, scrubber, displayed video frame, and submitted
`target_frame` must stay synchronized. A separate screenshot preview is not a
replacement for this contract.

If the user modifies `0V_start_s` or `0V_end_s`, any stale
`selection_window` or frame index fields carried by an older boundary object
must be discarded before confirmation. `normal.confirmBoundary` is a
second-based user-confirmation API: if a client accidentally sends both seconds
and stale frame indices, seconds are authoritative. The worker recomputes frame
indices and the selection window from the normalized, user-confirmed boundary.

Normal stages are reversible. The UI must expose explicit previous-stage
actions instead of relying only on a sidebar. Returning to a stage restores the
last user-confirmed state for that stage. If the user changes an upstream
dependency, downstream state is invalidated as follows:

- boundary changes invalidate target, tracking, crossing review, q candidate,
  and inversion state for the in-progress measurement
- target time or rectangle changes invalidate tracking, crossing review, q
  candidate, and inversion state for the in-progress measurement
- crossing review changes recompute whether the record may advance to user
  confirmation
- accepted historical records are immutable evidence unless the user explicitly
  excludes them; retrying creates a new `retry_of_record_id`

Return/adjust restoration must use the relevant record or in-progress
measurement snapshot. `active_video.adjustment` may override record fields only
when its `record_id` matches the record being adjusted; otherwise the frontend
must ignore it to avoid restoring an unrelated or initial boundary.

### Normal Measurement Record

Each saved Normal record represents one user-reviewed droplet measurement:

```json
{
  "record_id": "rec_...",
  "video_path": "...",
  "video_sha256_16": "...",
  "balance_voltage_V": 240.0,
  "time_window": {
    "zero_v_start_s": 1.8,
    "zero_v_end_s": 4.7,
    "zero_v_start_frame": 54,
    "zero_v_end_frame": 141
  },
  "target": {
    "target_time_s": 1.5,
    "selection_window": {"start_s": 0.8, "end_s": 2.3},
    "source_center": {"x": 430.0, "y": 220.0},
    "source_video_box": {"x": 424.0, "y": 214.0, "width": 12.0, "height": 12.0}
  },
  "parameter_overrides": {},
  "grid": {},
  "tracking": {},
  "crossing_events": [],
  "q": {
    "valid": true,
    "q_C": 6.4e-19,
    "sigma_q_C": 4.0e-20,
    "radius_m": 8.0e-7,
    "flags": []
  },
  "status": "pending_user_confirmation",
  "kept": false
}
```

The record must keep enough provenance to reproduce the q calculation: the
video identity, selected droplet position, edited `0 V` window, grid scale,
physical constants or overrides, track rows, velocity fit, and q uncertainty.
It should also keep `retry_of_record_id` when it was created from a previous
rejected/diagnostic record's adjustment path.

### Normal Tracking And Crossing Review

Normal tracks one selected droplet at a time. The algorithm must be copied or
reimplemented inside this repository from the teammate local Trackpy
single-drop tracker at `C:\Users\Teddy\Desktop\追踪`; do not import that external
project.

The Normal v1 tracking parameters are locked to the teammate implementation
unless a later user-approved plan changes them:

```json
{
  "diameter": 5,
  "minmass": 80,
  "local_search_radius": 45,
  "max_accept_distance": 30,
  "single_memory": 5,
  "local_topn": 20,
  "grid_reject_dilate_px": 0,
  "grid_occlusion_radius": 0,
  "skip_detection_on_grid": true,
  "grid_mask_for_tracking_enabled": true,
  "grid_removal_enabled": false
}
```

The tracker should output per-frame rows with at least:

```csv
frame_idx,time_s,x_px,y_px,pred_x_px,pred_y_px,detected,missed_count,blocked_by_grid,mass,state,reason
```

When the predicted or measured droplet enters a grid-line neighborhood, or when
the track is missing around a grid line, the backend should create a clickable
`crossing_event`:

```json
{
  "id": "crossing_001",
  "start_time_s": 2.1,
  "end_time_s": 2.4,
  "review_start_time_s": 1.1,
  "review_end_time_s": 3.4,
  "center_x_px": 430.0,
  "center_y_px": 512.0,
  "kind": "grid_crossing_or_reacquire"
}
```

The UI should play a local magnified review of roughly one second before and
after the crossing. If the video is too short or the crossing is near the
beginning/end, clip the review window to valid video bounds instead of failing.
The review is generated only when the user opens that crossing review.

`normal.prepareCrossingReview` returns the current record, the selected event,
and a renderer-playable frame sequence. Existing clip paths may remain as
export artifacts, but the desktop UI must not depend on Chromium being able to
decode the generated MP4:

```json
{
  "event_id": "crossing_001",
  "review_clip_path": ".../crossing_001.mp4",
  "review_clip_url": "file:///.../crossing_001.mp4",
  "review_frames": [
    {
      "frame_index": 88,
      "time_s": 2.933,
      "image_path": ".../crossing_001_frames/frame_0000.jpg",
      "image_url": "file:///.../crossing_001_frames/frame_0000.jpg",
      "source_video_box": {"x": 382, "y": 464, "width": 96, "height": 96}
    }
  ],
  "review_clip_start_time_s": 2.0,
  "review_clip_end_time_s": 4.0
}
```

The frame images must be generated from backend crop/track data with the same
identity evidence as the review clip. If the frame sequence cannot be generated,
the UI must show an explicit error instead of a black or empty player.

Review results are limited to:

```text
same_drop
different_drop
```

All crossings must be reviewed as `same_drop` before a q record can become
`accepted`. Any `different_drop` result permanently blocks that record from
inversion unless the user reselects and retracks.

The main record review video must be generated from backend track rows and must
show the teammate overlay style: green circle plus `target`, yellow circle plus
`missing`, and a blue trajectory line. The frontend must not draw or infer
target/missing/trajectory positions that are absent from the backend record.

### Normal Physical Parameters

Balance voltage is required for each measurement. The following parameters
default from config and may be overridden in a collapsed advanced panel for the
current measurement only:

- plate distance
- grid measurement distance
- air viscosity or temperature-derived viscosity settings
- pressure in `kPa`
- oil density
- Cunningham correction constant
- uncertainty settings for the current q estimate

Normal records must store the effective parameters actually used. Parameter
overrides are not global config changes unless a future explicit "save as
default" action is added.

Normal default physics parameters are backend-owned:

```json
{
  "gravity_m_s2": 9.79,
  "air_viscosity_Pa_s": 1.83e-5,
  "pressure_kPa": 101.325,
  "cunningham_b_kPa_m": 8.226e-6
}
```

The frontend must display values returned by `normal.initialize` and must send
only fields the user actually changed. It must not maintain another set of
silent physical defaults. Legacy `pressure_Pa` or `cunningham_b_Pa_m` inputs may
be accepted at worker boundaries only for conversion to the Normal kPa
contract; new records should persist `pressure_kPa` and
`cunningham_b_kPa_m`.

For Normal v1, q uncertainty is limited to the random velocity-fit contribution
unless a source is explicitly documented in config. The velocity fit uses
linear regression on `y(t)`:

```text
sigma_s^2 = SSR / (N - 2) / sum((t_i - mean(t))^2)
sigma_v = scale_y_m_per_px * sigma_s
```

`sigma_q_C` is then propagated through the nonlinear `q(v)` relation using the
local logarithmic sensitivity. The old empirical RMSE/R2 expression and a
q-level `5%` floor must not be used for `sigma_q_C`. If a finite positive
`sigma_v` or propagated `sigma_q_C` cannot be computed, the record is
diagnostic and ineligible for inversion. Inversion may still add its own
`sigma_floor_C` to prevent infinite weights; that floor is not written back to
the q record.

### Normal Inversion And Visualization

After at least three accepted q records exist, `normal.runInversion` runs the
Normal-only weighted integer residual grid search. It uses each record's
`q_C` and `sigma_q_C`, applies `sigma_eff_i^2 = sigma_q_i^2 + sigma_floor^2`,
assigns integer multiples, re-estimates `e` with fixed integer assignments,
iterates until the assignment vector stabilizes or reaches the iteration cap,
deduplicates identical assignment vectors, reports sorted candidate solutions,
and exposes chart data showing:

- observed q values with uncertainty
- nearest `n * e_hat` levels
- residuals normalized by `sigma_q_C`
- quantized alignment diagnostics

Normal inversion is a teaching and evidence tool. With exactly three records it
must be labeled exploratory. Until a real continuous baseline is defined and
fitted, Normal must not output `quantized_favored`, `continuous_favored`, or any
model-win claim. The UI may show residual and alignment plots only.

The underlying backend entry point remains the Python API:

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

`plots_data.json` is the elementary-charge interactive visualization contract. It uses `schema_version: 2`, standard JSON values only, and no renderer-specific chart options. The top-level `charts` object contains:

- `charge_distribution`: observed `q_i`, `sigma_q_i`, integer assignments, optional histogram bins, quantized predictive density from the fitted bounded quantized model, continuous predictive density from the fitted comparison GMM, and `n * e_hat` reference levels.
- `integer_assignment`: one point per droplet with `drop_id`, `track_id`, `q_C`, `sigma_q_C`, `n_hat`, nearest quantized charge, residual, normalized residual, assignment probability, and flags.
- `phase_residual`: one point per assigned droplet with `phase_residual = q_i / e_hat - round(q_i / e_hat)`, a phase histogram, and a zero reference line.
- `model_comparison`: total quantized/continuous ELPD fields and per-droplet `delta_log_predictive_density`. The per-droplet values sum to `delta_elpd`.

The manifest should expose this file through a frontend panel like `elementary_charge_visualization` with `source=plots_data.json` and `status_source=elementary_charge_result.json`. The UI may render the charts with ECharts, Plotly, Qt Charts, or another library, but should not treat `quantization_favored=true` as formal support unless `quantization_supported=true`.

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
