from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from millikan_ai.calibration.grid import Roi


@dataclass(frozen=True)
class Blob:
    x_px: float
    y_px: float
    radius_px: float
    area_px: float
    brightness: float


def detect_blobs(frame: np.ndarray, roi: Roi, min_area: float, max_area: float) -> list[Blob]:
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
        radius = (area / np.pi) ** 0.5
        brightness = float(gray[y : y + h, x : x + w].mean())
        blobs.append(Blob(cx, cy, radius, area, brightness))
    return blobs

