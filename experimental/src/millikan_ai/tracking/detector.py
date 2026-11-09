from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from millikan_ai.calibration.grid import GridCalibration, Roi


@dataclass(frozen=True)
class Blob:
    x_px: float
    y_px: float
    radius_px: float
    area_px: float
    brightness: float
    contrast: float = 0.0
    circularity: float = 0.0
    confidence: float = 0.0


def _near_grid_line(x_px: float, y_px: float, grid: GridCalibration | None, min_distance_px: float) -> bool:
    if grid is None or min_distance_px <= 0:
        return False
    distances = [abs(x_px - float(x)) for x in grid.grid_lines_x]
    distances.extend(abs(y_px - float(y)) for y in grid.grid_lines_y)
    return bool(distances and min(distances) < min_distance_px)


def _near_roi_edge(x_px: float, y_px: float, roi: Roi, min_margin_px: float) -> bool:
    if min_margin_px <= 0:
        return False
    return min(x_px - roi.x, roi.x + roi.w - x_px, y_px - roi.y, roi.y + roi.h - y_px) < min_margin_px


def _suppress_nearby(blobs: list[Blob], min_distance_px: float) -> list[Blob]:
    if min_distance_px <= 0:
        return blobs
    kept: list[Blob] = []
    for blob in blobs:
        if all(np.hypot(blob.x_px - other.x_px, blob.y_px - other.y_px) >= min_distance_px for other in kept):
            kept.append(blob)
    return kept


def detect_blobs(
    frame: np.ndarray,
    roi: Roi,
    min_area: float,
    max_area: float,
    *,
    grid: GridCalibration | None = None,
    min_grid_distance_px: float = 0.0,
    min_roi_margin_px: float = 0.0,
    nms_distance_px: float = 0.0,
) -> list[Blob]:
    crop = roi.crop(frame)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    background = cv2.medianBlur(gray, 21)
    enhanced = cv2.subtract(gray, background)
    _, mask = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs: list[Blob] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area or area > max_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if max(w, h) / max(min(w, h), 1) > 3.0:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        cx = roi.x + moments["m10"] / moments["m00"]
        cy = roi.y + moments["m01"] / moments["m00"]
        if _near_grid_line(cx, cy, grid, min_grid_distance_px) or _near_roi_edge(cx, cy, roi, min_roi_margin_px):
            continue
        radius = (area / np.pi) ** 0.5
        brightness = float(gray[y : y + h, x : x + w].mean())
        contrast = float(enhanced[y : y + h, x : x + w].mean())
        perimeter = float(cv2.arcLength(contour, True))
        circularity = float(4 * np.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0
        contrast_score = min(1.0, max(0.0, contrast / 255.0))
        circularity_score = min(1.0, max(0.0, circularity))
        area_midpoint = (min_area + max_area) / 2
        area_half_range = max((max_area - min_area) / 2, 1.0)
        area_score = max(0.0, 1.0 - abs(area - area_midpoint) / area_half_range)
        confidence = 0.55 * contrast_score + 0.35 * circularity_score + 0.10 * area_score
        blobs.append(Blob(cx, cy, radius, area, brightness, contrast, circularity, confidence))
    blobs.sort(key=lambda blob: blob.confidence, reverse=True)
    return _suppress_nearby(blobs, nms_distance_px)

