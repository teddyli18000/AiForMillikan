from __future__ import annotations

import cv2
import numpy as np


def _local_patch(
    image: np.ndarray,
    point: tuple[float, float],
    radius_px: int,
) -> tuple[np.ndarray, tuple[int, int], tuple[float, float]] | None:
    height, width = image.shape[:2]
    x, y = float(point[0]), float(point[1])
    if x < 0 or y < 0 or x >= width or y >= height:
        return None
    x0 = max(0, int(np.floor(x - radius_px)))
    y0 = max(0, int(np.floor(y - radius_px)))
    x1 = min(width, int(np.ceil(x + radius_px + 1)))
    y1 = min(height, int(np.ceil(y + radius_px + 1)))
    if x1 <= x0 or y1 <= y0:
        return None
    return image[y0:y1, x0:x1], (x0, y0), (x - x0, y - y0)


class KalmanPointTracker:
    def __init__(
        self,
        x_px: float,
        y_px: float,
        *,
        dt: float,
        process_noise: float = 1.0,
        measurement_noise: float = 2.0,
    ) -> None:
        self._filter = cv2.KalmanFilter(4, 2)
        self._filter.measurementMatrix = np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0]],
            dtype=np.float32,
        )
        self._filter.processNoiseCov = np.eye(4, dtype=np.float32) * float(process_noise)
        self._filter.measurementNoiseCov = np.eye(2, dtype=np.float32) * float(measurement_noise)
        self._filter.errorCovPost = np.eye(4, dtype=np.float32) * 100.0
        self._filter.statePost = np.array([[x_px], [y_px], [0.0], [0.0]], dtype=np.float32)
        self._filter.statePre = self._filter.statePost.copy()
        self._set_dt(dt)
        self._dt = max(float(dt), 1e-6)
        self._predicted_position = np.array([x_px, y_px], dtype=np.float32)
        self._has_prediction = False
        self._last_measurement = np.array([x_px, y_px], dtype=np.float32)
        self._velocity_initialized = False

    def _set_dt(self, dt: float) -> None:
        dt = max(float(dt), 1e-6)
        self._dt = dt
        self._filter.transitionMatrix = np.array(
            [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]],
            dtype=np.float32,
        )

    def predict(self, dt: float | None = None) -> tuple[float, float]:
        if dt is not None:
            self._set_dt(dt)
        state = self._filter.predict()
        self._predicted_position = state[:2, 0].copy()
        self._has_prediction = True
        return float(state[0, 0]), float(state[1, 0])

    def correct(self, point: tuple[float, float]) -> tuple[float, float]:
        if not self._has_prediction:
            self._filter.statePost[0, 0] = float(point[0])
            self._filter.statePost[1, 0] = float(point[1])
            self._filter.statePre = self._filter.statePost.copy()
            self._predicted_position = np.asarray(point, dtype=np.float32)
            return float(point[0]), float(point[1])
        measurement = np.array([[point[0]], [point[1]]], dtype=np.float32)
        state = self._filter.correct(measurement)
        current_measurement = measurement[:, 0]
        if not self._velocity_initialized:
            velocity = (current_measurement - self._last_measurement) / self._dt
            self._filter.statePost[2:, 0] = velocity
            state = self._filter.statePost
            self._velocity_initialized = True
        self._last_measurement = current_measurement.copy()
        self._has_prediction = False
        return float(state[0, 0]), float(state[1, 0])

    def mahalanobis_distance(self, point: tuple[float, float]) -> float:
        innovation = np.asarray(point, dtype=np.float64) - self._predicted_position.astype(np.float64)
        covariance = self._filter.measurementMatrix @ self._filter.errorCovPre @ self._filter.measurementMatrix.T
        covariance = covariance + self._filter.measurementNoiseCov
        try:
            inverse = np.linalg.inv(covariance.astype(np.float64))
        except np.linalg.LinAlgError:
            return float("inf")
        squared = float(innovation.T @ inverse @ innovation)
        return float(np.sqrt(max(0.0, squared)))


def track_lk_bidirectional(
    previous_gray: np.ndarray,
    current_gray: np.ndarray,
    point: tuple[float, float],
    *,
    window_size_px: int = 21,
    pyramid_levels: int = 3,
    max_forward_backward_error_px: float = 1.5,
    max_photometric_error: float = 30.0,
) -> tuple[tuple[float, float], float] | None:
    patch_radius = max(int(window_size_px) * max(2, int(pyramid_levels)), int(window_size_px) + 8)
    patch = _local_patch(previous_gray, point, patch_radius)
    if patch is None:
        return None
    previous_patch, offset, local_point = patch
    x0, y0 = offset
    current_patch = current_gray[y0 : y0 + previous_patch.shape[0], x0 : x0 + previous_patch.shape[1]]
    if current_patch.shape != previous_patch.shape or min(current_patch.shape[:2]) < max(3, int(window_size_px)):
        return None
    previous_point = np.array([[[local_point[0], local_point[1]]]], dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
    options = {
        "winSize": (int(window_size_px), int(window_size_px)),
        "maxLevel": int(pyramid_levels),
        "criteria": criteria,
    }
    forward, forward_status, forward_error = cv2.calcOpticalFlowPyrLK(
        previous_patch,
        current_patch,
        previous_point,
        None,
        **options,
    )
    if forward is None or forward_status is None or not bool(forward_status[0, 0]):
        return None
    backward, backward_status, _ = cv2.calcOpticalFlowPyrLK(
        current_patch,
        previous_patch,
        forward,
        None,
        **options,
    )
    if backward is None or backward_status is None or not bool(backward_status[0, 0]):
        return None
    if forward_error is not None and float(forward_error[0, 0]) > max_photometric_error:
        return None
    forward_xy = forward[0, 0].astype(np.float64)
    backward_xy = backward[0, 0].astype(np.float64)
    if not np.isfinite(forward_xy).all() or not np.isfinite(backward_xy).all():
        return None
    forward_backward_error = float(np.linalg.norm(backward_xy - previous_point[0, 0]))
    if forward_backward_error > max_forward_backward_error_px:
        return None
    return (float(forward_xy[0] + x0), float(forward_xy[1] + y0)), forward_backward_error
