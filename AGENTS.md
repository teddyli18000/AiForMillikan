# AGENTS.md

## Project Context

This project analyzes Millikan oil drop experiment videos. The current backend is a Python package with a CLI MVP that should remain suitable for later PySide6/Qt desktop integration.

## Module Boundaries

- `src/millikan_ai/video/`: OpenCV video metadata, frame sampling, and diagnostic frames.
- `src/millikan_ai/api.py`: public backend API for CLI and future PySide6/Qt frontend integration.
- `src/millikan_ai/calibration/`: screen/ROI/grid calibration and physical scale estimation.
- `src/millikan_ai/tracking/`: scored detection, Kalman/LK/detection fusion, adaptive multi-drop tracking, deduplication, and overlays.
- `src/millikan_ai/quality/`: deterministic runtime quality adapter; training remains under `training_quality_filter/`.
- `src/millikan_ai/segments/`: voltage platform segmentation and terminal velocity fitting.
- `src/millikan_ai/physics/`: physics-based single-drop charge inversion.
- `src/millikan_ai/elementary/`: non-ML elementary charge estimation from computed drop results.
- `training_quality_filter/`: future ML/unsupervised trajectory quality filtering subsystem. Do not implement ML filtering in the main backend.

## Raw Data

`raw_data/` contains the current local smoke-test videos `1.mp4` through `8.mp4`; `raw_data/AGENTS.md` records the guide voltage values. Older sample videos may live under `raw_data_old/`.

## Commands

Use the local virtual environment:

```powershell
.venv\Scripts\python -m pytest tests -q --basetemp runs\pytest_tmp_work -o cache_dir=runs\pytest_cache_work
.venv\Scripts\python run_millikan.py
.venv\Scripts\python -m millikan_ai.cli inspect raw_data\2.mp4
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2.mp4 --config configs\default.yaml --auto-platform-count 3 --platform-value 0 --platform-value 239 --platform-value 362
```

All project dependencies must stay inside the project-local `.venv/`. Do not install Python packages globally or into the user's base Conda environment.

## Current Implementation Rules

- All thresholds and physical constants should come from `configs/default.yaml`.
- Current `develop`/`main` does not run voltage OCR. It may auto-detect voltage-platform boundaries from visual display changes, but voltage values remain user/API supplied. OCR experiment code is preserved on `feature/ocr-current-archive`; do not re-enable OCR on mainline without an explicit new plan.
- Auto platform detection uses the user-provided expected platform count as a validation constraint. Rejected suggestions, short platforms, or count mismatches must fall back to manual boundary input rather than silently entering q calculation.
- If ROI detection or tracking confidence is low, write explicit flags and allow manual/config-driven correction.
- Do not claim a trained ML filter is implemented. The runtime adapter must report `mode=mock_rule_adapter`, `trained=false`.
- Do not silently output physical results when fewer than two usable voltage platforms exist.
- `analysis_report.md` is the user-facing report for the selected/default drop plus any configured multi-drop outputs; CSV/JSON/MP4 files remain the machine-readable contract.
- Single-drop elementary-charge estimation must report insufficient independent drops rather than inventing `e_hat`.
- Platform velocity fitting should use the best stable sub-window inside each voltage platform, not blindly fit the whole platform.
- Candidate tracking and segment validation must reject stationary grid/bright-spot candidates using `segment.min_motion_displacement_px`.
- Tracking must process each video frame once for shared blob detection across active seeds; LK optical flow should run on a local patch around the tracked point rather than the full video frame.
- Candidate tracking must stay inside the detected grid/tracking ROI so watermarks, manufacturer text, and border highlights are not eligible droplets.
- Candidate ranking should penalize candidates too close to grid lines or tracking ROI edges using `tracking.min_grid_line_distance_px`, `tracking.min_grid_clear_fraction`, `tracking.min_tracking_roi_margin_px`, and `tracking.min_roi_clear_fraction`.
- CLI manual platform inputs use `--platform START_FRAME:END_FRAME:VOLTAGE`; generated configs are written under `runs/manual_configs/` and platforms use `source=manual_cli`. Auto-boundary runs use `--auto-platform-count N` plus repeated `--platform-value V` and write platform rows with `source=auto_boundary_manual_voltage`.
- `run_manifest.json` is the frontend-facing machine-readable entry point for a completed run. Keep it stable and update `docs/frontend_backend_interface.md` when adding/removing output artifacts or panel contracts.
- `validity_report.json` is the frontend-facing legality/reasonableness checklist. Add explicit checks there when adding new q, tracking, or multi-drop prerequisites.
- `visualization_layers.json` is the frontend-facing structured drawing contract. Prefer adding reusable layer objects there over encoding new UI-only information only in rendered images.
- `diagnostic_overlay.jpg` is the frontend-facing static visualization contract: it should show pixel `+X/+Y`, microscope ROI, tracking ROI, grid lines, measurement lines, selected droplet, and trajectory. Keep `docs/frontend_backend_interface.md` in sync when this contract changes.
- Multi-drop tracking defaults to the safety cap `tracking.max_drops: 20`; preserve the selected/default drop files for compatibility.
- Elementary-charge estimation may only consume drops with both `trajectory_quality_scores.csv.keep=true` and `q_valid=true`.
- Keep the backend CPU-only. GPU/OpenCV CUDA work requires a separately approved dependency plan.
- `candidate_tracks_summary.csv` may include post-physics columns such as `drop_id`, `q_valid`, `physics_flags`, `charge_abs_C`, and `radius_m`. Treat `selected_for_multi_drop=true` as "tracked for evaluation"; use `q_valid=true` or `multi_drop_results.valid_drop_count` for physically valid droplets.
- The selected/default drop should prefer the highest-ranked `q_valid=true` result. Do not use tracking rank alone when a lower-ranked selected candidate has a valid q and the top candidate is physically invalid.
- Segment rows for short or transient-cropped platforms must preserve the source `track_id`; blank `track_id` rows in `drop_track_segments.csv` can create fake drops in `multi_drop_results.json`.
