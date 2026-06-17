import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from millikan_ai.config import load_config, save_config


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


def _make_normal_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(90):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (30, y), (230, y), (255, 255, 255), 2)
        y = 48 + idx * 0.55 + np.sin(idx / 3) * 0.35
        cv2.circle(frame, (92, int(round(y))), 4, (255, 255, 255), -1)
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


def test_desktop_worker_runs_normal_single_drop_and_counts_usable_q(tmp_path: Path):
    video = tmp_path / "normal.mp4"
    _make_normal_video(video)
    config = _fast_config()
    config["project"]["run_root"] = str(tmp_path / "runs")
    config["roi"]["microscope_roi"] = [20, 20, 240, 200]
    config["normal_mode"]["min_fit_points"] = 8
    config_path = tmp_path / "normal_config.yaml"
    save_config(config, config_path)
    run_dir = tmp_path / "normal_run"

    messages = _send_worker(
        {
            "id": "normal",
            "op": "normal.runSingleDrop",
            "payload": {
                "video_path": str(video),
                "config_path": str(config_path),
                "run_dir": str(run_dir),
                "balance_voltage_V": 240.0,
                "target": {"x": 92.0, "y": 48.0, "frame": 0},
                "confirmed_window": {"fall_start_frame": 0, "fall_end_frame": 70},
            },
        }
    )

    result = messages[-1]
    assert result["type"] == "result"
    payload = result["payload"]
    assert payload["manifest"]["mode"] == "normal_balance_fall"
    assert payload["manifest"]["counts"]["detected_tracking_points"] >= 20
    assert payload["manifest"]["counts"]["usable_q_records"] in {0, 1}
    assert "normal_result" in payload["artifacts"]
    assert Path(payload["artifacts"]["normal_result"]["files"]["normal_track_csv"]).exists()


def test_desktop_worker_normal_estimate_elementary_uses_dynamic_q_records():
    q_records = [
        {"record_id": "q1", "q_C": 2 * 1.602e-19, "sigma_q_C": 0.03e-19, "usable_for_inversion": True, "selected": True},
        {"record_id": "q2", "q_C": 3 * 1.602e-19, "sigma_q_C": 0.03e-19, "usable_for_inversion": True, "selected": True},
        {"record_id": "q3", "q_C": 5 * 1.602e-19, "sigma_q_C": 0.03e-19, "usable_for_inversion": True, "selected": True},
    ]

    result = _send_worker(
        {
            "id": "normal-e",
            "op": "normal.estimateElementary",
            "payload": {
                "q_records": q_records,
                "config_overrides": {
                    "elementary": {
                        "e_bootstrap_samples": 0,
                        "measurement_mc_samples": 0,
                        "null_simulation_samples": 0,
                        "skip_stability_diagnostics": True,
                    }
                },
            },
        }
    )[-1]

    assert result["type"] == "result"
    assert result["payload"]["usable_q_count"] == 3
    assert result["payload"]["normal_algorithm"]["valid"] is True
