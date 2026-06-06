from __future__ import annotations

from pathlib import Path

import cv2
import pandas as pd

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.video.reader import inspect_video, read_frame


def _draw_roi(frame, roi: Roi, color: tuple[int, int, int], label: str) -> None:
    p1 = (int(roi.x), int(roi.y))
    p2 = (int(roi.x + roi.w), int(roi.y + roi.h))
    cv2.rectangle(frame, p1, p2, color, 2)
    cv2.putText(frame, label, (p1[0] + 6, max(24, p1[1] + 24)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)


def render_diagnostic_overlay(
    video_path: str | Path,
    track: pd.DataFrame,
    grid: GridCalibration,
    tracking_roi: Roi,
    output_path: str | Path,
    frame_idx: int = 0,
) -> bool:
    frame = read_frame(video_path, frame_idx)
    height, width = frame.shape[:2]
    _draw_roi(frame, grid.roi, (255, 0, 0), "microscope ROI")
    _draw_roi(frame, tracking_roi, (0, 180, 0), "tracking ROI")
    for x in grid.grid_lines_x:
        cv2.line(frame, (int(x), 0), (int(x), height), (255, 255, 0), 1)
    for y in grid.grid_lines_y:
        cv2.line(frame, (0, int(y)), (width, int(y)), (255, 255, 0), 1)
    for y, label in [(grid.y_start_px, "measure start"), (grid.y_end_px, "measure end")]:
        if y is not None:
            cv2.line(frame, (0, int(y)), (width, int(y)), (0, 255, 255), 2)
            cv2.putText(frame, label, (20, max(24, int(y) - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
    axis_origin = (max(20, tracking_roi.x + 25), max(40, tracking_roi.y + 35))
    cv2.arrowedLine(frame, axis_origin, (axis_origin[0] + 90, axis_origin[1]), (255, 255, 255), 2, tipLength=0.2)
    cv2.arrowedLine(frame, axis_origin, (axis_origin[0], axis_origin[1] + 90), (255, 255, 255), 2, tipLength=0.2)
    cv2.putText(frame, "+X px", (axis_origin[0] + 96, axis_origin[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, "+Y px", (axis_origin[0] + 6, axis_origin[1] + 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    if not track.empty:
        valid = track[track["is_valid_detection"].astype(bool)] if "is_valid_detection" in track.columns else track
        points = [(int(row["x_px"]), int(row["y_px"])) for row in valid.to_dict("records")]
        for p1, p2 in zip(points[:-1], points[1:]):
            cv2.line(frame, p1, p2, (0, 255, 0), 2)
        first_row = track.iloc[0]
        point = (int(first_row["x_px"]), int(first_row["y_px"]))
        cv2.circle(frame, point, 12, (0, 0, 255), 2)
        cv2.putText(frame, f"best drop: {first_row.get('track_id', '')}", (point[0] + 12, max(24, point[1] - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2, cv2.LINE_AA)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(target), frame)
    return bool(ok and target.exists() and target.stat().st_size > 0)


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
