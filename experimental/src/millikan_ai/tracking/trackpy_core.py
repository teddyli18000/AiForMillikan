from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
import pandas as pd
import trackpy as tp

from millikan_ai.calibration.grid import Roi
from millikan_ai.tracking import grid_mask as grid_mask_utils


@dataclass
class SingleDropTrackingConfig:
    diameter: int = 5
    invert: bool = False
    minmass: float = 80.0
    local_search_radius: float = 45.0
    max_accept_distance: float = 30.0
    single_memory: int = 5
    local_topn: int = 20
    grid_reject_dilate_px: int = 0
    grid_occlusion_radius: int = 0
    skip_detection_on_grid: bool = True
    max_jump_px: float = 0.0


def preprocess_frame_for_droplets(frame, grid_mask=None):
    gray_before_grid_removal = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if grid_mask is not None:
        gray = grid_mask_utils.remove_static_grid_from_gray(gray_before_grid_removal, grid_mask)
    else:
        gray = gray_before_grid_removal
    return cv2.GaussianBlur(gray, (3, 3), 0)


def _dilated_reject_mask(mask_crop: np.ndarray, config: SingleDropTrackingConfig) -> np.ndarray:
    reject_mask = np.where(mask_crop > 0, 255, 0).astype(np.uint8)
    if config.grid_reject_dilate_px > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * int(config.grid_reject_dilate_px) + 1, 2 * int(config.grid_reject_dilate_px) + 1),
        )
        reject_mask = cv2.dilate(reject_mask, kernel, iterations=1)
    return reject_mask


def _mask_grid_pixels(crop: np.ndarray, reject_mask: np.ndarray | None) -> None:
    if reject_mask is None or np.count_nonzero(reject_mask) == 0:
        return
    valid_pixels = crop[reject_mask == 0]
    fill_value = np.median(valid_pixels) if valid_pixels.size > 0 else np.median(crop)
    crop[reject_mask > 0] = np.uint8(fill_value)


def _reject_features_on_mask(features: pd.DataFrame, reject_mask: np.ndarray | None) -> pd.DataFrame:
    if reject_mask is None or features is None or len(features) == 0:
        return features
    keep_rows = []
    for _, row in features.iterrows():
        lx = int(round(row["x"]))
        ly = int(round(row["y"]))
        if 0 <= lx < reject_mask.shape[1] and 0 <= ly < reject_mask.shape[0]:
            keep_rows.append(reject_mask[ly, lx] == 0)
        else:
            keep_rows.append(False)
    return features.loc[keep_rows].copy()


def locate_features_near_position(
    gray,
    center,
    radius: float,
    config: SingleDropTrackingConfig,
    grid_mask=None,
):
    height, width = gray.shape[:2]
    cx, cy = center
    x0 = max(0, int(round(cx - radius)))
    y0 = max(0, int(round(cy - radius)))
    x1 = min(width, int(round(cx + radius + 1)))
    y1 = min(height, int(round(cy + radius + 1)))
    crop = gray[y0:y1, x0:x1].copy()
    if crop.shape[0] < config.diameter + 2 or crop.shape[1] < config.diameter + 2:
        return pd.DataFrame()

    reject_mask = None
    if grid_mask is not None:
        reject_mask = _dilated_reject_mask(grid_mask[y0:y1, x0:x1], config)
        _mask_grid_pixels(crop, reject_mask)

    features = tp.locate(
        crop,
        diameter=int(config.diameter),
        minmass=float(config.minmass),
        invert=bool(config.invert),
        topn=int(config.local_topn),
        characterize=True,
    )
    if features is None or len(features) == 0:
        return pd.DataFrame()
    features = features.copy()
    features.index = range(len(features))
    features = _reject_features_on_mask(features, reject_mask)
    if len(features) == 0:
        return pd.DataFrame()
    features["x"] = features["x"] + x0
    features["y"] = features["y"] + y0
    return features


def locate_features_in_roi(
    gray,
    roi: Roi,
    config: SingleDropTrackingConfig,
    grid_mask=None,
):
    crop = roi.crop(gray).copy()
    reject_mask = None
    if grid_mask is not None:
        reject_mask = _dilated_reject_mask(grid_mask[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w], config)
        _mask_grid_pixels(crop, reject_mask)
    features = tp.locate(
        crop,
        diameter=int(config.diameter),
        minmass=float(config.minmass),
        invert=bool(config.invert),
        topn=None,
        characterize=True,
    )
    if features is None or len(features) == 0:
        return pd.DataFrame()
    features = features.copy()
    features.index = range(len(features))
    features = _reject_features_on_mask(features, reject_mask)
    if len(features) == 0:
        return pd.DataFrame()
    features["x"] = features["x"] + roi.x
    features["y"] = features["y"] + roi.y
    return features


def choose_nearest_feature(features, predicted_position, max_distance: float):
    if features is None or len(features) == 0:
        return None
    features = features.copy()
    dx = features["x"] - predicted_position[0]
    dy = features["y"] - predicted_position[1]
    features["distance_to_prediction"] = np.sqrt(dx**2 + dy**2)
    nearest = features.sort_values("distance_to_prediction").iloc[0]
    if nearest["distance_to_prediction"] > max_distance:
        return None
    return nearest


def is_position_near_grid(position, grid_mask, radius: int) -> bool:
    if grid_mask is None:
        return False
    height, width = grid_mask.shape[:2]
    x, y = position
    x = int(round(x))
    y = int(round(y))
    radius = max(0, int(radius))
    x0 = max(0, x - radius)
    y0 = max(0, y - radius)
    x1 = min(width, x + radius + 1)
    y1 = min(height, y + radius + 1)
    if x0 >= x1 or y0 >= y1:
        return False
    return np.count_nonzero(grid_mask[y0:y1, x0:x1]) > 0


def track_single_droplet(
    frames,
    initial_position,
    config: SingleDropTrackingConfig,
    grid_mask=None,
    source_start_frame: int = 0,
) -> pd.DataFrame:
    rows = []
    search_center = initial_position.astype(float)
    last_detected_position = initial_position.astype(float)
    velocity = np.array([0.0, 0.0], dtype=float)
    missed_count = 0
    for frame_id, gray in enumerate(frames):
        if frame_id == 0:
            current_position = initial_position.astype(float)
            rows.append(
                {
                    "frame": frame_id,
                    "source_frame": int(source_start_frame) + int(frame_id),
                    "x": current_position[0],
                    "y": current_position[1],
                    "pred_x": current_position[0],
                    "pred_y": current_position[1],
                    "detected": True,
                    "missed_count": 0,
                    "blocked_by_grid": False,
                    "mass": np.nan,
                }
            )
            continue
        predicted_position = search_center + velocity
        near_grid = is_position_near_grid(predicted_position, grid_mask, radius=config.grid_occlusion_radius)
        if near_grid and config.skip_detection_on_grid:
            chosen = None
            blocked_by_grid = True
        else:
            features = locate_features_near_position(gray, predicted_position, config.local_search_radius, config, grid_mask)
            chosen = choose_nearest_feature(features, predicted_position, max_distance=config.max_accept_distance)
            blocked_by_grid = False
        if chosen is not None:
            current_position = np.array([float(chosen["x"]), float(chosen["y"])], dtype=float)
            if last_detected_position is not None:
                velocity = current_position - last_detected_position
            last_detected_position = current_position.copy()
            search_center = current_position.copy()
            missed_count = 0
            mass_value = float(chosen["mass"]) if "mass" in chosen.index else np.nan
            rows.append(
                {
                    "frame": frame_id,
                    "source_frame": int(source_start_frame) + int(frame_id),
                    "x": current_position[0],
                    "y": current_position[1],
                    "pred_x": predicted_position[0],
                    "pred_y": predicted_position[1],
                    "detected": True,
                    "missed_count": missed_count,
                    "blocked_by_grid": blocked_by_grid,
                    "mass": mass_value,
                }
            )
        else:
            missed_count += 1
            search_center = predicted_position.copy()
            rows.append(
                {
                    "frame": frame_id,
                    "source_frame": int(source_start_frame) + int(frame_id),
                    "x": np.nan,
                    "y": np.nan,
                    "pred_x": predicted_position[0],
                    "pred_y": predicted_position[1],
                    "detected": False,
                    "missed_count": missed_count,
                    "blocked_by_grid": blocked_by_grid,
                    "mass": np.nan,
                }
            )
            if missed_count > config.single_memory:
                break
    return pd.DataFrame(rows)


@dataclass
class TrackpyDropState:
    track_id: str
    video_id: str
    start_frame: int
    initial_position: np.ndarray
    config: SingleDropTrackingConfig
    roi: Roi
    fps: float
    segment_id: str = field(init=False)
    search_center: np.ndarray = field(init=False)
    last_detected_position: np.ndarray = field(init=False)
    velocity: np.ndarray = field(init=False)
    missed_count: int = 0
    active: bool = True
    end_reason: str = ""
    rows: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.segment_id = f"{self.track_id}_seg001"
        self.search_center = self.initial_position.astype(float)
        self.last_detected_position = self.initial_position.astype(float)
        self.velocity = np.array([0.0, 0.0], dtype=float)

    def step(self, gray, frame_idx: int, grid_mask=None, platforms: pd.DataFrame | None = None) -> None:
        if not self.active or frame_idx < self.start_frame:
            return
        if frame_idx == self.start_frame and not self.rows:
            self._append_row(frame_idx, self.initial_position, self.initial_position, True, "trackpy_seed", False, 0, np.nan, platforms)
            return

        predicted_position = self.search_center + self.velocity
        if not self._inside_roi(predicted_position):
            self.missed_count += 1
            self._append_row(frame_idx, predicted_position, predicted_position, False, "trackpy_prediction", False, self.missed_count, np.nan, platforms)
            self._finish("roi_exit")
            return

        blocked_by_grid = is_position_near_grid(predicted_position, grid_mask, radius=self.config.grid_occlusion_radius)
        if blocked_by_grid and self.config.skip_detection_on_grid:
            chosen = None
        else:
            features = locate_features_near_position(gray, predicted_position, self.config.local_search_radius, self.config, grid_mask)
            chosen = choose_nearest_feature(features, predicted_position, max_distance=self.config.max_accept_distance)

        if chosen is not None:
            current_position = np.array([float(chosen["x"]), float(chosen["y"])], dtype=float)
            jump = float(np.linalg.norm(current_position - self.last_detected_position))
            if self.config.max_jump_px > 0 and jump > self.config.max_jump_px:
                self.missed_count += 1
                self._append_row(frame_idx, predicted_position, predicted_position, False, "trackpy_prediction", False, self.missed_count, np.nan, platforms)
                self._finish("jump_rejected")
                return
            self.velocity = current_position - self.last_detected_position
            self.last_detected_position = current_position.copy()
            self.search_center = current_position.copy()
            self.missed_count = 0
            mass_value = float(chosen["mass"]) if "mass" in chosen.index else np.nan
            self._append_row(frame_idx, current_position, predicted_position, True, "trackpy_detection", False, 0, mass_value, platforms)
            return

        self.missed_count += 1
        self.search_center = predicted_position.copy()
        self._append_row(frame_idx, predicted_position, predicted_position, False, "trackpy_prediction", blocked_by_grid, self.missed_count, np.nan, platforms)
        if blocked_by_grid:
            self._finish("grid_occlusion")
        elif self.missed_count > self.config.single_memory:
            self._finish("missing_limit")

    def finish_at_video_end(self) -> None:
        if self.active:
            self._finish("video_end")

    def _finish(self, reason: str) -> None:
        self.end_reason = reason
        self.active = False
        if self.rows:
            self.rows[-1]["end_reason"] = reason

    def _inside_roi(self, position: np.ndarray) -> bool:
        x, y = float(position[0]), float(position[1])
        return self.roi.x <= x < self.roi.x + self.roi.w and self.roi.y <= y < self.roi.y + self.roi.h

    def _append_row(
        self,
        frame_idx: int,
        position: np.ndarray,
        predicted: np.ndarray,
        detected: bool,
        tracking_source: str,
        blocked_by_grid: bool,
        missed_count: int,
        mass: float,
        platforms: pd.DataFrame | None,
    ) -> None:
        time_s = frame_idx / self.fps if self.fps else 0.0
        platform_id = ""
        voltage = np.nan
        if platforms is not None and not platforms.empty:
            hit = platforms[(platforms["start_time_s"] <= time_s) & (platforms["end_time_s"] >= time_s)]
            if not hit.empty:
                platform_id = str(hit.iloc[0]["platform_id"])
                voltage = float(hit.iloc[0]["voltage_V"])
        radius = max(1.0, float(self.config.diameter) / 2.0)
        self.rows.append(
            {
                "video_id": self.video_id,
                "track_id": self.track_id,
                "segment_id": self.segment_id,
                "frame_idx": int(frame_idx),
                "time_s": float(time_s),
                "x_px": float(position[0]),
                "y_px": float(position[1]),
                "pred_x_px": float(predicted[0]),
                "pred_y_px": float(predicted[1]),
                "radius_px": radius,
                "area_px": float(np.pi * radius * radius),
                "brightness": float(mass) if np.isfinite(mass) else np.nan,
                "mass": float(mass) if np.isfinite(mass) else np.nan,
                "voltage_V": voltage,
                "platform_id": platform_id,
                "is_valid_detection": bool(detected),
                "tracking_source": tracking_source,
                "blocked_by_grid": bool(blocked_by_grid),
                "missed_count": int(missed_count),
                "end_reason": "",
            }
        )
