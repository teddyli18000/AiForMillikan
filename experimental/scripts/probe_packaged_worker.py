"""End-to-end probe for the packaged Experimental worker.

Runs the real worker executable through inspect -> analysis -> load -> export and
verifies the produced artifacts. It does not check q or e accuracy.

Usage (from `experimental/`):

    .venv\\Scripts\\python scripts\\probe_packaged_worker.py --worker apps\\desktop\\dist-worker\\millikan-experimental-worker.exe

Omit `--worker` to run the source module instead.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = ROOT.parent / "media" / "videos" / "2u.mp4"


def build_fast_config(source: Path, target: Path) -> None:
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["elementary"]["e_bootstrap_samples"] = 0
    config["elementary"]["measurement_mc_samples"] = 0
    config["elementary"]["null_simulation_samples"] = 0
    config["physics"]["random_mc_samples"] = 30
    config["segment"]["velocity_bootstrap_samples_quick"] = 0
    config["tracking"]["max_drops"] = 3
    config["tracking"]["top_k_seeds"] = 8
    config["tracking"]["seed_sample_frames"] = 3
    target.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def worker_call(command: list[str], env: dict[str, str], op: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    message = json.dumps({"id": "probe", "op": op, "payload": payload}, ensure_ascii=False)
    completed = subprocess.run(
        command,
        input=message + "\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f"{op}: worker exited with {completed.returncode}\n{completed.stderr[-4000:]}")
    messages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    terminal = [message for message in messages if message.get("type") in {"result", "error"}]
    if not terminal:
        raise SystemExit(f"{op}: no result or error message\n{completed.stdout[-4000:]}")
    last = terminal[-1]
    if last["type"] == "error":
        raise SystemExit(f"{op} failed: {last['error']}")
    return last["payload"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, help="Packaged worker executable; omit for the source module.")
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "default.yaml")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    video = args.video.resolve()
    if not video.exists():
        raise SystemExit(f"video not found: {video}")

    command = [str(args.worker.resolve())] if args.worker else [sys.executable, "-m", "millikan_ai.desktop_worker"]

    with tempfile.TemporaryDirectory(prefix="millikan_experimental_probe_") as tmp:
        tmp_path = Path(tmp)
        run_root = tmp_path / "runs"
        export_root = tmp_path / "export"
        config_path = tmp_path / "fast.yaml"
        build_fast_config(args.config, config_path)

        env = {key: value for key, value in os.environ.items()}
        env["MILLIKAN_RUN_ROOT"] = str(run_root)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")]).strip(os.pathsep)

        inspected = worker_call(command, env, "video.inspect", {"video_path": str(video)}, args.timeout)
        metadata = inspected["metadata"]
        if not metadata.get("readable") or metadata.get("frame_count", 0) <= 0:
            raise SystemExit(f"video.inspect returned unusable metadata: {metadata}")

        analysis = worker_call(
            command,
            env,
            "analysis.run",
            {
                "video_path": str(video),
                "config_path": str(config_path),
                "manual_platforms": [
                    {"start_frame": 0, "end_frame": 180, "voltage_V": 0.0, "source": "ci_probe"},
                    {"start_frame": 181, "end_frame": 468, "voltage_V": 175.0, "source": "ci_probe"},
                ],
            },
            args.timeout,
        )
        run_dir = Path(analysis["run_dir"]).resolve()
        if not run_dir.is_relative_to(run_root.resolve()):
            raise SystemExit(f"run directory escaped MILLIKAN_RUN_ROOT: {run_dir}")
        if not (run_dir / "run_manifest.json").exists():
            raise SystemExit(f"run_manifest.json missing in {run_dir}")
        if analysis.get("validation_errors"):
            raise SystemExit(f"validation errors: {analysis['validation_errors']}")
        if not analysis["artifacts"].get("analysis_report_md", "").strip():
            raise SystemExit("analysis_report_md is empty")
        if analysis["artifacts"]["manifest"].get("schema_version") != 1:
            raise SystemExit("unexpected run manifest schema version")

        loaded = worker_call(command, env, "analysis.loadRun", {"run_dir": str(run_dir)}, args.timeout)
        if Path(loaded["artifacts"]["run_dir"]).resolve() != run_dir:
            raise SystemExit("analysis.loadRun returned a different run directory")

        exported = worker_call(
            command,
            env,
            "report.export",
            {"run_dir": str(run_dir), "destination_dir": str(export_root), "mode": "folder"},
            args.timeout,
        )
        if not (export_root / "export_manifest.json").exists():
            raise SystemExit("export_manifest.json missing")
        if not (export_root / "analysis_report.md").exists():
            raise SystemExit("analysis_report.md missing from export")
        if not exported.get("files"):
            raise SystemExit("report.export returned no files")

        reloaded = worker_call(command, env, "analysis.loadRun", {"run_dir": str(run_dir)}, args.timeout)
        if Path(reloaded["artifacts"]["run_dir"]).resolve() != run_dir:
            raise SystemExit("a fresh worker process could not reload the persistent run")

        print(
            json.dumps(
                {
                    "ok": True,
                    "worker": str(args.worker) if args.worker else "source-module",
                    "video": str(video),
                    "run_dir": str(run_dir),
                    "exported_files": len(exported["files"]),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
