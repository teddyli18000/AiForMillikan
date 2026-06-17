# Normal Mode V2 Reference Mapping

## Reference Scope

The teammate reference project at `C:\Users\Teddy\Desktop\追踪` is read-only input. V2 may reuse ideas and measured behavior, but packaged runtime must not import, execute, or otherwise depend on that directory.

The failed branch `feature/normal-balance-fall-mode` is not the implementation base. It may be inspected only as a negative reference for coverage gaps and integration pitfalls.

## Teammate Reference Structure

- `README.md`: describes a CLI flow: track one droplet, compute one q, collect q summaries, estimate e.
- `configs/single_drop.yaml`: records the reference `test.mp4` parameters, including `start_frame: 55`, `end_frame: 210`, `diameter: 5`, `minmass: 80`, local search radius, max accept distance, and memory frames.
- `src/millikan_ai/video/io.py`: reads one frame or a contiguous frame sequence, optionally cropped to ROI.
- `src/millikan_ai/tracking/grid_mask.py`: builds a bright static grid mask from sampled frames and provides crop/inpaint helpers.
- `src/millikan_ai/tracking/core.py`: contains the reusable single-drop Trackpy local search and prediction loop.
- `src/millikan_ai/tracking/single_drop.py`: CLI wrapper for user ROI/initial point, frame loading, tracking, CSV, and overlay output.
- `src/millikan_ai/tracking/overlay.py`: renders detected and missing positions into an MP4 overlay.
- `src/millikan_ai/physics/q_from_track.py`: computes falling velocity and q from a single track CSV using balance voltage and scale.
- `src/millikan_ai/elementary/estimate.py`: simple weighted integer-multiple e estimator.

## Algorithm Flow Observed

1. Read configured frame range from the video.
2. Optionally build a static bright grid mask.
3. Convert frames to grayscale, optionally removing grid mask.
4. Use the user-selected initial position as frame 0 truth.
5. For each following frame:
   - predict next position from current search center and velocity;
   - optionally skip detection near grid;
   - crop a local search window;
   - run Trackpy locate in the local crop;
   - reject candidates on the grid mask;
   - choose nearest candidate to prediction;
   - if accepted, update position and velocity;
   - if missing, advance prediction and increment missing count;
   - stop after memory limit.
6. Write a track CSV with detected and predicted positions.
7. Render overlay.
8. Compute velocity from detected points by linear `y(t)` fit.
9. Compute q from a balance-fall formula.

## Required Bug Fix

Reference `tracking/core.py` updates velocity after reacquisition as:

```text
velocity = current_position - last_detected_position
```

When multiple frames were missing, this treats a multi-frame displacement as a one-frame velocity. V2 must record `last_detected_frame` and update:

```text
velocity = (current_position - last_detected_position) / frame_gap
```

The test `test_reacquired_velocity_is_normalized_by_frame_gap` must fail before implementation and pass after.

## Mapping To V2

| Reference file/function | V2 destination | V2 behavior |
| --- | --- | --- |
| `video/io.py::read_bgr_frame` | `normal_v2/video_io.py::read_frame` | Read exact target/review frame for player and worker payloads. |
| `video/io.py::load_bgr_frames` | `normal_v2/video_io.py::iter_frames` / `read_frame_window` | Load only the confirmed tracking window plus context; no external dependency. |
| `grid_mask.py::crop_frame_to_roi` | `normal_v2/grid_calibration.py::crop_to_roi` | Keep explicit ROI validation. |
| `grid_mask.py::build_static_grid_mask` | `normal_v2/grid_calibration.py::detect_grid` | Detect actual horizontal/vertical grid lines and mask; expose second/penultimate y lines. |
| `grid_mask.py::remove_static_grid_from_gray` | `normal_v2/tracking.py::preprocess_frame` | Optional preprocessing helper internal to normal tracker. |
| `core.py::SingleDropTrackingConfig` | `normal_v2/tracking.py::NormalTrackingConfig` | Keep small parameter set; hide from normal user UI. |
| `core.py::locate_features_near_position` | `normal_v2/tracking.py::locate_local_features` | Same local Trackpy idea, configured through normal config. |
| `core.py::choose_nearest_feature` | `normal_v2/tracking.py::choose_candidate` | Add status and quality fields for review. |
| `core.py::is_position_near_grid` | `normal_v2/tracking.py::is_near_grid_mask` | Use for occlusion diagnostics, not to terminate track by default. |
| `core.py::track_single_droplet` | `normal_v2/tracking.py::track_single_drop` | Preserve cross-grid prediction/reacquire; add `tracking`, `missing`, `reacquired`; fix frame-gap velocity. |
| `single_drop.py::select_initial_droplet_position` | `apps/desktop` player box selection | User boxes current rendered frame; backend receives `target_frame`. |
| `overlay.py::make_single_droplet_overlay` | `normal_v2/reporting.py::write_review_overlay` and frontend canvas | Render real tracking/missing/reacquired states and detected grid lines. |
| `q_from_track.py::fit_line_y_time` | `normal_v2/velocity.py::fit_terminal_velocity` | Fit only real tracking/reacquired points inside confirmed time and legal grid region. |
| `q_from_track.py::compute_q` | `normal_v2/physics.py::compute_balance_fall_charge` | Independent physics with Cunningham positive root and uncertainty fields. |
| `elementary/estimate.py::estimate_elementary_charge` | `normal_v2/records.py` plus `normal_v2/elementary.py::estimate_normal_integer_fit` | Use as conceptual input only; V2 implements stronger guards. |

## Explicit Differences From Reference

- V2 does not use OpenCV modal ROI selection; target selection is in the Electron video player.
- V2 does not require CLI frame input.
- V2 records persistent session q records instead of overwriting a fixed `drop_001`.
- V2 does not use fixed 10% q uncertainty.
- V2 does not make q valid when grid calibration failed.
- V2 distinguishes diagnostic q records from inversion-eligible valid records.
- V2 supports no-recovery-voltage videos by ending at the last reliable measured point.
- V2 reports structured artifacts for the frontend and final export bundle.
