from __future__ import annotations

from dataclasses import dataclass

import math
import numpy as np

from millikan_ai.normal_v2.tracking import TrackPoint


@dataclass(frozen=True)
class FallVelocityFit:
    valid: bool
    velocity_m_s: float | None
    slope_y_px_s: float | None
    intercept_y_px: float | None
    r2: float | None
    rmse_px: float | None
    used_frame_indices: list[int]
    truncated_at_frame: int | None
    flags: list[str]


def fit_terminal_velocity(
    points: list[TrackPoint],
    *,
    start_time_s: float,
    end_time_s: float,
    scale_y_m_per_px: float,
    legal_y_min_px: float,
    legal_y_max_px: float,
    min_points: int = 5,
) -> FallVelocityFit:
    if scale_y_m_per_px <= 0:
        return _invalid("invalid_scale")
    rows: list[TrackPoint] = []
    truncated_at: int | None = None
    for point in sorted(points, key=lambda item: item.frame_idx):
        if point.time_s < start_time_s or point.time_s > end_time_s:
            continue
        if point.status not in {"tracking", "reacquired"} or point.x is None or point.y is None:
            continue
        if point.y > legal_y_max_px:
            truncated_at = point.frame_idx
            break
        if point.y < legal_y_min_px:
            continue
        rows.append(point)
    if len(rows) < min_points:
        result = _invalid("too_few_fit_points")
        return FallVelocityFit(**{**result.__dict__, "used_frame_indices": [row.frame_idx for row in rows], "truncated_at_frame": truncated_at})
    t = np.asarray([row.time_s for row in rows], dtype=float)
    y = np.asarray([row.y for row in rows], dtype=float)
    if float(np.max(t) - np.min(t)) <= 0:
        return _invalid("non_positive_duration")
    slope, intercept = np.polyfit(t, y, deg=1)
    pred = slope * t + intercept
    residual = y - pred
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    rmse = math.sqrt(ss_res / len(rows))
    flags: list[str] = []
    if slope <= 0:
        flags.append("non_positive_fall_velocity")
    return FallVelocityFit(
        valid=not flags,
        velocity_m_s=float(slope * scale_y_m_per_px),
        slope_y_px_s=float(slope),
        intercept_y_px=float(intercept),
        r2=float(r2),
        rmse_px=float(rmse),
        used_frame_indices=[row.frame_idx for row in rows],
        truncated_at_frame=truncated_at,
        flags=flags,
    )


def _invalid(flag: str) -> FallVelocityFit:
    return FallVelocityFit(False, None, None, None, None, None, [], None, [flag])

