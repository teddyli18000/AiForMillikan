from __future__ import annotations

import cv2
import numpy as np

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.tracking.detector import detect_blobs


def _grid() -> GridCalibration:
    return GridCalibration(
        roi=Roi(0, 0, 200, 160),
        grid_lines_x=[50, 150],
        grid_lines_y=[40, 120],
        x_start_px=50,
        x_end_px=150,
        y_start_px=40,
        y_end_px=120,
        measurement_distance_m=0.0015,
        scale_y_m_per_px=0.0015 / 80,
        warnings=[],
    )


def test_detector_ranks_isolated_droplets_and_suppresses_grid_and_edges():
    frame = np.zeros((160, 200, 3), dtype=np.uint8)
    cv2.line(frame, (0, 40), (199, 40), (170, 170, 170), 2)
    cv2.circle(frame, (90, 80), 4, (255, 255, 255), -1)
    cv2.circle(frame, (120, 92), 4, (220, 220, 220), -1)
    cv2.circle(frame, (85, 41), 4, (255, 255, 255), -1)
    cv2.circle(frame, (4, 75), 4, (255, 255, 255), -1)

    blobs = detect_blobs(
        frame,
        Roi(0, 0, 200, 160),
        min_area=3,
        max_area=180,
        grid=_grid(),
        min_grid_distance_px=6,
        min_roi_margin_px=8,
        nms_distance_px=6,
    )

    assert len(blobs) == 2
    assert blobs[0].confidence >= blobs[1].confidence
    assert abs(blobs[0].x_px - 90) <= 1
    assert all(abs(blob.y_px - 40) >= 6 for blob in blobs)
    assert all(blob.x_px >= 8 for blob in blobs)
