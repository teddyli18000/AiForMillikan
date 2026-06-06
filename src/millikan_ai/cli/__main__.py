from __future__ import annotations

import argparse
import json
from pathlib import Path

from millikan_ai.api import AnalysisRequest, ManualPlatformInput, analyze_video, manual_platform_row, parse_manual_platform_spec, prepare_analysis_config
from millikan_ai.config import load_config
from millikan_ai.pipeline import validate_run, write_summary
from millikan_ai.video.reader import inspect_video, save_diagnostic_frame


def _manual_platform_row(start_frame: int, end_frame: int, voltage: float, fps: float, index: int, frame_count: int | None = None) -> dict[str, object]:
    return manual_platform_row(ManualPlatformInput(start_frame, end_frame, voltage, source="manual_cli"), fps, index, frame_count)


def _parse_platform_spec(spec: str, fps: float, index: int, frame_count: int | None = None) -> dict[str, object]:
    return manual_platform_row(parse_manual_platform_spec(spec, source="manual_cli"), fps, index, frame_count)


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


def _prompt_platform_inputs(fps: float, frame_count: int) -> list[ManualPlatformInput]:
    print(f"video frames: 0..{max(0, frame_count - 1)}, fps={fps:g}")
    count = _prompt_int("voltage platform count")
    if count <= 0:
        raise ValueError("voltage platform count must be positive")
    platforms: list[ManualPlatformInput] = []
    previous_end = -1
    for offset in range(count):
        remaining = max(1, count - offset)
        default_start = previous_end + 1
        default_end = frame_count - 1 if offset == count - 1 else max(default_start, default_start + ((frame_count - default_start) // remaining) - 1)
        print(f"platform {offset + 1}")
        start_frame = _prompt_int("  start frame", default_start)
        end_frame = _prompt_int("  end frame", default_end)
        voltage = _prompt_float("  voltage V")
        platforms.append(ManualPlatformInput(start_frame, end_frame, voltage, source="manual_cli"))
        previous_end = end_frame
    return platforms


def _prompt_platform_rows(fps: float, frame_count: int, start_index: int = 1) -> list[dict[str, object]]:
    return [manual_platform_row(platform, fps, index, frame_count) for index, platform in enumerate(_prompt_platform_inputs(fps, frame_count), start=start_index)]


def _prepare_config(args: argparse.Namespace) -> str:
    platforms = [parse_manual_platform_spec(spec, source="manual_cli") for spec in list(args.platform or [])]
    use_interactive = getattr(args, "interactive_platforms", False)
    if not platforms and not use_interactive:
        return args.config
    meta = inspect_video(args.video)
    if use_interactive:
        if platforms:
            print("已有 --platform 输入；继续追加交互输入的平台。")
        platforms.extend(_prompt_platform_inputs(meta.fps, meta.frame_count))
    target = prepare_analysis_config(args.video, args.config, platforms)
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
    result = analyze_video(AnalysisRequest(args.video, config_path, args.run_dir))
    print(f"run_dir={result.run_dir}")
    print(f"config={result.config_path}")
    errors = result.validation_errors
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
    result = analyze_video(AnalysisRequest(args.video, config_path, args.run_dir))
    report = Path(result.run_dir) / "analysis_report.md"
    print(f"run_dir={result.run_dir}")
    print(f"config={result.config_path}")
    print(f"analysis_report={report}")
    errors = result.validation_errors
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
