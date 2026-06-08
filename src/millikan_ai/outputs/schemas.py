from __future__ import annotations

from pathlib import Path

import pandas as pd


PLATFORMS_COLUMNS = [
    "platform_id",
    "start_frame",
    "end_frame",
    "start_time_s",
    "end_time_s",
    "voltage_V",
    "voltage_confidence",
    "source",
]

VOLTAGE_SAMPLE_COLUMNS = [
    "frame_idx",
    "time_s",
    "voltage_V",
    "confidence",
    "source",
    "raw_text",
    "accepted",
    "reject_reason",
    "roi_x",
    "roi_y",
    "roi_w",
    "roi_h",
]

BEST_TRACK_COLUMNS = [
    "video_id",
    "track_id",
    "frame_idx",
    "time_s",
    "x_px",
    "y_px",
    "radius_px",
    "area_px",
    "brightness",
    "voltage_V",
    "platform_id",
    "is_valid_detection",
    "tracking_source",
]

SEGMENT_COLUMNS = [
    "video_id",
    "track_id",
    "platform_id",
    "voltage_V",
    "start_time_s",
    "end_time_s",
    "num_points",
    "duration_s",
    "vy_px_s",
    "vy_m_s",
    "sigma_vy",
    "vx_px_s",
    "r2_y",
    "rmse_y",
    "stable",
    "flags",
]

CANDIDATE_SUMMARY_COLUMNS = [
    "candidate_id",
    "usable_platform_count",
    "total_duration_s",
    "missing_ratio",
    "score_total",
    "rank",
    "reject_reason",
]

QUALITY_SCORE_COLUMNS = [
    "track_id",
    "drop_id",
    "trajectory_score",
    "physics_quality_score",
    "quality_score",
    "hard_rule_pass",
    "q_valid",
    "keep",
    "reject_reasons",
]


def validate_columns(path: str | Path, required_columns: list[str]) -> list[str]:
    csv_path = Path(path)
    if not csv_path.exists():
        return [f"missing file: {csv_path.name}"]
    try:
        frame = pd.read_csv(csv_path, nrows=1)
    except Exception as exc:  # pragma: no cover - pandas detail
        return [f"failed to read {csv_path.name}: {exc}"]
    missing = [column for column in required_columns if column not in frame.columns]
    return [f"{csv_path.name} missing column: {column}" for column in missing]
