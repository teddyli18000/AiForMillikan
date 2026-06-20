# AGENTS.md

## Project Context

This project analyzes Millikan oil drop experiment videos. The current desktop direction is an Electron + React frontend talking to a project-local Python worker. The product direction is split into two explicit modes:

- `Normal`: the mainline workflow. It is a human-in-the-loop balance-voltage + `0 V` falling measurement mode. The app assists with video inspection, `0 V` interval suggestions, grid detection, single-drop local tracking, crossing review, q calculation, session records, and blind elementary-charge inversion.
- `Experimental`: the existing automatic multi-drop / multi-platform backend and UI path. It is kept as an experimental half-finished route and must not drive Normal design decisions.

For the physics-themed experiment, the AI value proposition is intelligent assistance and blind inversion with inspectable evidence, not an unreviewed fully automatic answer.

## Module Boundaries

- `src/millikan_ai/video/`: OpenCV video metadata, frame sampling, and diagnostic frames.
- `src/millikan_ai/api.py`: public backend API for CLI and the existing Experimental/current backend integration.
- `src/millikan_ai/calibration/`: screen/ROI/grid calibration and physical scale estimation.
- `src/millikan_ai/tracking/`: Trackpy-based local single-drop tracking, static/grid-calibration mask handling, adaptive multi-drop seed scheduling, segment cutoffs, deduplication, and overlays. Older Kalman/LK fusion helpers may remain as tested utilities but are not the main tracking backend.
- `src/millikan_ai/quality/`: deterministic runtime quality adapter; training remains under `training_quality_filter/`.
- `src/millikan_ai/segments/`: voltage platform segmentation and terminal velocity fitting.
- `src/millikan_ai/physics/`: physics-based single-drop charge inversion.
- `src/millikan_ai/elementary/`: non-ML elementary charge estimation from computed drop results.
- `src/millikan_ai/normal/`: Normal-mode backend. This module owns the balance-voltage + `0 V` falling workflow, copied/reimplemented single-drop local tracking, Normal-only q records, transient per-launch Normal sessions, crossing-review artifacts, and Normal-only weighted integer residual inversion.
- `src/millikan_ai/downstream.py`: standalone scientific downstream API for already accepted trajectories, voltage platforms, calibration scale, and physical config. It must not require a video path, tracker, candidate generation, or overlays.
- `training_quality_filter/`: future ML/unsupervised trajectory quality filtering subsystem. Do not implement ML filtering in the main backend.

## Normal / Experimental Separation

- Normal and Experimental must stay separated in UI state, worker operations, backend modules, session/output contracts, and tests.
- Normal must not import Experimental business logic from `millikan_ai.api`, `pipeline`, `tracking`, `segments`, `physics`, `elementary`, or `downstream` when that logic encodes the multi-drop / multi-platform route. If Normal needs similar behavior, reimplement or copy the minimum algorithm into `millikan_ai.normal` with Normal names and Normal tests.
- Shared low-level, side-effect-free utilities may be used only when they are not Experimental business workflow code, such as basic video metadata reading, JSON helpers, or simple physical constants. When in doubt, duplicate the small code path inside `millikan_ai.normal`.
- Worker operation names must make the separation visible. Use `normal.*` for Normal and keep existing `analysis.*`, `platform.*`, and `downstream.*` operations for Experimental/current backend behavior.
- Frontend routes/components must make the separation visible. The startup screen can choose `Normal` or `Experimental`; after selection, the workflows should not share mutable state or silently hand off results to each other.
- v3 Normal branches are failed worktrees. They may be consulted only for visual inspiration and failure evidence, not used as an implementation blueprint.
- Normal state transitions are part of the contract. Frontend `video_imported` is local UI state after pure inspect. Backend `active_video.state` is limited to video-level states `video_prepared`, `boundary_confirmed`, `target_selected`, and `tracking`; it must never be set to a record status. Record `status` owns post-tracking states `pending_crossing_review`, `pending_user_confirmation`, `accepted`, `diagnostic`, `rejected_crossing_identity`, and `rejected_by_user`. Worker ops must enforce predecessor states, not rely only on disabled frontend buttons.
- `normal.inspectVideo` must stay pure: return metadata and a playable URL only. It must not create or mutate a session and must not run `0 V`, grid, tracking, or q calculation. `normal.prepareVideo` starts the expensive preparation after the user clicks start and emits Normal-only progress events.

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
- Before implementing a Normal/Experimental contract change, update `AGENTS.md`, `docs/frontend_backend_interface.md`, and the relevant design docs first. Code should then implement the documented contract rather than inventing a new one mid-edit.
- Desktop worker IPC is newline-delimited JSON encoded as UTF-8 without BOM. The Python worker must configure UTF-8 standard streams, Electron must launch it with `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`, and Node must decode stdout/stderr with a streaming UTF-8 decoder so a multibyte Chinese character split across chunks cannot become `�`.
- User-visible text, exported Markdown, JSON, CSV, source files, and documentation must not contain Unicode replacement characters or known UTF-8/legacy-codepage mojibake. Encoding regression tests must cover Chinese progress labels, Chinese error messages, scientific symbols, superscripts, and paths containing Chinese characters.
- Version `1.0.0` documentation is organized under `docs/technical/`, `docs/academic/`, and `docs/archive/`. Current contracts belong in technical or academic documents; superseded long-form designs remain available only as clearly marked historical material under `docs/archive/`.
- The root `README.md` is an English user-facing project showcase. It should lead with the working product, real packaged-app screenshots, operation guidance, honest build history, team contributions, and scientific boundaries. Detailed APIs, implementation contracts, and derivations belong in `docs/`.
- A formal release is complete only after the full Python and frontend suites, TypeScript build, worker build, Electron packaging, packaged-worker UTF-8 probe, packaged EXE launch, README link/image checks, checksum generation, final `main` verification, tag creation, and GitHub Release asset verification.
- Normal UI uses seconds for all user-facing time controls. Frame indices may be stored internally and in artifacts, but users adjust `0V_start_s` and `0V_end_s` with coarse `±1 s` and fine `±0.1 s` controls.
- Normal video import must support both file dialog selection and drag-and-drop. After import, the UI must display fps, frame count, resolution, and duration.
- Normal measures one user-selected droplet at a time. It must copy/reimplement the teammate local Trackpy single-drop algorithm from `C:\Users\Teddy\Desktop\追踪`; do not directly import that external project.
- Normal automatically detects horizontal grid lines and treats the region from the second line to the penultimate line as the effective measurement region.
- Normal crossing review must create clickable crossing events when tracking passes through or is interrupted near grid lines. The UI should show a local magnified review around roughly one second before and after the event, clipped to available video bounds. Do not show an empty or unplayable video control as if it were valid evidence; if packaged Chromium cannot reliably decode the generated clip, expose backend-generated review frames and play them in the renderer.
- Normal sessions are transient per application launch. `normal.initialize` without an explicit `session_root` must create a fresh session and must not reload old `runs/normal_session` records. Within one launch, a session may accumulate q records across multiple videos. Long-term retention happens only through explicit export, and the Electron shell must clean implicit transient session roots on application exit. At least three user-kept valid q records are required before Normal blind inversion.
- After a user accepts a Normal q record, the UI must offer a clear "next droplet" action. Choosing the same video must call a Normal worker operation that resets `active_video.state` to `boundary_confirmed` while preserving the confirmed boundary and video context; do not only change the frontend stage. Choosing a different video clears `active_video` and returns to the empty import state while preserving accepted records in the current transient session for cross-video inversion.
- Normal record review must show a renderer-playable whole-trajectory view. The backend should generate full-frame review images from the original video with target/missing labels, the trajectory line, frame/time, and pixel axes drawn in video pixel coordinates. The frontend may play those frames but must not redraw or infer track coordinates.
- Normal blind inversion must have its own final results stage/page after `normal.runInversion`. Do not leave the user on the per-drop measurement panel with only a toast or a few inline fields. The page must show `e_hat_C`, `sigma_e_C`, used q count, status, flags, sorted candidate solutions, integer assignments, per-drop residuals, and charted quantized-alignment diagnostics from the Normal inversion payload. It must not call Experimental elementary-estimator UI/business logic, and it must not claim a quantized/continuous model winner while the Normal continuous baseline is not fitted.
- Normal inversion must return a backend-computed `reference_comparison` using the exact SI defining constant `1.602176634e-19 C`. It includes relative uncertainty and absolute percentage error versus that reference. These display diagnostics must never influence the blind search, candidate ranking, integer assignments, or reliability flags.
- User-visible scientific notation across Normal and Experimental must use readable typography such as `1.602 × 10⁻¹⁹ C`; do not expose JavaScript/Python `1.602e-19` strings in UI labels, tables, charts, or Markdown reports. Charge and charge-uncertainty displays should use the shared `10⁻¹⁹ C` scale unless a different unit is explicitly required. Machine JSON/CSV values remain numeric SI values.
- Normal Stage 5 must expose an inspectable q-calculation evidence flow below the track review. Formula values must come from the backend record's fit/q calculation trace. The renderer may format and arrange those values but must not independently recompute radius, effective viscosity, q, or sigma_q.
- Normal Stage 6 has one canonical result summary in the main content area. The inspector is for convergence, search-boundary, flags, scientific limitations, export, and navigation; it must not duplicate the main `e_hat_C`/`sigma_e_C` result card.
- Normal rejected/diagnostic records remain visible in the current session as adjustment evidence. A user "return/adjust" action must not simply hide or discard the record; it must restore the relevant boundary/target/voltage/parameter inputs so the user can micro-adjust and retrack, producing a new linked record.
- Normal target selection time must be constrained to the user-confirmed `0V_start_s ± 0.5 s`, not anywhere in the video and not relative to the auto suggestion after the user edits it. The backend must reject target times outside this window, and the frontend must clamp second-based controls to the same window.
- Normal target selection preview is the main video player itself, paused at `selection_time_s`. Do not add a separate screenshot preview as a substitute. The frame displayed in the main player, the frontend `selectionTime`, and the backend `target_frame` must describe the same frame.
- After `normal.confirmBoundary`, the frontend must reset `selectionTime` to the backend-confirmed `zero_v_start_s` and recompute the target-selection window from that confirmed boundary. User edits to `0V_start_s`/`0V_end_s` must discard any stale `selection_window` inherited from an earlier boundary.
- `normal.confirmBoundary` is a second-based user-confirmation API. If a payload contains both seconds and stale frame indices, the seconds are authoritative and the backend must recompute frame indices from them.
- Normal return/adjust must restore the exact user-confirmed boundary snapshot from the relevant in-progress state or record. It must not fall back to the original automatic suggestion, and it must not use `active_video.adjustment` for a different record id.
- Normal stages must be reversible. A user can return to the previous stage and continue from the last user-confirmed state. When an upstream state changes, strongly dependent downstream state must be cleared or regenerated: boundary changes invalidate target/tracking/review/q candidate state; target/time/box changes invalidate tracking/review/q candidate state. Existing records remain immutable evidence unless the user explicitly excludes them.
- In Normal, balance voltage is required. Other physical parameters should default from config and be editable in a collapsed advanced panel; overrides apply only to the current measurement record unless the user explicitly changes saved defaults.
- Normal physical pressure is `pressure_kPa` in the Normal contract. Do not expose or persist new Normal records with `pressure_Pa`; convert legacy overrides only at the boundary. Normal q uncertainty must come from linear-regression slope uncertainty and q(v) propagation. Do not use the old RMSE/R2 empirical formula or a q-level 5% floor for `sigma_q_C`.
- Normal must use its own weighted integer residual grid-search inversion over q records with uncertainties. Do not call the Experimental elementary estimator as a shortcut.
- Normal inversion must include fixed-integer weighted re-estimation of `e`, assignment-stability iteration, sorted candidate solutions, boundary/convergence flags, and residual details. Without a fitted continuous baseline, do not output `quantized_favored`, `continuous_favored`, or any model-win claim.
- Current `develop`/`main` does not run voltage OCR. It may auto-detect voltage-platform boundaries from visual display changes, but voltage values remain user/API supplied. OCR experiment code is preserved on `feature/ocr-current-archive`; do not re-enable OCR on mainline without an explicit new plan.
- Auto platform detection uses the user-provided expected platform count as a validation constraint. Rejected suggestions, short platforms, or count mismatches must fall back to manual boundary input rather than silently entering q calculation.
- If ROI detection or tracking confidence is low, write explicit flags and allow manual/config-driven correction.
- Do not claim a trained ML filter is implemented. The runtime adapter must report `mode=mock_rule_adapter`, `trained=false`.
- Do not silently output physical results when fewer than two usable voltage platforms exist.
- Single-drop physics uses the fixed convention `+Y` downward and positive voltage pushing droplets upward, fitting `v = alpha - gamma U`. Cunningham radius solving uses the closed-form positive root, not fixed-point iteration.
- Physical q results must not invent a fixed `quality_score`; downstream diagnostics and the quality adapter may report adapter scores separately.
- Scientific validation for downstream physics/e estimation uses synthetic accepted-trajectory fixtures with known truth. Do not use raw videos as scientific validation for elementary charge on this branch.
- On `feature/downstream-physics-elementary`, do not modify tracker, optical-flow, Kalman, detection, trajectory stitching, or upstream filtering algorithms. Teacher's grid-avoidance idea is an upstream research direction for docs/interface assumptions only on this branch.
- Current downstream inputs are already accepted trajectories. Future upstream may provide the longest continuous segment that avoids grid-line neighborhoods, but this branch must not implement or require a new stitching API.
- Standalone downstream analysis starts after trajectory extraction and upstream trajectory filtering. Every mathematically successful q enters elementary-charge estimation; only computation failures are excluded.
- A formal successful q requires finite positive radius, finite positive charge, and finite positive random q uncertainty from joint alpha/gamma Monte Carlo or an explicit analytic fallback. Point estimates with missing uncertainty are `point_estimate_only`, are reported as partial/failures, and do not enter the e probability model.
- Shared systematic uncertainty belongs in the standalone downstream path: sample one common physical-parameter draw across all drops, while treating per-drop random q errors independently.
- Shared systematic uncertainty must be propagated to final e by recomputing all q values for each shared draw and rerunning the elementary-charge estimator on that draw.
- The elementary estimator's main `e_hat_C` is the global maximum of the bounded profile likelihood. Harmonic/divisor modes are diagnostics only and must not override the main estimate.
- Elementary-charge estimation is a predeclared bounded inversion over the fixed internal interval `[1.35e-19, 1.90e-19] C`. Do not expose this interval as user-editable config/CLI/UI state; old `e_search_min_C/e_search_max_C` keys must not change the actual interval and should be reported as ignored provenance.
- `elementary_charge_result.json.valid` is a legacy numeric-fit compatibility field. Use `fundamental_spacing_identified` for the final scientific conclusion, and propagate that field to `run_manifest.status.valid_for_elementary_charge` and `validity_report.overall_valid_for_elementary_charge`.
- A bounded candidate is not identified when evidence is uncalibrated, the profile hits the fixed-prior boundary, optimized profile coverage is incomplete, high-confidence integer assignments are non-primitive, or bootstrap/measurement-MC mode stability fails. Profile optimization is incomplete if a required nuisance-parameter candidate cannot be optimized after retries or if an important local profile mode is omitted by `max_profile_modes_to_optimize`.
- `scripts/validate_estimator_simulation.py` is the slow synthetic validation harness for e bias, interval coverage, continuous-data false positives, N/noise behavior, and harmonic ambiguity. It must not use raw videos.
- `analysis_report.md` is the user-facing report for the selected/default drop plus any configured multi-drop outputs; CSV/JSON/MP4 files remain the machine-readable contract.
- Single-drop elementary-charge estimation must report insufficient independent drops rather than inventing `e_hat`.
- Platform velocity fitting in the downstream scientific path fits the full provided constant-voltage platform, optionally trimming only `segment.boundary_guard_frames`; do not restore fixed transient trimming or highest-R2 sub-window selection.
- Candidate tracking and segment validation must reject stationary grid/bright-spot candidates using `segment.min_motion_displacement_px`.
- Tracking must process each video frame once for shared preprocessing across active Trackpy single-drop states. Each active state should run only a local Trackpy search around its predicted point; do not re-read the full video per candidate.
- Candidate tracking must stay inside the detected grid/tracking ROI so watermarks, manufacturer text, and border highlights are not eligible droplets.
- Trackpy multi-drop tracking uses the teammate single-drop local search and velocity extrapolation as the base. Do not replace it with a new global MOT/Hungarian tracker without a separate plan.
- Grid-line neighborhoods are unreliable regions. When a predicted droplet enters the grid mask safety band, cut the current segment with `end_reason=grid_occlusion`, preserve prior reliable points, and do not automatically reconnect across the grid.
- Candidate ranking should penalize candidates too close to grid lines or tracking ROI edges using `tracking.min_grid_line_distance_px`, `tracking.min_grid_clear_fraction`, `tracking.min_tracking_roi_margin_px`, and `tracking.min_roi_clear_fraction`.
- CLI manual platform inputs use `--platform START_FRAME:END_FRAME:VOLTAGE`; generated configs are written under `runs/manual_configs/` and platforms use `source=manual_cli`. Auto-boundary runs use `--auto-platform-count N` plus repeated `--platform-value V` and write platform rows with `source=auto_boundary_manual_voltage`.
- `run_manifest.json` is the frontend-facing machine-readable entry point for a completed run. Keep it stable and update `docs/frontend_backend_interface.md` when adding/removing output artifacts or panel contracts.
- `plots_data.json` is the frontend-facing elementary-charge chart-data contract. It must stay renderer-neutral: no PNG/SVG/HTML/Plotly/ECharts options, only schema-versioned data, units, chart semantics, and recommended rendering hints.
- `validity_report.json` is the frontend-facing legality/reasonableness checklist. Add explicit checks there when adding new q, tracking, or multi-drop prerequisites.
- `visualization_layers.json` is the frontend-facing structured drawing contract. Prefer adding reusable layer objects there over encoding new UI-only information only in rendered images.
- `diagnostic_overlay.jpg` is the frontend-facing static visualization contract: it should show pixel `+X/+Y`, microscope ROI, tracking ROI, grid lines, measurement lines, selected droplet, and trajectory. Keep `docs/frontend_backend_interface.md` in sync when this contract changes.
- Multi-drop tracking defaults to the safety cap `tracking.max_drops: 20`; preserve the selected/default drop files for compatibility.
- Elementary-charge estimation consumes every successfully computed `q_valid=true` drop. The mock quality adapter is diagnostic/frontend-facing and must not be a second gate for e estimation.
- Keep the backend CPU-only. GPU/OpenCV CUDA work requires a separately approved dependency plan.
- `candidate_tracks_summary.csv` may include post-physics columns such as `drop_id`, `q_valid`, `physics_flags`, `charge_abs_C`, and `radius_m`. Treat `selected_for_multi_drop=true` as "tracked for evaluation"; use `q_valid=true` or `multi_drop_results.valid_drop_count` for physically valid droplets.
- The selected/default drop should prefer the highest-ranked `q_valid=true` result. Do not use tracking rank alone when a lower-ranked selected candidate has a valid q and the top candidate is physically invalid.
- Segment rows for short or transient-cropped platforms must preserve the source `track_id`; blank `track_id` rows in `drop_track_segments.csv` can create fake drops in `multi_drop_results.json`.
