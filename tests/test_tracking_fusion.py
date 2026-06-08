from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.config import load_config
from millikan_ai.tracking.detector import detect_blobs
from millikan_ai.tracking.fusion import KalmanPointTracker, track_lk_bidirectional
from millikan_ai.tracking.tracker import track_multiple_candidates


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


def test_kalman_point_tracker_predicts_constant_velocity():
    tracker = KalmanPointTracker(10.0, 20.0, dt=0.1)
    tracker.correct((10.0, 20.0))
    tracker.predict()
    tracker.correct((11.0, 20.5))

    predicted = tracker.predict()

    assert 11.5 <= predicted[0] <= 12.5
    assert 20.7 <= predicted[1] <= 21.3
    assert tracker.mahalanobis_distance((12.0, 21.0)) < 3.0
    assert tracker.mahalanobis_distance((80.0, 90.0)) > 10.0


def test_bidirectional_lk_tracks_texture_and_rejects_disappearance():
    previous = np.zeros((100, 120), dtype=np.uint8)
    current = np.zeros_like(previous)
    cv2.circle(previous, (50, 45), 5, 255, -1)
    cv2.line(previous, (46, 45), (54, 45), 80, 1)
    cv2.circle(current, (52, 46), 5, 255, -1)
    cv2.line(current, (48, 46), (56, 46), 80, 1)

    tracked = track_lk_bidirectional(previous, current, (50.0, 45.0), max_forward_backward_error_px=1.0)
    disappeared = track_lk_bidirectional(previous, np.zeros_like(previous), (50.0, 45.0), max_forward_backward_error_px=1.0)

    assert tracked is not None
    assert abs(tracked[0][0] - 52.0) < 0.5
    assert abs(tracked[0][1] - 46.0) < 0.5
    assert tracked[1] < 1.0
    assert disappeared is None


def test_fusion_tracker_does_not_jump_to_distractor_during_occlusion(tmp_path):
    video = tmp_path / "occlusion.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (220, 180))
    for frame_idx in range(70):
        frame = np.zeros((180, 220, 3), dtype=np.uint8)
        target_y = int(45 + 0.7 * frame_idx)
        if not 28 <= frame_idx <= 33:
            cv2.circle(frame, (80, target_y), 5, (255, 255, 255), -1)
            cv2.line(frame, (76, target_y), (84, target_y), (80, 80, 80), 1)
        cv2.circle(frame, (101, 67), 4, (180, 180, 180), -1)
        writer.write(frame)
    writer.release()

    config = load_config("configs/default.yaml")
    config["tracking"].update(
        {
            "top_k_seeds": 2,
            "max_drops": 2,
            "min_grid_line_distance_px": 0,
            "min_grid_clear_fraction": 0,
            "min_tracking_roi_margin_px": 0,
            "min_roi_clear_fraction": 0,
            "max_missing_frames": 12,
        }
    )
    tracks, _summary = track_multiple_candidates(
        video,
        "occlusion",
        Roi(20, 20, 180, 140),
        pd.DataFrame(),
        config,
    )

    initial_points = tracks.sort_values("frame_idx").groupby("track_id").first()
    target_track_id = (initial_points["x_px"] - 80.0).abs().idxmin()
    selected = tracks[tracks["track_id"] == target_track_id].sort_values("frame_idx")
    jumps = np.hypot(selected["x_px"].diff(), selected["y_px"].diff()).dropna()
    after_occlusion = selected[selected["frame_idx"] == 36].iloc[0]
    assert jumps.max() < 8.0
    assert abs(float(after_occlusion["x_px"]) - 80.0) < 3.0
    assert "detection" in set(selected["tracking_source"])
    assert "kalman_prediction" in set(selected["tracking_source"])


def test_multi_keyframe_seeding_tracks_droplet_that_enters_late(tmp_path):
    video = tmp_path / "late_entry.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (220, 180))
    for frame_idx in range(90):
        frame = np.zeros((180, 220, 3), dtype=np.uint8)
        if frame_idx >= 20:
            cv2.circle(frame, (80, int(35 + 0.5 * (frame_idx - 20))), 5, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()

    config = load_config("configs/default.yaml")
    config["tracking"].update(
        {
            "top_k_seeds": 8,
            "max_drops": 5,
            "seed_sample_frames": 6,
            "min_grid_line_distance_px": 0,
            "min_grid_clear_fraction": 0,
            "min_tracking_roi_margin_px": 0,
            "min_roi_clear_fraction": 0,
        }
    )

    tracks, summary = track_multiple_candidates(
        video,
        "late_entry",
        Roi(20, 20, 180, 140),
        pd.DataFrame(),
        config,
    )

    assert not tracks.empty
    assert int(tracks["frame_idx"].min()) >= 15
    assert abs(float(tracks.iloc[0]["x_px"]) - 80.0) < 3.0
    assert summary["selected_for_multi_drop"].astype(bool).any()
