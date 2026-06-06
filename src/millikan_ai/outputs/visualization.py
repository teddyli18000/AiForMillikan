from __future__ import annotations

import math
from typing import Any

import pandas as pd

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.video.reader import VideoMetadata


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _roi_layer(layer_id: str, roi: Roi, label: str, color: str) -> dict[str, object]:
    return {
        "id": layer_id,
        "type": "rect",
        "label": label,
        "x": roi.x,
        "y": roi.y,
        "w": roi.w,
        "h": roi.h,
        "style": {"stroke": color, "stroke_width": 2},
    }


def build_visualization_layers(
    metadata: VideoMetadata,
    grid: GridCalibration,
    tracking_roi: Roi,
    voltage_roi: Roi,
    best_track: pd.DataFrame,
    platforms: pd.DataFrame,
    drop_tracks: pd.DataFrame | None = None,
) -> dict[str, object]:
    axis_origin = [tracking_roi.x + 25, tracking_roi.y + 35]
    layers: list[dict[str, object]] = [
        {
            "id": "pixel_axes",
            "type": "axes",
            "label": "Pixel coordinate axes",
            "origin": axis_origin,
            "x_positive": "right",
            "y_positive": "down",
            "x_label": "+X px",
            "y_label": "+Y px",
            "style": {"stroke": "#ffffff", "stroke_width": 2},
        },
        _roi_layer("microscope_roi", grid.roi, "Microscope ROI", "#0066ff"),
        _roi_layer("tracking_roi", tracking_roi, "Tracking ROI", "#00b000"),
        _roi_layer("voltage_roi", voltage_roi, "Voltage ROI", "#ff9900"),
        {
            "id": "vertical_grid_lines",
            "type": "line_set",
            "label": "Vertical grid lines",
            "orientation": "vertical",
            "positions_px": grid.grid_lines_x,
            "style": {"stroke": "#00ffff", "stroke_width": 1},
        },
        {
            "id": "horizontal_grid_lines",
            "type": "line_set",
            "label": "Horizontal grid lines",
            "orientation": "horizontal",
            "positions_px": grid.grid_lines_y,
            "style": {"stroke": "#00ffff", "stroke_width": 1},
        },
        {
            "id": "measurement_lines",
            "type": "line_pair",
            "label": "Measurement distance lines",
            "orientation": "horizontal",
            "start_px": grid.y_start_px,
            "end_px": grid.y_end_px,
            "distance_m": grid.measurement_distance_m,
            "scale_y_m_per_px": grid.scale_y_m_per_px,
            "style": {"stroke": "#ffff00", "stroke_width": 2},
        },
    ]
    if not platforms.empty:
        layers.append(
            {
                "id": "voltage_platforms",
                "type": "time_intervals",
                "label": "Manual or OCR voltage platforms",
                "intervals": [
                    {
                        "platform_id": str(row["platform_id"]),
                        "start_frame": int(row["start_frame"]),
                        "end_frame": int(row["end_frame"]),
                        "start_time_s": float(row["start_time_s"]),
                        "end_time_s": float(row["end_time_s"]),
                        "voltage_V": float(row["voltage_V"]),
                        "source": str(row["source"]),
                    }
                    for row in platforms.to_dict("records")
                ],
            }
        )
    if drop_tracks is not None and not drop_tracks.empty:
        tracks = []
        for track_id, track in drop_tracks.groupby("track_id", sort=False):
            points = [
                {
                    "frame_idx": int(row["frame_idx"]),
                    "time_s": float(row["time_s"]),
                    "x_px": float(row["x_px"]),
                    "y_px": float(row["y_px"]),
                    "valid": bool(row.get("is_valid_detection", True)),
                    "platform_id": str(_clean(row.get("platform_id", "")) or ""),
                    "voltage_V": _clean(float(row["voltage_V"])) if row.get("voltage_V") is not None else None,
                }
                for row in track.to_dict("records")
            ]
            tracks.append({"track_id": str(track_id), "points": points})
        layers.append(
            {
                "id": "drop_tracks",
                "type": "multi_frame_point_series",
                "label": "All selected droplet trajectories",
                "tracks": tracks,
                "style": {"stroke_palette": ["#00ff00", "#ff66cc", "#66ccff", "#ffaa00"], "stroke_width": 2},
            }
        )
    if not best_track.empty:
        records = best_track.to_dict("records")
        points = [
            {
                "frame_idx": int(row["frame_idx"]),
                "time_s": float(row["time_s"]),
                "x_px": float(row["x_px"]),
                "y_px": float(row["y_px"]),
                "valid": bool(row.get("is_valid_detection", True)),
                "platform_id": str(_clean(row.get("platform_id", "")) or ""),
                "voltage_V": _clean(float(row["voltage_V"])) if row.get("voltage_V") is not None else None,
            }
            for row in records
        ]
        first_valid = next((point for point in points if point["valid"]), points[0])
        layers.append(
            {
                "id": "best_track",
                "type": "frame_point_series",
                "label": "Selected best droplet trajectory",
                "track_id": str(records[0].get("track_id", "")),
                "points": points,
                "style": {"stroke": "#00ff00", "stroke_width": 2, "marker": "#ff0000"},
            }
        )
        layers.append(
            {
                "id": "selected_drop_marker",
                "type": "marker",
                "label": "Selected droplet",
                "frame_idx": first_valid["frame_idx"],
                "time_s": first_valid["time_s"],
                "x_px": first_valid["x_px"],
                "y_px": first_valid["y_px"],
                "style": {"stroke": "#ff0000", "stroke_width": 2, "radius_px": 12},
            }
        )
    return {
        "schema_version": 1,
        "frame": {
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "frame_count": metadata.frame_count,
            "duration_s": metadata.duration_s,
        },
        "coordinate_system": {
            "origin": "top_left_video_pixel",
            "x_positive": "right",
            "y_positive": "down",
            "time_s": "frame_idx / fps",
        },
        "layers": layers,
    }
