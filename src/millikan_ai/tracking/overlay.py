from __future__ import annotations

from pathlib import Path

import cv2
import pandas as pd

from millikan_ai.calibration.grid import GridCalibration
from millikan_ai.video.reader import inspect_video


def render_overlay(video_path: str | Path, track: pd.DataFrame, grid: GridCalibration, output_path: str | Path) -> bool:
    if track.empty:
        return False
    meta = inspect_video(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), meta.fps or 30.0, (meta.width, meta.height))
    track_by_frame = {int(row["frame_idx"]): row for row in track.to_dict("records")}
    trail: list[tuple[int, int]] = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        row = track_by_frame.get(frame_idx)
        if row:
            point = (int(row["x_px"]), int(row["y_px"]))
            trail.append(point)
            cv2.circle(frame, point, 8, (0, 0, 255), 2)
            cv2.putText(frame, f"{row.get('platform_id','')} {row.get('voltage_V','')}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        for a, b in zip(trail[-80:-1], trail[-79:]):
            cv2.line(frame, a, b, (0, 255, 0), 2)
        for y in [grid.y_start_px, grid.y_end_px]:
            if y is not None:
                cv2.line(frame, (0, int(y)), (meta.width, int(y)), (255, 255, 0), 1)
        writer.write(frame)
        frame_idx += 1
    cap.release()
    writer.release()
    return target.exists() and target.stat().st_size > 0

