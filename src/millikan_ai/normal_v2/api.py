from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from millikan_ai.config import load_config
from millikan_ai.normal_v2.elementary import estimate_normal_integer_fit
from millikan_ai.normal_v2.grid_calibration import grid_scale_from_horizontal_lines
from millikan_ai.normal_v2.physics import PhysicalConfig, compute_balance_fall_charge
from millikan_ai.normal_v2.records import NormalQRecord, NormalSession, load_session, save_session
from millikan_ai.normal_v2.reporting import render_session_report
from millikan_ai.normal_v2.tracking import Detection, NormalTrackingConfig, track_single_drop
from millikan_ai.normal_v2.velocity import fit_terminal_velocity
from millikan_ai.normal_v2.voltage_events import ChangePeak, merge_change_operations, normal_window_from_operations


def suggest_window_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    video_path = Path(_value(payload, "video_path"))
    meta = _video_meta(video_path)
    fps = float(meta["fps"] or 30.0)
    peaks = _detect_change_peaks(video_path, fps=fps)
    operations = merge_change_operations(peaks, fps=fps, merge_window_s=0.8)
    window = normal_window_from_operations(operations, frame_count=int(meta["frame_count"]), fps=fps, stable_after_s=0.2)
    return {
        "metadata": meta,
        "window": {
            "start_frame": window.start_frame,
            "end_frame": window.end_frame,
            "start_time_s": window.start_frame / fps,
            "end_time_s": window.end_frame / fps,
            "flags": window.flags,
        },
        "operations": [asdict(operation) for operation in operations],
    }


def run_single_drop_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    video_path = Path(_value(payload, "video_path"))
    run_dir = Path(_value(payload, "run_dir", None) or _default_run_dir(video_path))
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = _video_meta(video_path)
    fps = float(meta["fps"] or 30.0)
    target = dict(_value(payload, "target"))
    target_frame = int(target.get("frame", target.get("target_frame", 0)) or 0)
    initial = (float(target["x"]), float(target["y"]))
    window = dict(_value(payload, "confirmed_window", {}) or {})
    start_frame = int(window.get("start_frame", target_frame))
    end_frame = int(window.get("end_frame", meta["frame_count"] - 1))
    end_frame = min(end_frame, int(meta["frame_count"]) - 1)
    balance_voltage = float(_value(payload, "balance_voltage_V"))
    grid_lines_y = [int(value) for value in _value(payload, "grid_lines_y", []) or []]
    if not grid_lines_y:
        grid_lines_y = _detect_horizontal_grid_lines(video_path, target_frame)
    grid = grid_scale_from_horizontal_lines(grid_lines_y, measurement_distance_m=1.5e-3)

    frames = _read_gray_frames(video_path, target_frame, end_frame)
    detector = _make_bright_local_detector(frames, source_start_frame=target_frame)
    tracking = track_single_drop(
        frame_count=end_frame + 1,
        initial_position=initial,
        target_frame=target_frame,
        fps=fps,
        config=NormalTrackingConfig(),
        detector=detector,
    )

    q_record: NormalQRecord
    fit = None
    charge = None
    flags: list[str] = []
    if not grid.valid or grid.scale_y_m_per_px is None or grid.y_second_px is None or grid.y_penultimate_px is None:
        flags.extend(grid.flags)
        q_record = NormalQRecord.create(
            video_path=str(video_path),
            target_frame=target_frame,
            window={"start_frame": start_frame, "end_frame": end_frame},
            q_C=None,
            sigma_q_C=None,
            valid=False,
            flags=flags,
            run_dir=str(run_dir),
        )
    else:
        fit = fit_terminal_velocity(
            tracking.points,
            start_time_s=start_frame / fps,
            end_time_s=end_frame / fps,
            scale_y_m_per_px=grid.scale_y_m_per_px,
            legal_y_min_px=float(grid.y_second_px),
            legal_y_max_px=float(grid.y_penultimate_px),
            min_points=5,
        )
        if not fit.valid or fit.velocity_m_s is None:
            flags.extend(fit.flags)
            q_record = NormalQRecord.create(
                video_path=str(video_path),
                target_frame=target_frame,
                window={"start_frame": start_frame, "end_frame": end_frame},
                q_C=None,
                sigma_q_C=None,
                valid=False,
                flags=flags,
                run_dir=str(run_dir),
            )
        else:
            charge = compute_balance_fall_charge(
                v_g_m_s=fit.velocity_m_s,
                balance_voltage_V=balance_voltage,
                config=_physical_config(load_config(_value(payload, "config_path", None) or "configs/default.yaml")),
            )
            flags.extend(charge.flags)
            sigma_q = _sigma_q(charge.charge_C, fit)
            q_record = NormalQRecord.create(
                video_path=str(video_path),
                target_frame=target_frame,
                window={"start_frame": start_frame, "end_frame": end_frame},
                q_C=charge.charge_C,
                sigma_q_C=sigma_q,
                valid=bool(charge.valid and sigma_q and sigma_q > 0),
                flags=flags,
                run_dir=str(run_dir),
            )

    track_csv = run_dir / "normal_track.csv"
    track_json = run_dir / "normal_track.json"
    result_json = run_dir / "normal_result.json"
    layers_json = run_dir / "normal_visualization_layers.json"
    report_md = run_dir / "normal_report.md"
    _write_track_csv(track_csv, [point.to_dict() for point in tracking.points])
    track_json.write_text(json.dumps(tracking.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    layers = _layers(meta, grid_lines_y, tracking.to_dict(), q_record)
    layers_json.write_text(json.dumps(layers, indent=2, ensure_ascii=False), encoding="utf-8")
    result = {
        "mode": "normal_v2",
        "video": meta,
        "grid": asdict(grid),
        "fit": asdict(fit) if fit is not None else None,
        "charge": asdict(charge) if charge is not None else None,
        "q_record": q_record.to_dict(),
        "tracking_events": tracking.events,
        "files": {
            "normal_track_csv": str(track_csv),
            "normal_track_json": str(track_json),
            "normal_result_json": str(result_json),
            "normal_visualization_layers_json": str(layers_json),
            "normal_report_md": str(report_md),
        },
    }
    result_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    report_md.write_text(_single_report(result), encoding="utf-8")
    manifest = {
        "mode": "normal_v2",
        "run_dir": str(run_dir),
        "q_record_id": q_record.record_id,
        "valid_for_q": q_record.valid,
        "files": result["files"],
    }
    (run_dir / "normal_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "manifest": manifest,
        "q_record": q_record.to_dict(),
        "track_points": [point.to_dict() for point in tracking.points],
        "events": tracking.events,
        "files": result["files"],
        "normal_result": result,
    }


def save_session_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    records = [NormalQRecord(**row) for row in _value(payload, "records", [])]
    session = NormalSession(records=records, inversion=_value(payload, "inversion", None))
    path = save_session(session, _value(payload, "session_path"))
    return {"session_path": str(path), "session": session.to_dict(), "counts": session.counts()}


def load_session_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    session = load_session(_value(payload, "session_path"))
    return {"session": session.to_dict(), "counts": session.counts()}


def estimate_elementary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    records = list(_value(payload, "records", []) or [])
    normal = estimate_normal_integer_fit(records, grid_points=int(_value(payload, "grid_points", 1200)))
    experimental = _experimental_estimate(records)
    return {"normal_algorithm": normal, "experimental_algorithm": experimental}


def session_report_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    report = render_session_report(dict(_value(payload, "session")), _value(payload, "inversion", None))
    path_value = _value(payload, "report_path", None)
    if path_value:
        path = Path(path_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        return {"report_path": str(path), "report_md": report}
    return {"report_md": report}


def _experimental_estimate(records: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        from millikan_ai.elementary.estimate import estimate_elementary_charge

        drops = [
            {
                "drop_id": row.get("record_id"),
                "valid": bool(row.get("valid") and row.get("selected", True)),
                "result": {"charge_abs_C": row.get("q_C"), "sigma_charge_C": row.get("sigma_q_C")},
            }
            for row in records
        ]
        config = load_config("configs/default.yaml")
        elementary = config.setdefault("elementary", {})
        elementary["e_bootstrap_samples"] = 0
        elementary["measurement_mc_samples"] = 0
        elementary["null_simulation_samples"] = 0
        elementary["skip_model_comparison"] = True
        elementary["skip_stability_diagnostics"] = True
        elementary["profile_grid_points"] = min(int(elementary.get("profile_grid_points", 800)), 160)
        elementary["tau_lambda_profile_optimize_points"] = 2
        elementary["tau_lambda_optimizer_maxiter"] = 20
        return estimate_elementary_charge(drops, config)
    except Exception as exc:  # pragma: no cover - defensive adapter boundary
        return {"valid": False, "bounded_estimate_available": False, "status": "experimental_adapter_failed", "reason": str(exc)}


def _value(payload: dict[str, Any], key: str, default: Any = ...):
    camel = key.split("_")[0] + "".join(part[:1].upper() + part[1:] for part in key.split("_")[1:])
    if key in payload:
        return payload[key]
    if camel in payload:
        return payload[camel]
    if default is not ...:
        return default
    raise KeyError(key)


def _default_run_dir(video_path: Path) -> Path:
    return Path("runs") / "normal_v2" / video_path.stem


def _video_meta(video_path: Path) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return {"path": str(video_path), "width": width, "height": height, "fps": fps, "frame_count": frame_count, "duration_s": frame_count / fps if fps else 0.0}


def _read_gray_frames(video_path: Path, start_frame: int, end_frame: int) -> dict[int, np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_frame))
    frames: dict[int, np.ndarray] = {}
    for frame_idx in range(int(start_frame), int(end_frame) + 1):
        ok, frame = cap.read()
        if not ok:
            break
        frames[frame_idx] = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cap.release()
    return frames


def _make_bright_local_detector(frames: dict[int, np.ndarray], *, source_start_frame: int):
    def detect(frame_idx: int, predicted: tuple[float, float], radius: float) -> Detection | None:
        gray = frames.get(frame_idx)
        if gray is None:
            return None
        height, width = gray.shape[:2]
        x, y = predicted
        x0 = max(0, int(round(x - radius)))
        y0 = max(0, int(round(y - radius)))
        x1 = min(width, int(round(x + radius + 1)))
        y1 = min(height, int(round(y + radius + 1)))
        crop = gray[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        mask = np.where(crop >= 180, 255, 0).astype(np.uint8)
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
        best = None
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if 4 <= area <= 200:
                cx, cy = centroids[label]
                gx, gy = float(x0 + cx), float(y0 + cy)
                distance = math.hypot(gx - x, gy - y)
                if best is None or distance < best[0]:
                    best = (distance, gx, gy, area)
        if best is None:
            return None
        return Detection(best[1], best[2], mass=float(best[3]), quality=1.0 / (1.0 + best[0]))

    return detect


def _detect_horizontal_grid_lines(video_path: Path, frame_idx: int) -> list[int]:
    frames = _read_gray_frames(video_path, frame_idx, frame_idx)
    gray = next(iter(frames.values()))
    edges = cv2.Canny(gray, 40, 120)
    projection = edges.mean(axis=1)
    if projection.max(initial=0) <= 0:
        return []
    ys = np.where(projection >= max(8.0, float(projection.max()) * 0.35))[0]
    groups: list[list[int]] = []
    for y in ys.tolist():
        if not groups or y - groups[-1][-1] > 3:
            groups.append([int(y)])
        else:
            groups[-1].append(int(y))
    return [int(round(sum(group) / len(group))) for group in groups]


def _detect_change_peaks(video_path: Path, *, fps: float) -> list[ChangePeak]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    stride = max(1, int(round(fps / 6.0)))
    last: np.ndarray | None = None
    scores: list[tuple[int, float]] = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % stride == 0:
            height, width = frame.shape[:2]
            roi = frame[0 : max(1, int(height * 0.25)), int(width * 0.45) : width]
            gray = cv2.resize(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (96, 32))
            if last is not None:
                score = float(np.mean(cv2.absdiff(gray, last)) / 255.0)
                scores.append((frame_idx, score))
            last = gray
        frame_idx += 1
    cap.release()
    if not scores:
        return []
    values = np.asarray([score for _frame, score in scores], dtype=float)
    threshold = max(0.04, float(np.mean(values) + 2.5 * np.std(values)))
    return [ChangePeak(frame_idx=frame, score=score) for frame, score in scores if score >= threshold]


def _physical_config(config: dict[str, Any]) -> PhysicalConfig:
    physics = config.get("physics", {})
    viscosity = config.get("viscosity", {})
    return PhysicalConfig(
        plate_distance_m=float(physics.get("plate_distance_m", 0.005)),
        oil_density_kg_m3=float(physics.get("oil_density_kg_m3", 981.0)),
        gravity_m_s2=float(physics.get("gravity_m_s2", 9.80665)),
        air_viscosity_Pa_s=float(viscosity.get("direct_air_viscosity_Pa_s") or physics.get("air_viscosity_Pa_s", 1.81e-5) or 1.81e-5),
        pressure_Pa=float(physics.get("pressure_Pa", 101325.0)),
        cunningham_b_Pa_m=float(physics.get("cunningham_b_Pa_m", 8.2e-6)),
    )


def _sigma_q(charge_C: float | None, fit: Any) -> float | None:
    if charge_C is None or fit.velocity_m_s in (None, 0):
        return None
    duration = 1.0
    if fit.used_frame_indices:
        duration = max(1.0, float(max(fit.used_frame_indices) - min(fit.used_frame_indices)))
    relative = 0.02 + min(0.50, float(fit.rmse_px or 0.0) / max(abs(float(fit.slope_y_px_s or 0.0)) * duration, 1e-9))
    return abs(float(charge_C)) * relative


def _write_track_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = ["frame_idx", "time_s", "status", "x", "y", "predicted_x", "predicted_y", "missing_count", "frame_gap_since_detection", "flags"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in keys})


def _layers(meta: dict[str, Any], grid_lines_y: list[int], tracking: dict[str, Any], q_record: NormalQRecord) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "normal_v2",
        "frame": meta,
        "layers": [
            {"id": "horizontal_grid_lines", "type": "line_set", "orientation": "horizontal", "positions_px": grid_lines_y},
            {"id": "normal_track", "type": "status_point_series", "points": tracking["points"]},
        ],
        "q_record_id": q_record.record_id,
    }


def _single_report(result: dict[str, Any]) -> str:
    record = result["q_record"]
    lines = [
        "# Normal Single Measurement Report",
        "",
        f"- record_id: {record['record_id']}",
        f"- valid: {record['valid']}",
        f"- q_C: {record.get('q_C')}",
        f"- sigma_q_C: {record.get('sigma_q_C')}",
    ]
    return "\n".join(lines) + "\n"
