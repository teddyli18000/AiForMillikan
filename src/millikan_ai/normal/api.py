from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import Roi, calibrate_grid
from millikan_ai.config import load_config
from millikan_ai.normal.elementary import estimate_both_algorithms
from millikan_ai.normal.physics import compute_balance_fall_q, fit_fall_velocity
from millikan_ai.normal.tracking import (
    NormalSingleDropTrackingConfig,
    missing_reacquired_events,
    track_normal_single_drop,
)
from millikan_ai.normal.voltage import suggest_normal_fall_window
from millikan_ai.tracking.grid_mask import build_grid_mask_from_calibration
from millikan_ai.tracking.trackpy_core import SingleDropTrackingConfig, preprocess_frame_for_droplets
from millikan_ai.video.reader import inspect_video, read_frame


@dataclass(frozen=True)
class NormalTarget:
    x_px: float
    y_px: float
    frame: int = 0
    box: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class NormalWindow:
    fall_start_frame: int
    fall_end_frame: int | None = None


@dataclass(frozen=True)
class NormalRunRequest:
    video_path: str | Path
    balance_voltage_V: float
    target: NormalTarget
    config_path: str | Path = "configs/default.yaml"
    run_dir: str | Path | None = None
    window: NormalWindow | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _read_frames(video_path: str | Path, start_frame: int, end_frame: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(start_frame)))
    frames: list[np.ndarray] = []
    frame_idx = int(start_frame)
    while frame_idx <= int(end_frame):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
        frame_idx += 1
    cap.release()
    return frames


def _target_from_payload(payload: dict[str, Any]) -> NormalTarget:
    if "target" in payload and isinstance(payload["target"], dict):
        payload = payload["target"]
    box = payload.get("box") or payload.get("target_box")
    if box:
        x, y, w, h = [float(value) for value in box]
        return NormalTarget(x + w / 2.0, y + h / 2.0, int(payload.get("frame", 0) or 0), (x, y, w, h))
    x = payload.get("x_px", payload.get("x"))
    y = payload.get("y_px", payload.get("y"))
    if x is None or y is None:
        raise ValueError("normal target requires x/y or box")
    return NormalTarget(float(x), float(y), int(payload.get("frame", 0) or 0), None)


def _window_from_payload(payload: dict[str, Any], fps: float) -> NormalWindow | None:
    value = payload.get("window") or payload.get("confirmed_window") or payload.get("confirmedWindow")
    if not isinstance(value, dict):
        return None
    start = value.get("fall_start_frame", value.get("fallStartFrame"))
    if start is None and value.get("fall_start_time_s", value.get("fallStartTimeS")) is not None:
        start = int(round(float(value.get("fall_start_time_s", value.get("fallStartTimeS"))) * fps))
    end = value.get("fall_end_frame", value.get("fallEndFrame"))
    if end is None and value.get("fall_end_time_s", value.get("fallEndTimeS")) is not None:
        end = int(round(float(value.get("fall_end_time_s", value.get("fallEndTimeS"))) * fps))
    if start is None:
        return None
    return NormalWindow(int(start), int(end) if end is not None else None)


def _run_dir(video_path: str | Path, config: dict[str, Any], requested: str | Path | None) -> Path:
    if requested:
        return Path(requested)
    root = Path(config.get("project", {}).get("run_root", "runs"))
    stem = Path(video_path).stem
    index = 1
    while True:
        candidate = root / f"normal_{stem}_{index:03d}"
        if not candidate.exists():
            return candidate
        index += 1


def _tracking_config(config: dict[str, Any]) -> NormalSingleDropTrackingConfig:
    tracking = dict(config.get("tracking", {}))
    normal = dict(config.get("normal_mode", {}))
    base = SingleDropTrackingConfig(
        diameter=int(tracking.get("trackpy_diameter", 5)),
        invert=bool(tracking.get("trackpy_invert", False)),
        minmass=float(tracking.get("trackpy_minmass", 80.0)),
        local_search_radius=float(tracking.get("trackpy_local_search_radius_px", 45.0)),
        max_accept_distance=float(tracking.get("trackpy_max_accept_distance_px", 30.0)),
        single_memory=int(tracking.get("trackpy_memory_frames", 5)),
        local_topn=int(tracking.get("trackpy_local_topn", 20)),
        grid_reject_dilate_px=int(tracking.get("grid_reject_dilate_px", 0)),
        grid_occlusion_radius=int(tracking.get("grid_occlusion_radius_px", 0)),
        skip_detection_on_grid=bool(tracking.get("skip_detection_on_grid", True)),
        max_jump_px=float(tracking.get("trackpy_max_jump_px", 0.0)),
    )
    return NormalSingleDropTrackingConfig(
        base=base,
        max_search_radius_px=float(normal.get("max_search_radius_px", 80.0)),
        search_radius_growth_per_missing_px=float(normal.get("search_radius_growth_per_missing_px", 8.0)),
        max_accept_distance_px=float(normal.get("max_accept_distance_px", 60.0)),
        accept_distance_growth_per_missing_px=float(normal.get("accept_distance_growth_per_missing_px", 4.0)),
    )


def _normal_layers(track: pd.DataFrame, grid: dict[str, Any], target: NormalTarget, fit_interval: dict[str, Any]) -> dict[str, Any]:
    points = []
    for row in track.to_dict("records"):
        points.append(
            {
                "frame_idx": int(row["source_frame"]),
                "time_s": float(row["time_s"]),
                "x_px": row.get("x"),
                "y_px": row.get("y"),
                "pred_x_px": row.get("pred_x"),
                "pred_y_px": row.get("pred_y"),
                "status": row.get("status"),
                "detected": bool(row.get("detected")),
            }
        )
    return {
        "schema_version": 1,
        "mode": "normal_balance_fall",
        "layers": [
            {"id": "target_droplet", "type": "point", "x_px": target.x_px, "y_px": target.y_px, "frame_idx": target.frame},
            {"id": "horizontal_grid_lines", "type": "line_set", "orientation": "horizontal", "positions_px": grid.get("grid_lines_y", [])},
            {"id": "fit_interval", "type": "frame_interval", **fit_interval},
            {"id": "normal_track", "type": "status_point_series", "points": points},
        ],
    }


def _write_normal_report(path: Path, bundle: dict[str, Any]) -> None:
    q = bundle.get("q_record", {})
    result = q.get("result", {}) if isinstance(q, dict) else {}
    blind = bundle.get("blind_inversion", {})
    usable = int(blind.get("usable_q_count", 0) or 0) if isinstance(blind, dict) else 0
    lines = [
        "# Normal Balance-Fall Report",
        "",
        f"Mode: `{bundle.get('mode')}`",
        f"Usable q records before blind inversion: {usable}",
        "",
        "## q Result",
        "",
        f"- q_C: {result.get('q_C', '-')}",
        f"- sigma_q_total_C: {result.get('sigma_q_total_C', '-')}",
        f"- radius_m: {result.get('radius_m', '-')}",
        f"- flags: {', '.join(q.get('flags', [])) if isinstance(q, dict) else '-'}",
    ]
    normal = blind.get("normal_algorithm", {}) if isinstance(blind, dict) else {}
    experimental = blind.get("experimental_algorithm", {}) if isinstance(blind, dict) else {}
    if usable >= 3 and (normal.get("valid") or experimental.get("bounded_estimate_available")):
        lines.extend(
            [
                "",
                "## Blind Inversion",
                "",
                f"- normal_algorithm_status: {normal.get('status', '-')}",
                f"- normal_e_hat_C: {normal.get('e_hat_C', '-')}",
                f"- experimental_status: {experimental.get('status', '-')}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_normal_single_drop(request: NormalRunRequest) -> dict[str, Any]:
    config = load_config(request.config_path)
    meta = inspect_video(request.video_path)
    if not meta.readable:
        raise RuntimeError("video_unreadable")
    suggestion = suggest_normal_fall_window(request.video_path, request.config_path)
    window = request.window or NormalWindow(
        int(suggestion.get("suggested_window", {}).get("fall_start_frame", request.target.frame)),
        int(suggestion.get("suggested_window", {}).get("fall_end_frame", meta.frame_count - 1)),
    )
    end_frame = min(meta.frame_count - 1, int(window.fall_end_frame if window.fall_end_frame is not None else meta.frame_count - 1))
    start_frame = min(max(0, int(request.target.frame)), end_frame)
    frames_bgr = _read_frames(request.video_path, start_frame, end_frame)
    if not frames_bgr:
        raise RuntimeError("no_frames_in_normal_window")
    first_frame = read_frame(request.video_path, 0)
    microscope_roi = Roi.from_config(config.get("roi", {}).get("microscope_roi"))
    grid = calibrate_grid(
        first_frame,
        microscope_roi,
        float(config.get("calibration", {}).get("measurement_distance_m", 0.0015)),
        int(config.get("calibration", {}).get("min_grid_lines", 4)),
    )
    scale = grid.scale_y_m_per_px
    if scale is None:
        scale = float(config.get("normal_mode", {}).get("fallback_scale_y_m_per_px", 0.0) or 0.0)
    if scale <= 0:
        raise RuntimeError("normal_mode_scale_unavailable")
    grid_mask = build_grid_mask_from_calibration(
        first_frame.shape[:2],
        grid,
        dilate_px=int(config.get("tracking", {}).get("grid_reject_dilate_px", 0)),
    )
    frames_gray = [preprocess_frame_for_droplets(frame, None) for frame in frames_bgr]
    track = track_normal_single_drop(
        frames_gray,
        np.asarray([request.target.x_px, request.target.y_px], dtype=float),
        _tracking_config(config),
        grid_mask=grid_mask,
        source_start_frame=start_frame,
        fps=meta.fps,
    )
    fall_start = max(start_frame, int(window.fall_start_frame))
    fit = fit_fall_velocity(
        track,
        fps=meta.fps,
        scale_y_m_per_px=float(scale),
        start_frame=fall_start,
        end_frame=end_frame,
        penultimate_grid_y_px=grid.y_end_px,
        min_points=int(config.get("normal_mode", {}).get("min_fit_points", 5)),
    )
    q_record = compute_balance_fall_q(
        fit,
        balance_voltage_V=float(request.balance_voltage_V),
        config=config,
        record_id=f"q_{Path(request.video_path).stem}_001",
    )
    if q_record.get("result"):
        q_record = {
            **q_record,
            "video_path": str(request.video_path),
            "balance_voltage_V": float(request.balance_voltage_V),
            "selected": bool(q_record.get("valid")),
            "q_C": q_record["result"].get("q_C"),
            "sigma_q_C": q_record["result"].get("sigma_q_total_C"),
        }
    q_records = [q_record] if q_record.get("usable_for_inversion") else []
    blind = estimate_both_algorithms(q_records, config) if q_records else {"usable_q_count": 0, "normal_algorithm": {"valid": False, "status": "insufficient_q_records"}, "experimental_algorithm": {"status": "insufficient_drops"}, "reportable": False}

    run_dir = _run_dir(request.video_path, config, request.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    track_path = run_dir / "normal_track.csv"
    track.to_csv(track_path, index=False)
    q_path = run_dir / "normal_q_records.csv"
    pd.DataFrame([q_record]).to_csv(q_path, index=False)
    result_path = run_dir / "normal_result.json"
    manifest_path = run_dir / "run_manifest.json"
    layers_path = run_dir / "normal_visualization_layers.json"
    report_path = run_dir / "normal_report.md"
    fit_interval = {
        "start_frame": fit.start_frame,
        "end_frame": fit.end_frame,
        "requested_start_frame": int(fall_start),
        "requested_end_frame": int(end_frame),
    }
    bundle = {
        "schema_version": 1,
        "mode": "normal_balance_fall",
        "run_dir": str(run_dir),
        "video": meta.to_dict(),
        "input": {"balance_voltage_V": float(request.balance_voltage_V), "config_path": str(request.config_path)},
        "target": asdict(request.target),
        "suggestion": {key: value for key, value in suggestion.items() if key != "samples"},
        "confirmed_window": asdict(window),
        "grid_calibration": grid.to_dict(),
        "tracking_summary": {
            "total_rows": int(len(track)),
            "detected_rows": int(track["detected"].sum()) if not track.empty else 0,
            "events": missing_reacquired_events(track),
        },
        "fit_interval": fit_interval,
        "fit_diagnostics": fit.to_dict(),
        "q_record": q_record,
        "blind_inversion": blind,
        "files": {
            "normal_result_json": str(result_path),
            "normal_track_csv": str(track_path),
            "normal_q_records_csv": str(q_path),
            "normal_visualization_layers_json": str(layers_path),
            "normal_report_md": str(report_path),
            "run_manifest_json": str(manifest_path),
        },
    }
    layers = _normal_layers(track, grid.to_dict(), request.target, fit_interval)
    manifest = {
        "schema_version": 1,
        "mode": "normal_balance_fall",
        "run_dir": str(run_dir),
        "status": {
            "video_readable": True,
            "valid_for_q": bool(q_record.get("valid")),
            "elementary_estimation_ready": int(blind.get("usable_q_count", 0) or 0) >= 3,
            "flags": list(q_record.get("flags", [])),
        },
        "counts": {
            "usable_q_records": int(blind.get("usable_q_count", 0) or 0),
            "tracking_points": int(len(track)),
            "detected_tracking_points": int(track["detected"].sum()) if not track.empty else 0,
        },
        "video": meta.to_dict(),
        "primary_results": q_record.get("result", {}),
        "files": bundle["files"],
    }
    _write_json(result_path, bundle)
    _write_json(layers_path, layers)
    _write_json(manifest_path, manifest)
    _write_normal_report(report_path, bundle)
    return {**bundle, "manifest": manifest, "visualization_layers": layers}


def run_normal_single_drop_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    meta = inspect_video(payload["video_path"] if "video_path" in payload else payload["videoPath"])
    target = _target_from_payload(payload)
    window = _window_from_payload(payload, meta.fps)
    request = NormalRunRequest(
        video_path=payload.get("video_path", payload.get("videoPath")),
        balance_voltage_V=float(payload.get("balance_voltage_V", payload.get("balanceVoltageV"))),
        target=target,
        config_path=payload.get("config_path", payload.get("configPath", "configs/default.yaml")),
        run_dir=payload.get("run_dir", payload.get("runDir")),
        window=window,
    )
    return run_normal_single_drop(request)

