from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

import math


@dataclass(frozen=True)
class Detection:
    x: float
    y: float
    mass: float | None = None
    quality: float | None = None


@dataclass(frozen=True)
class NormalTrackingConfig:
    memory_frames: int = 5
    base_search_radius_px: float = 45.0
    search_radius_growth_px: float = 8.0
    max_search_radius_px: float = 90.0
    max_accept_distance_px: float = 30.0
    accept_distance_growth_px: float = 4.0
    max_reacquire_dx_px: float = 80.0


@dataclass(frozen=True)
class TrackPoint:
    frame_idx: int
    time_s: float
    status: str
    x: float | None
    y: float | None
    predicted_x: float
    predicted_y: float
    missing_count: int = 0
    blocked_by_grid: bool = False
    mass: float | None = None
    quality: float | None = None
    frame_gap_since_detection: int | None = None
    flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TrackingResult:
    points: list[TrackPoint]
    events: list[dict[str, object]]
    flags: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "points": [point.to_dict() for point in self.points],
            "events": self.events,
            "flags": self.flags,
        }


Detector = Callable[[int, tuple[float, float], float], Detection | None]


def track_single_drop(
    *,
    frame_count: int,
    initial_position: tuple[float, float],
    target_frame: int,
    fps: float,
    config: NormalTrackingConfig,
    detector: Detector,
) -> TrackingResult:
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    if fps <= 0:
        raise ValueError("fps must be positive")
    target_frame = max(0, int(target_frame))
    initial_x, initial_y = float(initial_position[0]), float(initial_position[1])
    search_x, search_y = initial_x, initial_y
    last_detected_x, last_detected_y = initial_x, initial_y
    last_detected_frame = target_frame
    vx = vy = 0.0
    missing_count = 0
    points: list[TrackPoint] = [
        TrackPoint(
            frame_idx=target_frame,
            time_s=target_frame / fps,
            status="tracking",
            x=initial_x,
            y=initial_y,
            predicted_x=initial_x,
            predicted_y=initial_y,
            frame_gap_since_detection=0,
        )
    ]
    events: list[dict[str, object]] = []
    missing_start: int | None = None

    for frame_idx in range(target_frame + 1, frame_count):
        predicted_x = search_x + vx
        predicted_y = search_y + vy
        radius = min(config.max_search_radius_px, config.base_search_radius_px + missing_count * config.search_radius_growth_px)
        accepted_distance = config.max_accept_distance_px + missing_count * config.accept_distance_growth_px
        detection = detector(frame_idx, (predicted_x, predicted_y), radius)

        if detection is not None and _distance((detection.x, detection.y), (predicted_x, predicted_y)) <= accepted_distance:
            frame_gap = max(1, frame_idx - last_detected_frame)
            status = "reacquired" if missing_count > 0 else "tracking"
            flags: list[str] = []
            if status == "reacquired" and abs(float(detection.x) - last_detected_x) > config.max_reacquire_dx_px:
                flags.append("reacquired_dx_too_large")
            vx = (float(detection.x) - last_detected_x) / frame_gap
            vy = (float(detection.y) - last_detected_y) / frame_gap
            search_x, search_y = float(detection.x), float(detection.y)
            last_detected_x, last_detected_y = search_x, search_y
            last_detected_frame = frame_idx
            if status == "reacquired" and missing_start is not None:
                events.append(
                    {
                        "type": "missing_reacquired",
                        "missing_start_frame": missing_start,
                        "reacquired_frame": frame_idx,
                        "frame_gap": frame_gap,
                    }
                )
            missing_count = 0
            missing_start = None
            points.append(
                TrackPoint(
                    frame_idx=frame_idx,
                    time_s=frame_idx / fps,
                    status=status,
                    x=search_x,
                    y=search_y,
                    predicted_x=predicted_x,
                    predicted_y=predicted_y,
                    missing_count=0,
                    mass=detection.mass,
                    quality=detection.quality,
                    frame_gap_since_detection=frame_gap,
                    flags=tuple(flags),
                )
            )
            continue

        missing_count += 1
        if missing_start is None:
            missing_start = frame_idx
        search_x, search_y = predicted_x, predicted_y
        points.append(
            TrackPoint(
                frame_idx=frame_idx,
                time_s=frame_idx / fps,
                status="missing",
                x=None,
                y=None,
                predicted_x=predicted_x,
                predicted_y=predicted_y,
                missing_count=missing_count,
            )
        )
        if missing_count > config.memory_frames:
            break

    return TrackingResult(points=points, events=events, flags=[])


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))

