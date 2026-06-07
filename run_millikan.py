from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from millikan_ai.api import AnalysisRequest, AnalysisResult, ManualPlatformInput, analyze_video
from millikan_ai.config import load_config, save_config
from millikan_ai.video.reader import inspect_video


def _clean_path(text: str) -> Path:
    return Path(text.strip().strip('"').strip("'")).expanduser()


def _prompt_path(prompt: str, default: Path | None = None) -> Path:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        text = input(f"{prompt}{suffix}: ").strip()
        if not text and default is not None:
            return default
        path = _clean_path(text)
        if path.exists():
            return path
        print(f"路径不存在: {path}")


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


def _prompt_float_override(prompt: str, default: float) -> float:
    return _prompt_float(prompt, default)


def _prompt_platforms(fps: float, frame_count: int) -> tuple[ManualPlatformInput, ...]:
    print(f"视频帧范围: 0..{max(0, frame_count - 1)}；time_s = frame_idx / {fps:g}")
    count = _prompt_int("电压平台数量")
    if count <= 0:
        raise ValueError("电压平台数量必须大于 0")
    platforms: list[ManualPlatformInput] = []
    previous_end = -1
    for index in range(count):
        default_start = previous_end + 1
        default_end = frame_count - 1 if index == count - 1 else default_start
        print(f"\n平台 {index + 1}")
        start_frame = _prompt_int("  起始帧 start_frame", default_start)
        end_frame = _prompt_int("  结束帧 end_frame", default_end)
        if start_frame < 0 or end_frame < start_frame or end_frame >= frame_count:
            raise ValueError(f"平台帧范围非法: {start_frame}:{end_frame}")
        voltage = _prompt_float("  电压 voltage_V")
        print(f"  时间范围: {start_frame / fps if fps else 0.0:.3f}s -> {end_frame / fps if fps else 0.0:.3f}s")
        platforms.append(ManualPlatformInput(start_frame, end_frame, voltage, source="manual_cli"))
        previous_end = end_frame
    return tuple(platforms)


def _write_interactive_config(config_path: Path, video_path: Path, config: dict) -> Path:
    run_root = Path(config["project"]["run_root"])
    target = run_root / "manual_configs" / f"{video_path.stem}_interactive_params.yaml"
    save_config(config, target)
    return target


def _progress_bar(percent: float, label: str) -> None:
    width = 24
    filled = int(round(width * percent))
    bar = "#" * filled + "." * (width - filled)
    print(f"\r[{bar}] {percent * 100:5.1f}% {label}", end="", flush=True)
    if percent >= 1.0:
        print()


def _confirm_run(video_path: Path, config_path: Path, platforms: tuple[ManualPlatformInput, ...], config: dict) -> bool:
    print("\n运行参数确认")
    print(f"- video: {video_path}")
    print(f"- config: {config_path}")
    print(f"- measurement_distance_m: {config['calibration']['measurement_distance_m']}")
    print(f"- plate_distance_m: {config['physics']['plate_distance_m']}")
    print(f"- voltage_sign: {config['physics']['voltage_sign']}")
    for index, platform in enumerate(platforms, start=1):
        print(f"- P{index:03d}: frames {platform.start_frame}-{platform.end_frame}, voltage={platform.voltage_V:g} V")
    answer = input("开始分析? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def run_interactive() -> int:
    print("Millikan AI 手动平台分析向导")
    video_path = _prompt_path("视频文件路径")
    meta = inspect_video(video_path)
    if not meta.readable:
        print("视频不可读，无法继续。")
        return 2
    print(f"视频: {meta.width}x{meta.height}, fps={meta.fps:g}, frames={meta.frame_count}, duration={meta.duration_s:.3f}s")

    config_path = _prompt_path("配置文件路径", ROOT / "configs" / "default.yaml")
    config = load_config(config_path)
    config["calibration"]["measurement_distance_m"] = _prompt_float_override(
        "测量距离 measurement_distance_m", float(config["calibration"]["measurement_distance_m"])
    )
    config["physics"]["plate_distance_m"] = _prompt_float_override("极板距离 plate_distance_m", float(config["physics"]["plate_distance_m"]))
    config["physics"]["voltage_sign"] = _prompt_float_override("电压方向 voltage_sign", float(config["physics"]["voltage_sign"]))
    effective_config_path = _write_interactive_config(config_path, video_path, config)

    try:
        platforms = _prompt_platforms(meta.fps, meta.frame_count)
    except ValueError as exc:
        print(f"输入错误: {exc}")
        return 2
    if not _confirm_run(video_path, effective_config_path, platforms, config):
        print("已取消。")
        return 1

    result = analyze_video(
        AnalysisRequest(
            video_path=video_path,
            config_path=effective_config_path,
            manual_platforms=platforms,
            progress_callback=_progress_bar,
        )
    )
    report = result.run_dir / "analysis_report.md"
    manifest = result.run_dir / "run_manifest.json"
    print("\n分析完成")
    print(f"- run_dir: {result.run_dir}")
    print(f"- analysis_report: {report}")
    print(f"- run_manifest: {manifest}")
    overlay = result.run_dir / "overlay_best_track.mp4"
    if overlay.exists():
        print(f"- overlay: {overlay}")
    if result.validation_errors:
        print(f"- validation_errors: {result.validation_errors}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run_interactive())
