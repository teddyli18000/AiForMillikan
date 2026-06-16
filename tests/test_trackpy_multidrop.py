from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.config import load_config
from millikan_ai.tracking.trackpy_core import (
    SingleDropTrackingConfig,
    choose_nearest_feature,
    locate_features_near_position,
)
from millikan_ai.tracking.tracker import (
    _deduplicate_track_candidates,
    track_multiple_candidates,
)


def _make_grid() -> GridCalibration:
    return GridCalibration(
        roi=Roi(0, 0, 180, 140),
        grid_lines_x=[],
        grid_lines_y=[70],
        x_start_px=0,
        x_end_px=180,
        y_start_px=20,
        y_end_px=120,
        measurement_distance_m=0.0015,
        scale_y_m_per_px=0.0015 / 100,
        warnings=[],
    )


def test_trackpy_local_detection_selects_nearest_feature():
    gray = np.zeros((100, 120), dtype=np.uint8)
    cv2.circle(gray, (45, 48), 4, 255, -1)
    cv2.circle(gray, (72, 50), 4, 230, -1)
    config = SingleDropTrackingConfig(diameter=7, minmass=20, local_topn=5)

    features = locate_features_near_position(
        gray,
        center=np.array([48.0, 48.0]),
        radius=35,
        config=config,
    )
    chosen = choose_nearest_feature(features, np.array([48.0, 48.0]), max_distance=10)

    assert chosen is not None
    assert np.hypot(float(chosen["x"]) - 45.0, float(chosen["y"]) - 48.0) < 2.0


def _write_two_drop_grid_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (180, 140))
    for frame_idx in range(80):
        frame = np.zeros((140, 180, 3), dtype=np.uint8)
        cv2.line(frame, (0, 70), (179, 70), (255, 255, 255), 2)
        cv2.circle(frame, (55, int(38 + 0.55 * frame_idx)), 4, (255, 255, 255), -1)
        cv2.circle(frame, (125, int(96 + 0.05 * frame_idx)), 4, (230, 230, 230), -1)
        writer.write(frame)
    writer.release()


def test_trackpy_multidrop_cuts_grid_segment_without_stopping_other_tracker(tmp_path: Path):
    video = tmp_path / "grid_cut.mp4"
    _write_two_drop_grid_video(video)
    config = load_config("configs/default.yaml")
    config["tracking"].update(
        {
            "tracker_backend": "trackpy_single_drop",
            "top_k_seeds": 4,
            "max_drops": 4,
            "seed_sample_frames": 3,
            "seed_merge_distance_px": 10,
            "trackpy_diameter": 7,
            "trackpy_minmass": 20,
            "trackpy_local_search_radius_px": 18,
            "trackpy_max_accept_distance_px": 8,
            "trackpy_memory_frames": 2,
            "grid_occlusion_radius_px": 5,
            "grid_reject_dilate_px": 2,
            "min_grid_line_distance_px": 0,
            "min_grid_clear_fraction": 0,
            "min_tracking_roi_margin_px": 0,
            "min_roi_clear_fraction": 0,
        }
    )

    tracks, summary = track_multiple_candidates(
        video,
        "grid_cut",
        Roi(0, 0, 180, 140),
        pd.DataFrame(),
        config,
        _make_grid(),
    )

    assert tracks["track_id"].nunique() >= 2
    assert "segment_id" in tracks.columns
    assert "blocked_by_grid" in tracks.columns
    assert "end_reason" in summary.columns
    assert "grid_occlusion" in set(summary["end_reason"].astype(str))

    by_start_x = tracks.sort_values("frame_idx").groupby("track_id").first()["x_px"]
    grid_track_id = (by_start_x - 55.0).abs().idxmin()
    other_track_id = (by_start_x - 125.0).abs().idxmin()
    grid_track = tracks[tracks["track_id"] == grid_track_id]
    other_track = tracks[tracks["track_id"] == other_track_id]

    assert int(grid_track["frame_idx"].max()) < 75
    assert int(other_track["frame_idx"].max()) >= int(grid_track["frame_idx"].max()) + 10
    assert tracks.loc[tracks["track_id"] == grid_track_id, "blocked_by_grid"].astype(bool).any()


def test_trackpy_deduplication_marks_near_identical_overlapping_tracks():
    base = [
        {"track_id": "candidate_001", "frame_idx": idx, "x_px": 50.0, "y_px": 30.0 + idx, "is_valid_detection": True}
        for idx in range(20)
    ]
    duplicate = [
        {"track_id": "candidate_002", "frame_idx": idx, "x_px": 51.0, "y_px": 30.5 + idx, "is_valid_detection": True}
        for idx in range(20)
    ]
    distinct = [
        {"track_id": "candidate_003", "frame_idx": idx, "x_px": 95.0, "y_px": 30.0 + idx, "is_valid_detection": True}
        for idx in range(20)
    ]
    tracks = {"candidate_001": base, "candidate_002": duplicate, "candidate_003": distinct}
    summaries = [
        {"candidate_id": "candidate_001", "score_total": 0.9, "reject_reason": ""},
        {"candidate_id": "candidate_002", "score_total": 0.7, "reject_reason": ""},
        {"candidate_id": "candidate_003", "score_total": 0.6, "reject_reason": ""},
    ]

    selected = _deduplicate_track_candidates(
        tracks,
        summaries,
        max_drops=3,
        min_distance_px=8,
    )

    assert selected == ["candidate_001", "candidate_003"]
    duplicate_summary = next(row for row in summaries if row["candidate_id"] == "candidate_002")
    assert duplicate_summary["reject_reason"] == "duplicate_track"
    assert duplicate_summary["duplicate_of"] == "candidate_001"
