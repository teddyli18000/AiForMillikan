from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


def calibrate_grid(video_path: str | Path, cfg: dict[str, Any], start_frame: int = 0, end_frame: int | None = None) -> dict[str, Any]:
    gcfg = cfg["grid"]
    samples = _sample_frames(video_path, int(gcfg.get("sample_frames", 48)), int(gcfg.get("sample_stride", 3)), start_frame, end_frame)
    background = np.median(np.stack(samples, axis=0), axis=0).astype(np.uint8)
    gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    lines_y = detect_horizontal_lines(gray, gcfg)
    warnings: list[str] = []
    if len(lines_y) < 4:
        warnings.append("grid_lines_insufficient")
        return {"valid": False, "grid_lines_y": lines_y, "warnings": warnings}
    second = int(lines_y[1])
    penultimate = int(lines_y[-2])
    span = penultimate - second
    if span <= 0:
        warnings.append("grid_span_invalid")
        return {"valid": False, "grid_lines_y": lines_y, "warnings": warnings}
    scale = float(gcfg.get("measurement_distance_m", 0.0015)) / float(span)
    mask = build_grid_mask(gray, lines_y, int(gcfg.get("mask_dilate_px", 5)))
    return {
        "valid": True,
        "grid_lines_y": lines_y,
        "second_line_y": second,
        "penultimate_line_y": penultimate,
        "scale_y_m_per_px": scale,
        "measurement_distance_m": float(gcfg.get("measurement_distance_m", 0.0015)),
        "warnings": warnings,
        "mask_coverage": float(np.count_nonzero(mask) / mask.size),
    }


def detect_horizontal_lines(gray: np.ndarray, cfg: dict[str, Any]) -> list[int]:
    eq = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    edges = cv2.Canny(eq, 40, 120)
    width = gray.shape[1]
    kernel_len = max(20, int(width * float(cfg.get("min_horizontal_coverage", 0.45))))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1))
    horiz = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel)
    projection = np.count_nonzero(horiz, axis=1)
    if projection.max(initial=0) <= 0:
        return []
    threshold = max(5, int(projection.max() * 0.35))
    ys = np.where(projection >= threshold)[0].tolist()
    return _merge_positions(ys, int(cfg.get("line_merge_px", 5)))


def build_grid_mask(gray: np.ndarray, lines_y: list[int], dilate_px: int) -> np.ndarray:
    mask = np.zeros_like(gray, dtype=np.uint8)
    for y in lines_y:
        cv2.line(mask, (0, int(y)), (gray.shape[1] - 1, int(y)), 255, 2)
    if dilate_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def _merge_positions(values: list[int], distance: int) -> list[int]:
    if not values:
        return []
    groups: list[list[int]] = [[values[0]]]
    for value in values[1:]:
        if value - groups[-1][-1] <= distance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [int(round(float(np.mean(group)))) for group in groups]


def _sample_frames(video_path: str | Path, count: int, stride: int, start_frame: int, end_frame: int | None) -> list:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    start = max(0, int(start_frame))
    end = min(frame_count - 1, int(end_frame) if end_frame is not None else frame_count - 1)
    frames = []
    for frame_idx in range(start, end + 1, max(1, stride)):
        if len(frames) >= count:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    if not frames:
        raise RuntimeError("no grid sample frames")
    return frames

