from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from millikan_ai.tracking.trackpy_core import (
    SingleDropTrackingConfig,
    choose_nearest_feature,
    is_position_near_grid,
    locate_features_near_position,
)


FeatureLocator = Callable[[object, np.ndarray, float, SingleDropTrackingConfig, object | None, int], pd.DataFrame]


@dataclass(frozen=True)
class NormalSingleDropTrackingConfig:
    base: SingleDropTrackingConfig
    max_search_radius_px: float = 80.0
    search_radius_growth_per_missing_px: float = 8.0
    max_accept_distance_px: float = 60.0
    accept_distance_growth_per_missing_px: float = 4.0


def _default_locator(gray, center, radius: float, config: SingleDropTrackingConfig, grid_mask=None, frame_id: int = 0) -> pd.DataFrame:
    del frame_id
    return locate_features_near_position(gray, center, radius, config, grid_mask)


def _effective_radius(base: float, growth: float, cap: float, missed_count: int) -> float:
    return min(float(cap), float(base) + max(0, int(missed_count)) * float(growth))


def track_normal_single_drop(
    frames,
    initial_position,
    config: NormalSingleDropTrackingConfig,
    *,
    grid_mask=None,
    source_start_frame: int = 0,
    fps: float = 30.0,
    feature_locator: FeatureLocator | None = None,
) -> pd.DataFrame:
    """Track one user-selected droplet with explicit tracking/missing states.

    This adapts the teammate local Trackpy search. The important difference from
    the older helper is that velocity is normalized by the number of frames
    between real detections after a missing gap.
    """

    locator = feature_locator or _default_locator
    initial = np.asarray(initial_position, dtype=float)
    rows: list[dict[str, object]] = []

    search_center = initial.copy()
    last_detected_position = initial.copy()
    last_detected_frame = 0
    velocity = np.array([0.0, 0.0], dtype=float)
    missed_count = 0

    for frame_id, gray in enumerate(frames):
        source_frame = int(source_start_frame) + int(frame_id)
        time_s = source_frame / fps if fps else 0.0

        if frame_id == 0:
            rows.append(
                {
                    "frame": int(frame_id),
                    "source_frame": source_frame,
                    "time_s": float(time_s),
                    "x": float(initial[0]),
                    "y": float(initial[1]),
                    "pred_x": float(initial[0]),
                    "pred_y": float(initial[1]),
                    "detected": True,
                    "status": "tracking",
                    "missed_count": 0,
                    "blocked_by_grid": False,
                    "mass": np.nan,
                    "velocity_x_px_frame": 0.0,
                    "velocity_y_px_frame": 0.0,
                    "frame_gap_since_detection": 0,
                }
            )
            continue

        predicted_position = search_center + velocity
        blocked_by_grid = is_position_near_grid(predicted_position, grid_mask, radius=config.base.grid_occlusion_radius)
        chosen = None
        if not (blocked_by_grid and config.base.skip_detection_on_grid):
            search_radius = _effective_radius(
                config.base.local_search_radius,
                config.search_radius_growth_per_missing_px,
                config.max_search_radius_px,
                missed_count,
            )
            accept_distance = _effective_radius(
                config.base.max_accept_distance,
                config.accept_distance_growth_per_missing_px,
                config.max_accept_distance_px,
                missed_count,
            )
            features = locator(gray, predicted_position, search_radius, config.base, grid_mask, frame_id)
            chosen = choose_nearest_feature(features, predicted_position, max_distance=accept_distance)

        if chosen is not None:
            current_position = np.array([float(chosen["x"]), float(chosen["y"])], dtype=float)
            frame_gap = max(1, int(frame_id) - int(last_detected_frame))
            was_missing = missed_count > 0
            velocity = (current_position - last_detected_position) / float(frame_gap)
            last_detected_position = current_position.copy()
            last_detected_frame = int(frame_id)
            search_center = current_position.copy()
            missed_count = 0
            mass_value = float(chosen["mass"]) if "mass" in chosen.index else np.nan
            rows.append(
                {
                    "frame": int(frame_id),
                    "source_frame": source_frame,
                    "time_s": float(time_s),
                    "x": float(current_position[0]),
                    "y": float(current_position[1]),
                    "pred_x": float(predicted_position[0]),
                    "pred_y": float(predicted_position[1]),
                    "detected": True,
                    "status": "reacquired" if was_missing else "tracking",
                    "missed_count": 0,
                    "blocked_by_grid": bool(blocked_by_grid),
                    "mass": mass_value,
                    "velocity_x_px_frame": float(velocity[0]),
                    "velocity_y_px_frame": float(velocity[1]),
                    "frame_gap_since_detection": int(frame_gap),
                }
            )
            continue

        missed_count += 1
        search_center = predicted_position.copy()
        rows.append(
            {
                "frame": int(frame_id),
                "source_frame": source_frame,
                "time_s": float(time_s),
                "x": np.nan,
                "y": np.nan,
                "pred_x": float(predicted_position[0]),
                "pred_y": float(predicted_position[1]),
                "detected": False,
                "status": "missing",
                "missed_count": int(missed_count),
                "blocked_by_grid": bool(blocked_by_grid),
                "mass": np.nan,
                "velocity_x_px_frame": float(velocity[0]),
                "velocity_y_px_frame": float(velocity[1]),
                "frame_gap_since_detection": int(frame_id - last_detected_frame),
            }
        )
        if missed_count > config.base.single_memory:
            break

    return pd.DataFrame(rows)


def missing_reacquired_events(track: pd.DataFrame) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    missing_start: dict[str, object] | None = None
    missing_count = 0
    for row in track.to_dict("records"):
        status = str(row.get("status", ""))
        if status == "missing":
            if missing_start is None:
                missing_start = row
                missing_count = 0
            missing_count += 1
            continue
        if status == "reacquired" and missing_start is not None:
            events.append(
                {
                    "type": "missing_reacquired",
                    "start_frame": int(missing_start["source_frame"]),
                    "end_frame": int(row["source_frame"]),
                    "start_time_s": float(missing_start.get("time_s", 0.0)),
                    "end_time_s": float(row.get("time_s", 0.0)),
                    "missing_frames": int(missing_count),
                    "reacquired_x": float(row["x"]),
                    "reacquired_y": float(row["y"]),
                }
            )
            missing_start = None
            missing_count = 0
    return events

