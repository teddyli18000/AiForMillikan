# AGENTS.md

## Project Context

This project analyzes Millikan oil drop experiment videos. The current backend is a Python package with a CLI MVP that should remain suitable for later PySide6/Qt desktop integration.

## Module Boundaries

- `src/millikan_ai/video/`: OpenCV video metadata, frame sampling, and diagnostic frames.
- `src/millikan_ai/calibration/`: screen/ROI/grid calibration and physical scale estimation.
- `src/millikan_ai/ocr/`: local OpenCV/template voltage OCR; no Tesseract or deep OCR dependency.
- `src/millikan_ai/tracking/`: non-ML droplet candidate detection, single-target tracking, scoring, and overlay rendering.
- `src/millikan_ai/segments/`: voltage platform segmentation and terminal velocity fitting.
- `src/millikan_ai/physics/`: physics-based single-drop charge inversion.
- `src/millikan_ai/elementary/`: non-ML elementary charge estimation from computed drop results.
- `training_quality_filter/`: future ML/unsupervised trajectory quality filtering subsystem. Do not implement ML filtering in the main backend.

## Raw Data

`raw_data/` contains local smoke-test videos:

- `single.mp4`: one droplet with no voltage change; useful for inspect and failure-path testing.
- `2u.mp4`: two-voltage experiment video.
- `3u1.mp4`, `3u2.mp4`: three-voltage experiment videos.

## Commands

Use the local virtual environment:

```powershell
.venv\Scripts\python -m pytest tests -q --basetemp runs\pytest_tmp -o cache_dir=runs\pytest_cache
.venv\Scripts\python -m millikan_ai.cli inspect raw_data\single.mp4
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --platform 0:180:0 --platform 181:468:175
```

All project dependencies must stay inside the project-local `.venv/`. Do not install Python packages globally or into the user's base Conda environment.

## Current Implementation Rules

- All thresholds and physical constants should come from `configs/default.yaml`.
- If OCR, ROI detection, or tracking confidence is low, write explicit flags and allow manual/config-driven correction.
- Do not claim ML-based trajectory filtering is implemented in this stage.
- Do not silently output physical results when fewer than two usable voltage platforms exist.
- `analysis_report.md` is the user-facing single-drop report; CSV/JSON/MP4 files remain the machine-readable contract.
- Single-drop elementary-charge estimation must report insufficient independent drops rather than inventing `e_hat`.
- Platform velocity fitting should use the best stable sub-window inside each voltage platform, not blindly fit the whole platform.
- Candidate tracking and segment validation must reject stationary grid/bright-spot candidates using `segment.min_motion_displacement_px`.
- CLI manual platform inputs use `--platform START_FRAME:END_FRAME:VOLTAGE`; generated configs are written under `runs/manual_configs/` and platforms use `source=manual_cli`.
