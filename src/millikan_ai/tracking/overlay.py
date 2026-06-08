from __future__ import annotations

from pathlib import Path

import cv2
import pandas as pd

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.video.reader import inspect_video, read_frame


def _draw_roi(frame, roi: Roi, color: tuple[int, int, int], label: str, *, label_at_bottom: bool = False) -> None:
    p1 = (int(roi.x), int(roi.y))
    p2 = (int(roi.x + roi.w), int(roi.y + roi.h))
    cv2.rectangle(frame, p1, p2, color, 2)
    label_y = p2[1] - 8 if label_at_bottom else max(22, p1[1] + 20)
    cv2.putText(frame, label, (p1[0] + 6, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def render_diagnostic_overlay(
    video_path: str | Path,
    track: pd.DataFrame,
    grid: GridCalibration,
    tracking_roi: Roi,
    output_path: str | Path,
    frame_idx: int = 0,
    all_tracks: pd.DataFrame | None = None,
    quality_scores: pd.DataFrame | None = None,
) -> bool:
    frame = read_frame(video_path, frame_idx)
    height, width = frame.shape[:2]
    _draw_roi(frame, grid.roi, (255, 0, 0), "microscope ROI")
    _draw_roi(frame, tracking_roi, (0, 180, 0), "tracking ROI", label_at_bottom=True)
    for x in grid.grid_lines_x:
        cv2.line(frame, (int(x), 0), (int(x), height), (255, 255, 0), 1)
    for y in grid.grid_lines_y:
        cv2.line(frame, (0, int(y)), (width, int(y)), (255, 255, 0), 1)
    for y, label in [(grid.y_start_px, "measure start"), (grid.y_end_px, "measure end")]:
        if y is not None:
            cv2.line(frame, (0, int(y)), (width, int(y)), (0, 255, 255), 2)
            cv2.putText(frame, label, (max(8, width - 105), max(18, int(y) - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    axis_origin = (max(16, tracking_roi.x + 18), max(tracking_roi.y + 45, tracking_roi.y + tracking_roi.h - 65))
    cv2.arrowedLine(frame, axis_origin, (axis_origin[0] + 45, axis_origin[1]), (255, 255, 255), 1, tipLength=0.2)
    cv2.arrowedLine(frame, axis_origin, (axis_origin[0], axis_origin[1] + 45), (255, 255, 255), 1, tipLength=0.2)
    cv2.putText(frame, "+X", (axis_origin[0] + 49, axis_origin[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, "+Y", (axis_origin[0] + 4, axis_origin[1] + 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    selected_track_id = str(track.iloc[0]["track_id"]) if not track.empty else ""
    quality_by_track = {}
    if quality_scores is not None and not quality_scores.empty:
        quality_by_track = {str(row["track_id"]): row for row in quality_scores.to_dict("records")}
    if all_tracks is not None and not all_tracks.empty:
        palette = [(0, 220, 0), (255, 120, 0), (220, 0, 220), (0, 180, 255)]
        legend_x = max(8, width - 150)
        for index, (track_id, candidate) in enumerate(all_tracks.groupby("track_id", sort=False)):
            valid = candidate[candidate["is_valid_detection"].astype(bool)]
            points = [(int(row["x_px"]), int(row["y_px"])) for row in valid.to_dict("records")]
            quality = quality_by_track.get(str(track_id), {})
            color = palette[index % len(palette)] if bool(quality.get("keep", False)) else (130, 130, 130)
            for p1, p2 in zip(points[:-1], points[1:]):
                cv2.line(frame, p1, p2, color, 1)
            status = "KEEP" if bool(quality.get("keep", False)) else "REJECT"
            selected_label = " *" if str(track_id) == selected_track_id else ""
            cv2.putText(
                frame,
                f"{track_id}: {status}{selected_label}",
                (legend_x, 18 + index * 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                color,
                1,
                cv2.LINE_AA,
            )
    if not track.empty:
        valid = track[track["is_valid_detection"].astype(bool)] if "is_valid_detection" in track.columns else track
        points = [(int(row["x_px"]), int(row["y_px"])) for row in valid.to_dict("records")]
        for p1, p2 in zip(points[:-1], points[1:]):
            cv2.line(frame, p1, p2, (0, 255, 0), 2)
        first_row = track.iloc[0]
        point = (int(first_row["x_px"]), int(first_row["y_px"]))
        cv2.circle(frame, point, 12, (0, 0, 255), 2)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(target), frame)
    return bool(ok and target.exists() and target.stat().st_size > 0)


def render_overlay(
    video_path: str | Path,
    track: pd.DataFrame,
    grid: GridCalibration,
    output_path: str | Path,
    all_tracks: pd.DataFrame | None = None,
    quality_scores: pd.DataFrame | None = None,
) -> bool:
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
    selected_track_id = str(track.iloc[0]["track_id"])
    quality_by_track = {}
    if quality_scores is not None and not quality_scores.empty:
        quality_by_track = {str(row["track_id"]): row for row in quality_scores.to_dict("records")}
    frame_tracks: dict[int, list[dict[str, object]]] = {}
    if all_tracks is not None and not all_tracks.empty:
        for row in all_tracks.to_dict("records"):
            frame_tracks.setdefault(int(row["frame_idx"]), []).append(row)
    trails: dict[str, list[tuple[int, int]]] = {}
    palette = [(0, 220, 0), (255, 120, 0), (220, 0, 220), (0, 180, 255)]
    track_colors: dict[str, tuple[int, int, int]] = {}
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
        for candidate in frame_tracks.get(frame_idx, []):
            track_id = str(candidate["track_id"])
            quality = quality_by_track.get(track_id, {})
            if track_id not in track_colors:
                track_colors[track_id] = palette[len(track_colors) % len(palette)] if bool(quality.get("keep", False)) else (130, 130, 130)
            color = (0, 255, 255) if track_id == selected_track_id else track_colors[track_id]
            point = (int(candidate["x_px"]), int(candidate["y_px"]))
            trails.setdefault(track_id, []).append(point)
            cv2.circle(frame, point, 6 if track_id == selected_track_id else 4, color, 2)
            cv2.putText(frame, track_id, (point[0] + 6, point[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
            history = trails[track_id][-50:]
            for a, b in zip(history[:-1], history[1:]):
                cv2.line(frame, a, b, color, 1)
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
