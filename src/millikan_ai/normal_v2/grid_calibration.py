from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GridScale:
    valid: bool
    y_second_px: int | None
    y_penultimate_px: int | None
    scale_y_m_per_px: float | None
    flags: list[str]


def grid_scale_from_horizontal_lines(lines_y: list[int], *, measurement_distance_m: float) -> GridScale:
    ordered = sorted(int(value) for value in lines_y)
    if len(ordered) < 4:
        return GridScale(False, None, None, None, ["too_few_horizontal_grid_lines"])
    y_second = ordered[1]
    y_penultimate = ordered[-2]
    span = y_penultimate - y_second
    if span <= 0 or measurement_distance_m <= 0:
        return GridScale(False, y_second, y_penultimate, None, ["invalid_grid_span"])
    return GridScale(True, y_second, y_penultimate, float(measurement_distance_m) / float(span), [])

