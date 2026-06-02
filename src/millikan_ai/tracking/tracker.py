from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import Roi
from millikan_ai.tracking.detector import Blob, detect_blobs
from millikan_ai.video.reader import inspect_video


def _distance(a: Blob, b: Blob) -> float:
    return math.hypot(a.x_px - b.x_px, a.y_px - b.y_px)


def track_best_candidate(
    video_path: str | Path,
    video_id: str,
    microscope_roi: Roi,
    platforms: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    meta = inspect_video(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    tracking_cfg = config["tracking"]
    min_area = float(tracking_cfg["min_blob_area_px"])
    max_area = float(tracking_cfg["max_blob_area_px"])
    max_radius = float(tracking_cfg["max_search_radius_px"])
    ok, frame = cap.read()
    if not ok:
        cap.release()
        return pd.DataFrame(), pd.DataFrame()
    seeds = detect_blobs(frame, microscope_roi, min_area, max_area)[: int(tracking_cfg["top_k_seeds"])]
    if not seeds:
        cap.release()
        return pd.DataFrame(), pd.DataFrame(
            [{"candidate_id": "none", "usable_platform_count": 0, "total_duration_s": 0, "missing_ratio": 1, "score_total": 0, "rank": 1, "reject_reason": "no_seeds"}]
        )
    tracks: list[list[dict[str, object]]] = []
    summaries = []
    for seed_idx, seed in enumerate(seeds[: min(10, len(seeds))], start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        current = seed
        rows = []
        missing = 0
        for frame_idx in range(meta.frame_count):
            ok, frame = cap.read()
            if not ok:
                break
            blobs = detect_blobs(frame, microscope_roi, min_area, max_area)
            nearest = min(blobs, key=lambda blob: _distance(blob, current), default=None)
            valid = nearest is not None and _distance(nearest, current) <= max_radius
            if valid:
                current = nearest
            else:
                missing += 1
            time_s = frame_idx / meta.fps if meta.fps else 0.0
            platform_id = ""
            voltage = np.nan
            if not platforms.empty:
                hit = platforms[(platforms["start_time_s"] <= time_s) & (platforms["end_time_s"] >= time_s)]
                if not hit.empty:
                    platform_id = str(hit.iloc[0]["platform_id"])
                    voltage = float(hit.iloc[0]["voltage_V"])
            rows.append(
                {
                    "video_id": video_id,
                    "track_id": f"candidate_{seed_idx:03d}",
                    "frame_idx": frame_idx,
                    "time_s": time_s,
                    "x_px": current.x_px,
                    "y_px": current.y_px,
                    "radius_px": current.radius_px,
                    "area_px": current.area_px,
                    "brightness": current.brightness,
                    "voltage_V": voltage,
                    "platform_id": platform_id,
                    "is_valid_detection": valid,
                    "tracking_source": "detection" if valid else "last_known",
                }
            )
        missing_ratio = missing / max(len(rows), 1)
        total_duration = rows[-1]["time_s"] - rows[0]["time_s"] if len(rows) > 1 else 0.0
        platform_count = len({row["platform_id"] for row in rows if row["platform_id"]})
        score = max(0.0, min(1.0, (1 - missing_ratio) * (0.4 + 0.2 * platform_count)))
        tracks.append(rows)
        summaries.append(
            {
                "candidate_id": f"candidate_{seed_idx:03d}",
                "usable_platform_count": platform_count,
                "total_duration_s": total_duration,
                "missing_ratio": missing_ratio,
                "score_total": score,
                "rank": 0,
                "reject_reason": "" if score > 0 else "tracking_failed",
            }
        )
    cap.release()
    summaries.sort(key=lambda row: row["score_total"], reverse=True)
    for rank, row in enumerate(summaries, start=1):
        row["rank"] = rank
    best_id = summaries[0]["candidate_id"]
    best_rows = next(rows for rows in tracks if rows and rows[0]["track_id"] == best_id)
    return pd.DataFrame(best_rows), pd.DataFrame(summaries)

