from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Roi:
    x: int
    y: int
    w: int
    h: int

    @classmethod
    def from_config(cls, value: list[int] | tuple[int, int, int, int] | None) -> "Roi | None":
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("ROI must be [x, y, w, h]")
        return cls(*(int(v) for v in value))

    def crop(self, image: np.ndarray) -> np.ndarray:
        return image[self.y : self.y + self.h, self.x : self.x + self.w]

    def to_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]


@dataclass(frozen=True)
class GridCalibration:
    roi: Roi
    grid_lines_y: list[int]
    y_start_px: int | None
    y_end_px: int | None
    measurement_distance_m: float
    scale_y_m_per_px: float | None
    warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "roi": self.roi.to_list(),
            "grid_lines_y": self.grid_lines_y,
            "y_start_px": self.y_start_px,
            "y_end_px": self.y_end_px,
            "measurement_distance_m": self.measurement_distance_m,
            "scale_y_m_per_px": self.scale_y_m_per_px,
            "warnings": self.warnings,
        }


def default_voltage_roi(width: int, height: int) -> Roi:
    return Roi(int(width * 0.62), 0, int(width * 0.24), int(height * 0.10))


def auto_microscope_roi(frame: np.ndarray) -> Roi:
    height, width = frame.shape[:2]
    search_x0 = int(width * 0.05)
    search_y0 = int(height * 0.10)
    search_x1 = int(width * 0.78)
    search_y1 = int(height * 0.97)
    search = frame[search_y0:search_y1, search_x0:search_x1]
    gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 95, 255, cv2.THRESH_BINARY)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 3))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 35))
    grid_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_h) | cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_v)
    points = cv2.findNonZero(grid_mask)
    if points is None:
        return Roi(int(width * 0.12), int(height * 0.08), int(width * 0.62), int(height * 0.84))
    x, y, w, h = cv2.boundingRect(points)
    pad = 12
    x = max(0, search_x0 + x - pad)
    y = max(0, search_y0 + y - pad)
    w = min(width - x, w + 2 * pad)
    h = min(height - y, h + 2 * pad)
    if w < width * 0.30 or h < height * 0.30:
        return Roi(int(width * 0.12), int(height * 0.08), int(width * 0.62), int(height * 0.84))
    return Roi(x, y, w, h)


def detect_horizontal_grid_lines(image: np.ndarray, min_distance_px: int = 25) -> list[int]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 3))
    horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, horizontal_kernel)
    projection = horizontal.mean(axis=1)
    if projection.max(initial=0) <= 0:
        return []
    threshold = max(12.0, float(projection.max()) * 0.28)
    ys = np.where(projection >= threshold)[0]
    if len(ys) == 0:
        return []
    groups: list[list[int]] = [[int(ys[0])]]
    for y in ys[1:]:
        if int(y) - groups[-1][-1] <= 3:
            groups[-1].append(int(y))
        else:
            groups.append([int(y)])
    centers = [int(round(sum(group) / len(group))) for group in groups]
    merged: list[int] = []
    for y in centers:
        if not merged or y - merged[-1] >= min_distance_px:
            merged.append(y)
        else:
            merged[-1] = int(round((merged[-1] + y) / 2))
    return merged


def calibrate_grid(
    frame: np.ndarray,
    microscope_roi: Roi | None,
    measurement_distance_m: float,
    min_grid_lines: int = 4,
) -> GridCalibration:
    roi = microscope_roi or auto_microscope_roi(frame)
    crop = roi.crop(frame)
    local_lines = detect_horizontal_grid_lines(crop)
    global_lines = [roi.y + y for y in local_lines]
    warnings: list[str] = []
    y_start = y_end = None
    scale = None
    if len(global_lines) < min_grid_lines:
        warnings.append("too_few_grid_lines")
    else:
        y_start = global_lines[1]
        y_end = global_lines[-2]
        pixel_span = abs(y_end - y_start)
        if pixel_span <= 0:
            warnings.append("invalid_grid_span")
        else:
            scale = measurement_distance_m / pixel_span
    return GridCalibration(roi, global_lines, y_start, y_end, measurement_distance_m, scale, warnings)
