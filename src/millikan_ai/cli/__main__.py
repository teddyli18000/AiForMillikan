from __future__ import annotations

import argparse
import json
from pathlib import Path

from millikan_ai.config import load_config, save_config
from millikan_ai.pipeline import run_pipeline, validate_run, write_summary
from millikan_ai.video.reader import inspect_video, save_diagnostic_frame


def _manual_platform_row(start_frame: int, end_frame: int, voltage: float, fps: float, index: int, frame_count: int | None = None) -> dict[str, object]:
    if start_frame < 0 or end_frame < start_frame:
        raise ValueError(f"invalid platform frame range: {start_frame}:{end_frame}")
    if frame_count is not None and frame_count > 0 and end_frame >= frame_count:
        raise ValueError(f"platform end_frame {end_frame} exceeds video last frame {frame_count - 1}")
    return {
        "platform_id": f"P{index:03d}",
        "start_frame": start_frame,
        "end_frame": end_frame,
        "start_time_s": start_frame / fps if fps else 0.0,
        "end_time_s": end_frame / fps if fps else 0.0,
        "voltage_V": voltage,
        "voltage_confidence": 1.0,
        "source": "manual_cli",
    }


def _parse_platform_spec(spec: str, fps: float, index: int, frame_count: int | None = None) -> dict[str, object]:
    parts = [part.strip() for part in spec.split(":")]
    if len(parts) != 3:
        raise ValueError(f"platform spec must be START_FRAME:END_FRAME:VOLTAGE, got: {spec}")
    return _manual_platform_row(int(parts[0]), int(parts[1]), float(parts[2]), fps, index, frame_count)


def _prompt_int(prompt: str, default: int | None = None) -> int:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        text = input(f"{prompt}{suffix}: ").strip()
        if not text and default is not None:
            return default
        try:
            return int(text)
        except ValueError:
            print("请输入整数。")


def _prompt_float(prompt: str, default: float | None = None) -> float:
    suffix = f" [{default:g}]" if default is not None else ""
    while True:
        text = input(f"{prompt}{suffix}: ").strip()
        if not text and default is not None:
            return default
        try:
            return float(text)
        except ValueError:
            print("请输入数字。")


def _prompt_platform_rows(fps: float, frame_count: int, start_index: int = 1) -> list[dict[str, object]]:
    print(f"video frames: 0..{max(0, frame_count - 1)}, fps={fps:g}")
    count = _prompt_int("voltage platform count")
    if count <= 0:
        raise ValueError("voltage platform count must be positive")
    rows: list[dict[str, object]] = []
    previous_end = -1
    for offset in range(count):
        platform_index = start_index + offset
        remaining = max(1, count - offset)
        default_start = previous_end + 1
        default_end = frame_count - 1 if offset == count - 1 else max(default_start, default_start + ((frame_count - default_start) // remaining) - 1)
        print(f"platform {platform_index}")
        start_frame = _prompt_int("  start frame", default_start)
        end_frame = _prompt_int("  end frame", default_end)
        voltage = _prompt_float("  voltage V")
        rows.append(_manual_platform_row(start_frame, end_frame, voltage, fps, platform_index, frame_count))
        previous_end = end_frame
    return rows


def _prepare_config(args: argparse.Namespace) -> str:
    specs = list(args.platform or [])
    use_interactive = getattr(args, "interactive_platforms", False)
    if not specs and not use_interactive:
        return args.config
    config = load_config(args.config)
    meta = inspect_video(args.video)
    rows = [_parse_platform_spec(spec, meta.fps, idx, meta.frame_count) for idx, spec in enumerate(specs, start=1)]
    if use_interactive:
        if rows:
            print("已有 --platform 输入；继续追加交互输入的平台。")
        rows.extend(_prompt_platform_rows(meta.fps, meta.frame_count, len(rows) + 1))
    config["manual_platforms"] = rows
    target = Path(config["project"]["run_root"]) / "manual_configs" / f"{Path(args.video).stem}_manual_platforms.yaml"
    save_config(config, target)
    return str(target)


def _cmd_inspect(args: argparse.Namespace) -> int:
    meta = inspect_video(args.video)
    print(json.dumps(meta.to_dict(), indent=2, ensure_ascii=False))
    if args.save_frame:
        target = save_diagnostic_frame(args.video, Path(args.save_frame))
        print(f"diagnostic_frame={target}")
    return 0 if meta.readable else 1


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        config_path = _prepare_config(args)
    except ValueError as exc:
        print(f"platform_input_error={exc}")
        return 2
    run_dir = run_pipeline(args.video, config_path, args.run_dir)
    print(f"run_dir={run_dir}")
    print(f"config={config_path}")
    errors = validate_run(run_dir, config_path)
    if errors:
        print("validation_errors=" + json.dumps(errors, ensure_ascii=False))
        return 2
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    try:
        config_path = _prepare_config(args)
    except ValueError as exc:
        print(f"platform_input_error={exc}")
        return 2
    run_dir = run_pipeline(args.video, config_path, args.run_dir)
    report = Path(run_dir) / "analysis_report.md"
    print(f"run_dir={run_dir}")
    print(f"config={config_path}")
    print(f"analysis_report={report}")
    errors = validate_run(run_dir, config_path)
    if errors:
        print("validation_errors=" + json.dumps(errors, ensure_ascii=False))
        return 2
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    errors = validate_run(args.run_dir, args.config)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({"valid": True, "errors": []}, indent=2, ensure_ascii=False))
    return 0


def _cmd_summarize(args: argparse.Namespace) -> int:
    summary = write_summary(args.run_dir, load_config(args.config) if args.config else None)
    print(summary.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="millikan-ai")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("video")
    inspect.add_argument("--save-frame")
    inspect.set_defaults(func=_cmd_inspect)
    run = sub.add_parser("run")
    run.add_argument("--video", required=True)
    run.add_argument("--config", default="configs/default.yaml")
    run.add_argument("--run-dir")
    run.add_argument("--non-interactive", action="store_true")
    run.add_argument("--platform", action="append", help="Manual platform as START_FRAME:END_FRAME:VOLTAGE; repeat for multiple platforms.")
    run.add_argument("--interactive-platforms", action="store_true", help="Prompt for manual platform ranges before running.")
    run.set_defaults(func=_cmd_run)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--video", required=True)
    analyze.add_argument("--config", default="configs/default.yaml")
    analyze.add_argument("--run-dir")
    analyze.add_argument("--platform", action="append", help="Manual platform as START_FRAME:END_FRAME:VOLTAGE; repeat for multiple platforms.")
    analyze.add_argument("--interactive-platforms", action="store_true", help="Prompt for manual platform ranges before running.")
    analyze.set_defaults(func=_cmd_analyze)
    validate = sub.add_parser("validate")
    validate.add_argument("--run-dir", required=True)
    validate.add_argument("--config", default="configs/default.yaml")
    validate.set_defaults(func=_cmd_validate)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--run-dir", required=True)
    summarize.add_argument("--config", default=None)
    summarize.set_defaults(func=_cmd_summarize)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
