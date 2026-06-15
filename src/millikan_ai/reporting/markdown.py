from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


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


def _drop_result_rows(multi_drop_results: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for drop in multi_drop_results.get("drops", []):
        result = drop.get("result", {}) or {}
        fit = drop.get("fit", {}) or {}
        rows.append(
            {
                "drop_id": drop.get("drop_id", ""),
                "track_id": drop.get("track_id", ""),
                "valid": drop.get("valid"),
                "charge_abs_C": result.get("charge_abs_C"),
                "sigma_charge_C": result.get("sigma_charge_C"),
                "radius_m": result.get("radius_m"),
                "alpha": fit.get("alpha"),
                "gamma": fit.get("gamma"),
                "flags": ",".join(drop.get("flags", [])),
            }
        )
    return pd.DataFrame(rows)


def write_analysis_report(run_dir: str | Path, config: dict[str, Any]) -> Path:
    root = Path(run_dir)
    output = config["output"]
    diagnostics = _read_json(root / output["diagnostics_json"])
    drop = _read_json(root / output["drop_results_json"])
    multi_drop = _read_json(root / output.get("multi_drop_results_json", "multi_drop_results.json"))
    quality = _read_json(root / output["quality_scores_json"])
    elementary = _read_json(root / output["elementary_charge_result_json"])
    platforms = _read_csv(root / output["platforms_csv"])
    voltage_samples = _read_csv(root / output.get("voltage_samples_csv", "voltage_samples.csv"))
    candidates = _read_csv(root / output["candidate_tracks_summary_csv"])
    velocity_results = _read_csv(root / output.get("platform_velocity_results_csv", "platform_velocity_results.csv"))
    charge_results = _read_csv(root / output.get("drop_charge_results_csv", "drop_charge_results.csv"))
    charge_failures = _read_json(root / output.get("drop_charge_failures_json", "drop_charge_failures.json"))
    model_comparison = _read_json(root / output.get("model_comparison_json", "model_comparison.json"))
    uncertainty = _read_json(root / output.get("uncertainty_details_json", "uncertainty_details.json"))
    drop_result_rows = _drop_result_rows(multi_drop)
    video = diagnostics.get("video", {})
    grid = diagnostics.get("grid", {})
    flags = list(diagnostics.get("flags", [])) + list(drop.get("flags", [])) + list(elementary.get("flags", []))
    valid_drop_count = int(multi_drop.get("valid_drop_count", 0) or 0)
    failed_drop_count = len(charge_failures.get("failures", []))
    if elementary.get("valid"):
        status = "SUCCESS"
    elif valid_drop_count > 0:
        status = "PARTIAL"
    else:
        status = "FAILED"
    e_result = elementary.get("elementary_charge", {}) or {}
    machine_keys = [
        "platform_velocity_results_csv",
        "drop_charge_results_csv",
        "drop_charge_failures_json",
        "multi_drop_results_json",
        "elementary_charge_result_json",
        "model_comparison_json",
        "uncertainty_details_json",
        "visualization_layers_json",
        "run_manifest_json",
    ]

    lines = [
        "# Millikan Analysis Report",
        "",
        "## 运行结论",
        "",
        f"运行状态：{status}",
        f"成功计算 q 的油滴数：{valid_drop_count}",
        f"失败油滴数：{failed_drop_count}",
        f"基本电荷估计：{_fmt(e_result.get('e_hat_C'))} C",
        f"综合 95% 区间：{_fmt(e_result.get('ci_95_C'))}",
        f"量子化证据：{model_comparison.get('evidence_label', 'insufficient')}",
        f"主要警告：{', '.join(flags) if flags else 'none'}",
        "",
        "## 视频与距离标定",
        "",
        f"- 视频路径: `{video.get('path', '')}`",
        f"- 时间来源: `{diagnostics.get('time_source', 'opencv_fps_frame_index')}`",
        f"- 分辨率: `{video.get('width', 0)} x {video.get('height', 0)}`",
        f"- FPS: `{_fmt(video.get('fps', 0))}`",
        f"- 帧数: `{video.get('frame_count', 0)}`",
        f"- 时长: `{_fmt(video.get('duration_s', 0))} s`",
        "- 时间计算: `time_s = frame_idx / fps`",
        "",
        "## 距离标定",
        "",
        f"- microscope ROI: `{diagnostics.get('roi', {}).get('microscope_roi', [])}`",
        f"- voltage display ROI placeholder: `{diagnostics.get('roi', {}).get('voltage_roi', [])}`",
        f"- grid lines y(px): `{grid.get('grid_lines_y', [])}`",
        f"- 有效起点线 y(px): `{grid.get('y_start_px')}`",
        f"- 有效终点线 y(px): `{grid.get('y_end_px')}`",
        f"- 像素距离: `{abs((grid.get('y_end_px') or 0) - (grid.get('y_start_px') or 0))}`",
        f"- 物理距离: `{_fmt(grid.get('measurement_distance_m'))} m`",
        f"- scale_y_m_per_px: `{_fmt(grid.get('scale_y_m_per_px'))}`",
        "",
        "## 电压平台",
        "",
        "当前主线不启用 OCR；电压值来自用户/API 输入，自动边界只提供候选区间。",
        _table(platforms),
        "",
        "## 多油滴结果",
        "",
        f"- total_drops: `{multi_drop.get('num_total_drops', 0)}`",
        f"- valid_drop_count: `{multi_drop.get('valid_drop_count', 0)}`",
        "",
        _table(drop_result_rows, max_rows=20),
        "",
        "## 单颗油滴结果",
        "",
        _table(charge_results, ["drop_id", "track_id", "num_platforms", "validation_level", "radius_m", "charge_abs_C", "sigma_charge_total_C", "warnings"], max_rows=20),
        "",
        "## 基本电荷反演",
        "",
        f"- 使用 q 数量: `{elementary.get('num_used_drops', 0)}`",
        f"- 搜索区间: `{_fmt(e_result.get('search_interval_C'))}`",
        f"- e_hat: `{_fmt(e_result.get('e_hat_C'))}`",
        f"- profile 区间: `{_fmt(e_result.get('profile_ci_95_C'))}`",
        f"- bootstrap 区间: `{_fmt(e_result.get('ci_95_C'))}`",
        f"- harmonic ambiguity: `{elementary.get('harmonic_analysis', {}).get('harmonic_ambiguity')}`",
        f"- flags: `{', '.join(elementary.get('flags', []))}`",
        f"- reason: `{elementary.get('reason', '')}`",
        "",
        _table(pd.DataFrame(elementary.get("drops", [])), ["drop_id", "charge_C", "n_hat", "assignment_probability", "residual_C", "normalized_residual"], max_rows=20),
        "",
        "## 模型比较",
        "",
        f"- 量子化模型预测得分: `{_fmt(model_comparison.get('quantized_elpd'))}`",
        f"- 连续 GMM 预测得分: `{_fmt(model_comparison.get('continuous_elpd'))}`",
        f"- Delta ELPD: `{_fmt(model_comparison.get('delta_elpd'))}`",
        f"- 证据等级: `{model_comparison.get('evidence_label', 'insufficient')}`",
        f"- 连续模型: `{model_comparison.get('continuous_model', '')}`",
        "",
        "## 平台速度结果",
        "",
        _table(velocity_results, ["drop_id", "track_id", "platform_id", "voltage_V", "velocity_m_s", "sigma_velocity_random_m_s", "r2_diagnostic", "warnings"], max_rows=30),
        "",
        "## 误差来源",
        "",
        f"- 随机误差: `{uncertainty.get('random_uncertainty', '')}`",
        f"- 系统误差: `{uncertainty.get('systematic_uncertainty', '')}`",
        "- 本计算按实验约定忽略空气浮力，并采用 Stokes 阻力与给定 Cunningham 修正。",
        "",
        "## 调试警告",
        "",
        _table(pd.DataFrame(charge_failures.get("failures", [])), max_rows=20),
        "",
        "## 机器文件入口",
        "",
    ]
    for key in machine_keys:
        if key in output:
            lines.append(f"- `{output[key]}`")
    target = root / output.get("analysis_report_md", "analysis_report.md")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
