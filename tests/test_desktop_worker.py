import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from millikan_ai.config import load_config, save_config
from millikan_ai.normal.config import normal_config
from millikan_ai.normal.grid import calibrate_grid


def _fast_config() -> dict:
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 0
    config["elementary"]["measurement_mc_samples"] = 0
    config["elementary"]["null_simulation_samples"] = 0
    config["physics"]["random_mc_samples"] = 30
    config["segment"]["velocity_bootstrap_samples_quick"] = 0
    return config


def _make_synthetic_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (30, y), (230, y), (255, 255, 255), 2)
        cv2.circle(frame, (90, int(50 + idx * 0.35)), 4, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def _make_normal_synthetic_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (24, y), (296, y), (190, 190, 190), 1)
        cv2.circle(frame, (92, int(82 + idx * 0.24)), 5, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def _make_crossing_normal_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (24, y), (296, y), (190, 190, 190), 1)
        cv2.circle(frame, (92, int(52 + idx * 0.5)), 5, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def _make_blue_grid_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for _idx in range(20):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 60, 90, 120, 150, 180, 210]:
            cv2.line(frame, (24, y), (296, y), (255, 150, 90), 2)
        writer.write(frame)
    writer.release()


def _send_worker(message: dict) -> list[dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd() / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "millikan_ai.desktop_worker"],
        input=json.dumps(message, ensure_ascii=False) + "\n",
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_desktop_worker_inspects_video(tmp_path: Path):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)

    messages = _send_worker({"id": "inspect", "op": "video.inspect", "payload": {"videoPath": str(video)}})

    assert messages[-1]["type"] == "result"
    assert messages[-1]["payload"]["metadata"]["readable"] is True
    assert messages[-1]["payload"]["metadata"]["frame_count"] == 120


def test_normal_grid_detects_blue_screen_lines(tmp_path: Path):
    video = tmp_path / "blue_grid.mp4"
    _make_blue_grid_video(video)
    cfg = normal_config({"grid": {"measurement_distance_m": 0.0015, "min_horizontal_coverage": 0.55}})

    grid = calibrate_grid(str(video), cfg)

    assert grid["valid"] is True
    assert len(grid["grid_lines_y"]) >= 7
    assert grid["second_line_y"] == 60
    assert grid["penultimate_line_y"] == 180


def test_desktop_worker_runs_analysis_and_loads_artifacts(tmp_path: Path):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)
    config = _fast_config()
    config["project"]["run_root"] = str(tmp_path / "runs")
    config["roi"]["microscope_roi"] = [20, 20, 240, 200]
    config["segment"]["stable_min_duration_s"] = 0.5
    config["segment"]["min_valid_points"] = 10
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)
    run_dir = tmp_path / "run"

    messages = _send_worker(
        {
            "id": "run",
            "op": "analysis.run",
            "payload": {
                "video_path": str(video),
                "config_path": str(config_path),
                "run_dir": str(run_dir),
                "manual_platforms": [
                    {"startFrame": 0, "endFrame": 59, "voltageV": 0.0, "source": "manual_ui"},
                    {"startFrame": 60, "endFrame": 119, "voltageV": 200.0, "source": "manual_ui"},
                ],
            },
        }
    )

    assert any(message["type"] == "progress" for message in messages)
    result = messages[-1]
    assert result["type"] == "result"
    assert result["payload"]["validation_errors"] == []
    assert result["payload"]["artifacts"]["manifest"]["schema_version"] == 1
    assert result["payload"]["artifacts"]["plots_data"]["schema_version"] == 2

    loaded = _send_worker({"id": "load", "op": "analysis.loadRun", "payload": {"runDir": str(run_dir)}})[-1]
    assert loaded["payload"]["artifacts"]["run_dir"] == str(run_dir)


def test_desktop_worker_normal_session_measurement_and_inversion(tmp_path: Path):
    video = tmp_path / "normal_synthetic.mp4"
    _make_normal_synthetic_video(video)
    session_base = tmp_path / "normal_session"
    overrides = {
        "session": {"session_root": str(session_base), "run_root": str(tmp_path / "normal_runs")},
        "grid": {"measurement_distance_m": 0.0015, "mask_dilate_px": 3},
        "tracking": {"minmass": 20, "memory_frames": 4, "grid_occlusion_radius_px": 1},
        "fit": {"min_points": 8, "min_duration_s": 0.4, "min_displacement_px": 2.0, "min_r2": 0.2},
    }

    inspected = _send_worker(
        {
            "id": "inspect-normal",
            "op": "normal.inspectVideo",
            "payload": {"video_path": str(video)},
        }
    )[-1]
    assert inspected["type"] == "result"
    assert inspected["payload"]["metadata"]["readable"] is True

    prepared_messages = _send_worker(
        {
            "id": "prepare",
            "op": "normal.prepareVideo",
            "payload": {"video_path": str(video), "config_overrides": overrides},
        }
    )
    assert any(message["type"] == "progress" and message["payload"]["operation"] == "prepare_video" for message in prepared_messages)
    prepared = prepared_messages[-1]
    assert prepared["type"] == "result"
    payload = prepared["payload"]
    assert payload["metadata"]["readable"] is True
    assert payload["grid"]["valid"] is True
    assert payload["session"]["counts"]["total"] == 0
    assert "config" in payload
    session_root = Path(payload["session_root"])
    assert session_root.parent == session_base

    fresh = _send_worker({"id": "fresh-normal", "op": "normal.initialize", "payload": {"config_overrides": overrides}})[-1]
    assert fresh["type"] == "result"
    assert fresh["payload"]["session"]["session_id"] != payload["session"]["session_id"]
    assert fresh["payload"]["session"]["counts"]["total"] == 0

    for index in range(3):
        prepared = _send_worker(
            {
                "id": f"prepare-{index}",
                "op": "normal.prepareVideo",
                "payload": {"video_path": str(video), "session_root": str(session_root), "config_overrides": overrides},
            }
        )[-1]
        payload = prepared["payload"]
        confirmed = _send_worker(
            {
                "id": f"confirm-{index}",
                "op": "normal.confirmBoundary",
                "payload": {
                    "session_root": str(session_root),
                    "boundary": {"zero_v_start_s": 0.1, "zero_v_end_s": 2.8, "source": "test_manual"},
                },
            }
        )[-1]
        assert confirmed["type"] == "result"
        assert confirmed["payload"]["active_video"]["state"] == "boundary_confirmed"
        assert confirmed["payload"]["active_video"]["boundary"]["selection_window"]["end_s"] <= 0.6

        if index == 0:
            out_of_range = _send_worker(
                {
                    "id": "select-out-of-range",
                    "op": "normal.selectTarget",
                    "payload": {
                        "session_root": str(session_root),
                        "balance_voltage_V": 239.0,
                        "balance_confirmed": True,
                        "target": {
                            "target_frame": 90,
                            "target_time_s": 3.0,
                            "source_center": {"x": 92.0, "y": 83.0},
                            "source_video_box": {"x": 78.0, "y": 69.0, "width": 28.0, "height": 28.0},
                        },
                        "parameter_overrides": overrides,
                    },
                }
            )[-1]
            assert out_of_range["type"] == "error"

        selected = _send_worker(
            {
                "id": f"select-{index}",
                "op": "normal.selectTarget",
                "payload": {
                    "session_root": str(session_root),
                    "balance_voltage_V": 239.0,
                    "balance_confirmed": True,
                    "target": {
                        "target_frame": 3,
                        "target_time_s": 0.1,
                        "source_center": {"x": 92.0, "y": 83.0},
                        "source_video_box": {"x": 78.0, "y": 69.0, "width": 28.0, "height": 28.0},
                    },
                    "parameter_overrides": overrides,
                },
            }
        )[-1]
        assert selected["type"] == "result"
        assert selected["payload"]["active_video"]["state"] == "target_selected"

        measured = _send_worker(
            {
                "id": f"measure-{index}",
                "op": "normal.saveMeasurement",
                "payload": {
                    "session_root": str(session_root),
                    "config_overrides": overrides,
                },
            }
        )[-1]
        assert measured["type"] == "result"
        record = measured["payload"]["record"]
        assert record["valid"] is False
        assert record["q_valid"] is True
        assert record["q_C"] > 0
        assert record["sigma_q_C"] > 0
        assert record["kept"] is False

        blocked = _send_worker(
            {
                "id": f"blocked-accept-{index}",
                "op": "normal.updateRecordSelection",
                "payload": {"session_root": str(session_root), "record_id": record["record_id"], "kept": True},
            }
        )[-1]
        if record["crossings"]:
            assert blocked["type"] == "error"
            for crossing in record["crossings"]:
                review = _send_worker(
                    {
                        "id": f"prepare-crossing-{index}-{crossing['event_id']}",
                        "op": "normal.prepareCrossingReview",
                        "payload": {"session_root": str(session_root), "record_id": record["record_id"], "event_id": crossing["event_id"]},
                    }
                )[-1]
                assert review["type"] == "result"
                assert Path(review["payload"]["event"]["review_clip_path"]).exists()
                reviewed = _send_worker(
                    {
                        "id": f"review-crossing-{index}-{crossing['event_id']}",
                        "op": "normal.reviewCrossing",
                        "payload": {"session_root": str(session_root), "record_id": record["record_id"], "event_id": crossing["event_id"], "result": "same_drop"},
                    }
                )[-1]
                assert reviewed["type"] == "result"

        accepted = _send_worker(
            {
                "id": f"accept-{index}",
                "op": "normal.updateRecordSelection",
                "payload": {"session_root": str(session_root), "record_id": record["record_id"], "kept": True},
            }
        )[-1]
        assert accepted["type"] == "result"
        accepted_record = [row for row in accepted["payload"]["records"] if row["record_id"] == record["record_id"]][0]
        assert accepted_record["status"] == "accepted"
        assert accepted_record["kept"] is True

    inverted = _send_worker(
        {
            "id": "invert",
            "op": "normal.runInversion",
            "payload": {"session_root": str(session_root), "config_overrides": overrides},
        }
    )[-1]
    assert inverted["type"] == "result"
    assert inverted["payload"]["session"]["eligible_for_inversion"] is True
    assert inverted["payload"]["inversion"]["valid_q_count"] == 3
    assert "quantized_favored" not in inverted["payload"]["inversion"].get("comparison", {})
    assert inverted["payload"]["inversion"]["candidates"]


def test_normal_different_crossing_blocks_acceptance_and_inversion(tmp_path: Path):
    video = tmp_path / "crossing_synthetic.mp4"
    _make_crossing_normal_video(video)
    session_base = tmp_path / "normal_crossing_session"
    overrides = {
        "session": {"session_root": str(session_base), "run_root": str(tmp_path / "normal_crossing_runs")},
        "grid": {"measurement_distance_m": 0.0015, "mask_dilate_px": 1},
        "tracking": {"minmass": 20, "memory_frames": 4, "grid_occlusion_radius_px": 1},
        "fit": {"min_points": 8, "min_duration_s": 0.4, "min_displacement_px": 2.0, "min_r2": 0.2},
    }

    prepared = _send_worker(
        {
            "id": "prepare-crossing-block",
            "op": "normal.prepareVideo",
            "payload": {"video_path": str(video), "config_overrides": overrides},
        }
    )[-1]
    assert prepared["type"] == "result"
    assert prepared["payload"]["grid"]["valid"] is True
    session_root = Path(prepared["payload"]["session_root"])

    confirmed = _send_worker(
        {
            "id": "confirm-crossing-block",
            "op": "normal.confirmBoundary",
            "payload": {
                "session_root": str(session_root),
                "boundary": {"zero_v_start_s": 0.0, "zero_v_end_s": 3.8, "source": "test_manual"},
            },
        }
    )[-1]
    assert confirmed["type"] == "result"

    selected = _send_worker(
        {
            "id": "select-crossing-block",
            "op": "normal.selectTarget",
            "payload": {
                "session_root": str(session_root),
                "balance_voltage_V": 239.0,
                "balance_confirmed": True,
                "target": {
                    "target_frame": 0,
                    "target_time_s": 0.0,
                    "source_center": {"x": 92.0, "y": 52.0},
                    "source_video_box": {"x": 78.0, "y": 38.0, "width": 28.0, "height": 28.0},
                },
                "parameter_overrides": overrides,
            },
        }
    )[-1]
    assert selected["type"] == "result"

    measured = _send_worker(
        {
            "id": "measure-crossing-block",
            "op": "normal.saveMeasurement",
            "payload": {"session_root": str(session_root), "config_overrides": overrides},
        }
    )[-1]
    assert measured["type"] == "result"
    record = measured["payload"]["record"]
    assert record["crossings"], "synthetic crossing video should require human review"

    crossing = record["crossings"][0]
    review = _send_worker(
        {
            "id": "prepare-crossing-block-review",
            "op": "normal.prepareCrossingReview",
            "payload": {"session_root": str(session_root), "record_id": record["record_id"], "event_id": crossing["event_id"]},
        }
    )[-1]
    assert review["type"] == "result"
    assert Path(review["payload"]["event"]["review_clip_path"]).exists()

    rejected = _send_worker(
        {
            "id": "reject-crossing-block",
            "op": "normal.reviewCrossing",
            "payload": {
                "session_root": str(session_root),
                "record_id": record["record_id"],
                "event_id": crossing["event_id"],
                "result": "different_drop",
            },
        }
    )[-1]
    assert rejected["type"] == "result"
    assert rejected["payload"]["record"]["status"] == "rejected_crossing_identity"
    assert rejected["payload"]["session"]["active_video"]["state"] == "boundary_confirmed"
    assert rejected["payload"]["session"]["active_video"]["adjustment"]["record_id"] == record["record_id"]

    blocked_accept = _send_worker(
        {
            "id": "accept-rejected-crossing",
            "op": "normal.updateRecordSelection",
            "payload": {"session_root": str(session_root), "record_id": record["record_id"], "kept": True},
        }
    )[-1]
    assert blocked_accept["type"] == "error"

    inverted = _send_worker(
        {
            "id": "invert-rejected-crossing",
            "op": "normal.runInversion",
            "payload": {"session_root": str(session_root), "config_overrides": overrides},
        }
    )[-1]
    assert inverted["type"] == "result"
    assert inverted["payload"]["inversion"]["status"] == "insufficient_eligible_records"
