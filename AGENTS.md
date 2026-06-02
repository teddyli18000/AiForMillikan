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
.venv\Scripts\python -m pytest tests
.venv\Scripts\python -m millikan_ai.cli inspect raw_data\single.mp4
.venv\Scripts\python -m millikan_ai.cli run --video raw_data\2u.mp4 --config configs\default.yaml --non-interactive
```

## Current Implementation Rules

- All thresholds and physical constants should come from `configs/default.yaml`.
- If OCR, ROI detection, or tracking confidence is low, write explicit flags and allow manual/config-driven correction.
- Do not claim ML-based trajectory filtering is implemented in this stage.
- Do not silently output physical results when fewer than two usable voltage platforms exist.

