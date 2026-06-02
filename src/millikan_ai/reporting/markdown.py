from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, float):
        if abs(value) >= 1e4 or (value != 0 and abs(value) < 1e-3):
            return f"{value:.6e}"
        return f"{value:.6g}"
    return str(value)


def _table(frame: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 20) -> str:
    if frame.empty:
        return "_无数据_\n"
    view = frame[columns] if columns else frame
    view = view.head(max_rows)
    headers = list(view.columns)
    lines = ["|" + "|".join(headers) + "|", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in view.to_dict("records"):
        lines.append("|" + "|".join(_fmt(row.get(column, "")) for column in headers) + "|")
    return "\n".join(lines) + "\n"


def _config_lines(config: dict[str, Any]) -> list[str]:
    rows = []
    for section, values in config.items():
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, dict):
                    for nested_key, nested_value in value.items():
                        rows.append(f"|`{section}.{key}.{nested_key}`|`{_fmt(nested_value)}`|")
                else:
                    rows.append(f"|`{section}.{key}`|`{_fmt(value)}`|")
        else:
            rows.append(f"|`{section}`|`{_fmt(values)}`|")
    return rows


def write_analysis_report(run_dir: str | Path, config: dict[str, Any]) -> Path:
    root = Path(run_dir)
    output = config["output"]
    diagnostics = _read_json(root / output["diagnostics_json"])
    drop = _read_json(root / output["drop_results_json"])
    quality = _read_json(root / output["quality_scores_json"])
    elementary = _read_json(root / output["elementary_charge_result_json"])
    platforms = _read_csv(root / output["platforms_csv"])
    voltage_samples = _read_csv(root / output.get("voltage_samples_csv", "voltage_samples.csv"))
    candidates = _read_csv(root / output["candidate_tracks_summary_csv"])
    segments = _read_csv(root / output["best_track_segments_csv"])
    video = diagnostics.get("video", {})
    grid = diagnostics.get("grid", {})
    flags = list(diagnostics.get("flags", [])) + list(drop.get("flags", [])) + list(elementary.get("flags", []))
    valid_for_q = bool(drop.get("valid"))
    valid_video = bool(video.get("readable")) and bool(grid.get("scale_y_m_per_px")) and diagnostics.get("platform_count", 0) >= 2 and valid_for_q

    lines = [
        "# Millikan 单油滴视频分析报告",
        "",
        "## 结论",
        "",
        f"- 视频是否合法: {str(valid_video).lower()}",
        f"- 是否满足 q 计算条件: {str(valid_for_q).lower()}",
        f"- 主要 flags: {', '.join(flags) if flags else 'none'}",
        f"- 有效油滴数量: {1 if valid_for_q else 0}",
        "",
        "## 输入与参数",
        "",
        f"- 视频路径: `{video.get('path', '')}`",
        f"- 时间来源: `{diagnostics.get('time_source', 'opencv_fps_frame_index')}`",
        "",
        "|参数|值|",
        "|---|---|",
        *_config_lines(config),
        "",
        "## 视频检查",
        "",
        f"- 分辨率: `{video.get('width', 0)} x {video.get('height', 0)}`",
        f"- FPS: `{_fmt(video.get('fps', 0))}`",
        f"- 帧数: `{video.get('frame_count', 0)}`",
        f"- 时长: `{_fmt(video.get('duration_s', 0))} s`",
        "- 时间计算: `time_s = frame_idx / fps`",
        "",
        "## 距离标定",
        "",
        f"- microscope ROI: `{diagnostics.get('roi', {}).get('microscope_roi', [])}`",
        f"- voltage ROI: `{diagnostics.get('roi', {}).get('voltage_roi', [])}`",
        f"- grid lines y(px): `{grid.get('grid_lines_y', [])}`",
        f"- 有效起点线 y(px): `{grid.get('y_start_px')}`",
        f"- 有效终点线 y(px): `{grid.get('y_end_px')}`",
        f"- 像素距离: `{abs((grid.get('y_end_px') or 0) - (grid.get('y_start_px') or 0))}`",
        f"- 物理距离: `{_fmt(grid.get('measurement_distance_m'))} m`",
        f"- scale_y_m_per_px: `{_fmt(grid.get('scale_y_m_per_px'))}`",
        "",
        "## 电压 OCR 与平台",
        "",
        "### OCR 采样",
        "",
        _table(voltage_samples, ["frame_idx", "time_s", "voltage_V", "confidence", "source", "raw_text", "accepted", "reject_reason"], max_rows=12),
        "",
        "### 电压平台",
        "",
        _table(platforms),
        "",
        "## 最佳油滴轨迹",
        "",
        _table(candidates, max_rows=10),
        "",
        f"- overlay: `{root / output['overlay_mp4']}`",
        "",
        "## 稳定速度段",
        "",
        _table(segments),
        "",
        "## q 计算",
        "",
        f"- 方法: `{drop.get('method', '')}`",
        f"- valid: `{drop.get('valid')}`",
        f"- quality_score: `{_fmt(drop.get('quality_score'))}`",
        f"- alpha: `{_fmt(drop.get('fit', {}).get('alpha'))}`",
        f"- beta: `{_fmt(drop.get('fit', {}).get('beta'))}`",
        f"- radius_m: `{_fmt(drop.get('result', {}).get('radius_m'))}`",
        f"- charge_C: `{_fmt(drop.get('result', {}).get('charge_C'))}`",
        f"- charge_abs_C: `{_fmt(drop.get('result', {}).get('charge_abs_C'))}`",
        f"- sigma_charge_C: `{_fmt(drop.get('result', {}).get('sigma_charge_C'))}`",
        "",
        "## 元电荷反演",
        "",
        f"- valid: `{elementary.get('valid')}`",
        f"- flags: `{', '.join(elementary.get('flags', []))}`",
        f"- reason: `{elementary.get('reason', '')}`",
        f"- result: `{elementary.get('elementary_charge', {})}`",
        "",
        "## 质量筛选",
        "",
        f"- ml_training: `{quality.get('ml_training', False)}`",
        f"- method: `{quality.get('implemented', '')}`",
        "",
        "## 输出文件",
        "",
    ]
    for key, filename in output.items():
        lines.append(f"- `{key}`: `{root / filename}`")
    target = root / output.get("analysis_report_md", "analysis_report.md")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
