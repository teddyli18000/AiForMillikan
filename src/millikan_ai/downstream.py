from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from millikan_ai.elementary.estimate import estimate_elementary_charge
from millikan_ai.physics.charge import compute_drop_result, eta_eff, solve_radius_with_cunningham
from millikan_ai.physics.viscosity import resolve_air_viscosity
from millikan_ai.segments.fitting import fit_track_segments


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _default_run_dir(config: dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return Path(config["project"]["run_root"]) / f"downstream_{stamp}"


def _fit_all_segments(
    trajectories: pd.DataFrame,
    platforms: pd.DataFrame,
    scale_y_m_per_px: float,
    config: dict[str, Any],
) -> pd.DataFrame:
    frames = []
    for _track_id, track in trajectories.groupby("track_id", sort=False):
        frames.append(fit_track_segments(track, platforms, scale_y_m_per_px, config))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _compute_drop_results(drop_segments: pd.DataFrame, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    drops: list[dict[str, Any]] = []
    if not drop_segments.empty:
        for index, (track_id, segments) in enumerate(drop_segments.groupby("track_id", sort=False), start=1):
            result = compute_drop_result(segments, config)
            result["drop_id"] = f"drop_{index:03d}"
            result["track_id"] = str(track_id)
            drops.append(result)
    return drops, {
        "schema_version": 1,
        "num_total_drops": len(drops),
        "valid_drop_count": sum(1 for drop in drops if bool(drop.get("valid"))),
        "drops": drops,
    }


def _write_velocity_results(run_dir: Path, drop_segments: pd.DataFrame, drop_results: list[dict[str, Any]]) -> pd.DataFrame:
    drop_id_by_track = {str(drop.get("track_id", "")): str(drop.get("drop_id", "")) for drop in drop_results}
    rows = []
    for row in drop_segments.to_dict("records") if not drop_segments.empty else []:
        rows.append(
            {
                "drop_id": drop_id_by_track.get(str(row.get("track_id", "")), ""),
                "track_id": row.get("track_id", ""),
                "platform_id": row.get("platform_id", ""),
                "voltage_V": row.get("voltage_V"),
                "velocity_m_s": row.get("vy_m_s"),
                "sigma_velocity_random_m_s": row.get("sigma_vy"),
                "velocity_ci_95_m_s": row.get("velocity_ci_95_m_s"),
                "fit_method": row.get("fit_method", ""),
                "uncertainty_method": row.get("uncertainty_method", ""),
                "num_points": row.get("num_points"),
                "duration_s": row.get("duration_s"),
                "r2_diagnostic": row.get("r2_y"),
                "bootstrap_block_length": row.get("bootstrap_block_length"),
                "bootstrap_block_length_method": row.get("bootstrap_block_length_method"),
                "warnings": row.get("flags", ""),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(run_dir / "platform_velocity_results.csv", index=False)
    return frame


def _write_charge_outputs(run_dir: Path, drop_results: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    failures = []
    for drop in drop_results:
        fit = drop.get("fit", {}) or {}
        result = drop.get("result", {}) or {}
        if bool(drop.get("valid")):
            rows.append(
                {
                    "drop_id": drop.get("drop_id", ""),
                    "track_id": drop.get("track_id", ""),
                    "alpha_m_s": fit.get("alpha_m_s"),
                    "gamma_m_s_V": fit.get("gamma_m_s_V"),
                    "sigma_alpha_random": fit.get("sigma_alpha_random"),
                    "sigma_gamma_random": fit.get("sigma_gamma_random"),
                    "fit_method": fit.get("fit_method"),
                    "velocity_uncertainty_source": fit.get("velocity_uncertainty_source"),
                    "radius_m": result.get("radius_m"),
                    "radius_um": result.get("radius_m") * 1e6 if result.get("radius_m") is not None else None,
                    "sigma_radius_random_m": result.get("sigma_radius_random_m"),
                    "radius_ci95_low_m": result.get("radius_ci95_low_m"),
                    "radius_ci95_high_m": result.get("radius_ci95_high_m"),
                    "charge_abs_C": result.get("charge_abs_C"),
                    "charge_1e_minus_19_C": result.get("charge_abs_C") / 1e-19 if result.get("charge_abs_C") is not None else None,
                    "sigma_charge_random_C": result.get("sigma_charge_random_C"),
                    "sigma_charge_total_C": result.get("sigma_charge_total_C", result.get("sigma_charge_C")),
                    "charge_ci95_low_C": result.get("charge_ci95_low_C"),
                    "charge_ci95_high_C": result.get("charge_ci95_high_C"),
                    "voltage_span_V": fit.get("voltage_span_V"),
                    "intercept_extrapolation_ratio": fit.get("intercept_extrapolation_ratio"),
                    "design_matrix_condition_number": fit.get("design_matrix_condition_number"),
                    "warnings": ";".join(str(flag) for flag in drop.get("flags", []) if str(flag)),
                }
            )
        else:
            failures.append(
                {
                    "drop_id": drop.get("drop_id", ""),
                    "track_id": drop.get("track_id", ""),
                    "stage": "single_drop_physics",
                    "errors": list(drop.get("flags", []) or []),
                    "diagnostics": {"fit": fit},
                }
            )
    charges = pd.DataFrame(rows)
    charge_failures = {"failures": failures}
    charges.to_csv(run_dir / "drop_charge_results.csv", index=False)
    _write_json(run_dir / "drop_charge_failures.json", charge_failures)
    return charges, charge_failures


def _normal_factor(rng: np.random.Generator, sigma_rel: float) -> float:
    if sigma_rel <= 0 or not math.isfinite(float(sigma_rel)):
        return 1.0
    return max(1e-12, float(rng.normal(1.0, sigma_rel)))


def _systematic_draw_config(config: dict[str, Any], rng: np.random.Generator) -> tuple[dict[str, Any], float, float]:
    physics = dict(config["physics"])
    viscosity = dict(config.get("viscosity", {}))
    systematic = physics.get("systematic_uncertainty", {}) or {}
    scale_factor = _normal_factor(rng, float(systematic.get("spatial_scale_rel", 0.0)))
    voltage_factor = _normal_factor(rng, float(systematic.get("voltage_scale_rel", 0.0)))
    physics["plate_distance_m"] = float(physics["plate_distance_m"]) * _normal_factor(rng, float(systematic.get("plate_distance_rel", 0.0)))
    physics["pressure_Pa"] = float(physics["pressure_Pa"]) * _normal_factor(rng, float(systematic.get("pressure_rel", 0.0)))
    physics["oil_density_kg_m3"] = float(physics["oil_density_kg_m3"]) * _normal_factor(rng, float(systematic.get("oil_density_rel", 0.0)))
    physics["cunningham_b_Pa_m"] = float(physics["cunningham_b_Pa_m"]) * _normal_factor(rng, float(systematic.get("cunningham_b_rel", 0.0)))
    if "temperature_C" in systematic and viscosity.get("source", "temperature") != "direct":
        viscosity["air_temperature_C"] = float(viscosity.get("air_temperature_C", 20.0)) + float(rng.normal(0.0, float(systematic["temperature_C"])))
    elif "viscosity_rel" in systematic:
        base_eta = resolve_air_viscosity({"physics": physics, "viscosity": viscosity})["air_viscosity_Pa_s"]
        viscosity["source"] = "direct"
        viscosity["direct_air_viscosity_Pa_s"] = base_eta * _normal_factor(rng, float(systematic.get("viscosity_rel", 0.0)))
    return {"physics": physics, "viscosity": viscosity}, scale_factor, voltage_factor


def _compute_q_from_fit(alpha: float, gamma: float, constants: dict[str, Any], viscosity: dict[str, Any]) -> tuple[float | None, float | None]:
    radius, flags = solve_radius_with_cunningham(alpha, constants)
    if flags or radius is None:
        return None, None
    eff = eta_eff(radius, float(viscosity["air_viscosity_Pa_s"]), float(constants["pressure_Pa"]), float(constants["cunningham_b_Pa_m"]))
    charge = 6 * math.pi * eff * radius * float(constants["plate_distance_m"]) * gamma
    if not math.isfinite(charge) or charge <= 0:
        return None, None
    return float(radius), float(charge)


def _build_uncertainty_details(drop_results: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    valid_drops = [drop for drop in drop_results if bool(drop.get("valid"))]
    samples = int(config.get("physics", {}).get("systematic_mc_samples", 0))
    if not valid_drops or samples <= 0:
        return {
            "status": "incomplete",
            "random_uncertainty": "per-drop random q uncertainty uses joint alpha-gamma Monte Carlo when covariance is available",
            "systematic_uncertainty": "shared systematic Monte Carlo not configured",
            "per_drop": [],
        }
    seed = int(config.get("elementary", {}).get("random_seed", 42)) + 65537
    rng = np.random.default_rng(seed)
    radius_samples: dict[str, list[float]] = {str(drop.get("drop_id", "")): [] for drop in valid_drops}
    charge_samples: dict[str, list[float]] = {str(drop.get("drop_id", "")): [] for drop in valid_drops}
    combined_samples: dict[str, list[float]] = {str(drop.get("drop_id", "")): [] for drop in valid_drops}
    for _sample in range(samples):
        draw_cfg, scale_factor, voltage_factor = _systematic_draw_config(config, rng)
        viscosity = resolve_air_viscosity(draw_cfg)
        constants = {**draw_cfg["physics"], **viscosity}
        for drop in valid_drops:
            drop_id = str(drop.get("drop_id", ""))
            fit = drop.get("fit", {}) or {}
            alpha = float(fit.get("alpha_m_s", fit.get("alpha", math.nan))) * scale_factor
            gamma = float(fit.get("gamma_m_s_V", fit.get("gamma", math.nan))) * scale_factor / voltage_factor
            if not (math.isfinite(alpha) and math.isfinite(gamma)) or alpha <= 0 or gamma <= 0:
                continue
            radius, charge = _compute_q_from_fit(alpha, gamma, constants, viscosity)
            if radius is None or charge is None:
                continue
            radius_samples[drop_id].append(radius)
            charge_samples[drop_id].append(charge)
            sigma_random = float((drop.get("result", {}) or {}).get("sigma_charge_random_C", 0.0) or 0.0)
            combined_samples[drop_id].append(max(1e-30, float(rng.normal(charge, sigma_random))) if sigma_random > 0 else charge)
    per_drop = []
    min_used = samples
    for drop in valid_drops:
        drop_id = str(drop.get("drop_id", ""))
        result = drop.get("result", {}) or {}
        q_nominal = float(result.get("charge_abs_C", math.nan))
        radius_nominal = float(result.get("radius_m", math.nan))
        q_sys = np.asarray(charge_samples[drop_id], dtype=float)
        r_sys = np.asarray(radius_samples[drop_id], dtype=float)
        q_combined = np.asarray(combined_samples[drop_id], dtype=float)
        min_used = min(min_used, len(q_sys))
        if len(q_sys) >= 2:
            per_drop.append(
                {
                    "drop_id": drop_id,
                    "track_id": drop.get("track_id", ""),
                    "radius_m": radius_nominal,
                    "charge_abs_C": q_nominal,
                    "sigma_radius_systematic_m": float(np.std(r_sys, ddof=1)),
                    "radius_systematic_ci95_low_m": float(np.percentile(r_sys, 2.5)),
                    "radius_systematic_ci95_high_m": float(np.percentile(r_sys, 97.5)),
                    "sigma_charge_systematic_C": float(np.std(q_sys, ddof=1)),
                    "charge_systematic_ci95_low_C": float(np.percentile(q_sys, 2.5)),
                    "charge_systematic_ci95_high_C": float(np.percentile(q_sys, 97.5)),
                    "combined_charge_ci95_low_C": float(np.percentile(q_combined, 2.5)),
                    "combined_charge_ci95_high_C": float(np.percentile(q_combined, 97.5)),
                }
            )
        else:
            per_drop.append(
                {
                    "drop_id": drop_id,
                    "track_id": drop.get("track_id", ""),
                    "radius_m": radius_nominal,
                    "charge_abs_C": q_nominal,
                    "sigma_radius_systematic_m": math.inf,
                    "radius_systematic_ci95_low_m": math.nan,
                    "radius_systematic_ci95_high_m": math.nan,
                    "sigma_charge_systematic_C": math.inf,
                    "charge_systematic_ci95_low_C": math.nan,
                    "charge_systematic_ci95_high_C": math.nan,
                    "combined_charge_ci95_low_C": math.nan,
                    "combined_charge_ci95_high_C": math.nan,
                }
            )
    return {
        "status": "complete" if min_used >= max(2, samples // 2) else "partial",
        "random_uncertainty": "per-drop random q uncertainty uses joint alpha-gamma Monte Carlo",
        "systematic_uncertainty": "shared systematic Monte Carlo uses common sampled physical parameters across all drops",
        "shared_systematic_mc": {
            "samples_requested": int(samples),
            "samples_used": int(min_used),
            "seed": int(seed),
            "inputs": config.get("physics", {}).get("systematic_uncertainty", {}),
        },
        "per_drop": per_drop,
    }


def _write_report(run_dir: Path, result: dict[str, Any]) -> None:
    charges = result["charge_results"]
    elementary = result["elementary"]
    comparison = result["model_comparison"]
    status = "success" if elementary.get("valid") else ("partial" if result["multi_drop_results"]["valid_drop_count"] else "failed")
    lines = [
        "# Downstream Millikan Report",
        "",
        "## Run Conclusion",
        "",
        f"- status: `{status}`",
        f"- valid q count: `{result['multi_drop_results']['valid_drop_count']}`",
        f"- failed q count: `{len(result['charge_failures']['failures'])}`",
        "",
        "## Per-Drop r and q",
        "",
    ]
    if charges.empty:
        lines.append("_No successful q results._")
    else:
        view = charges[["drop_id", "track_id", "radius_um", "charge_1e_minus_19_C", "sigma_charge_total_C", "warnings"]]
        lines.extend(_markdown_table(view))
    lines.extend(
        [
            "",
            "## Elementary-Charge Estimate",
            "",
            f"- valid: `{elementary.get('valid')}`",
            f"- used q count: `{elementary.get('num_used_drops', 0)}`",
            f"- e_hat (1e-19 C): `{_scale_e(elementary)}`",
            "",
            "## Quantized-vs-Continuous Comparison",
            "",
            f"- delta_elpd: `{comparison.get('delta_elpd')}`",
            f"- evidence_label: `{comparison.get('evidence_label', 'not_calibrated')}`",
            "",
            "## Uncertainty Contributors",
            "",
            f"- uncertainty status: `{result['uncertainty_details'].get('status')}`",
            "",
            "## Concise Warnings",
            "",
            f"- flags: `{', '.join(elementary.get('flags', []))}`",
            "",
            "## Machine-Output File List",
            "",
            "- `platform_velocity_results.csv`",
            "- `drop_charge_results.csv`",
            "- `drop_charge_failures.json`",
            "- `elementary_charge_result.json`",
            "- `model_comparison.json`",
            "- `uncertainty_details.json`",
            "- `plots_data.json`",
        ]
    )
    (run_dir / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _scale_e(elementary: dict[str, Any]) -> str:
    e_hat = elementary.get("elementary_charge", {}).get("e_hat_C")
    if e_hat is None or (isinstance(e_hat, float) and not math.isfinite(e_hat)):
        return ""
    return f"{float(e_hat) / 1e-19:.6g}"


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    headers = list(frame.columns)
    lines = ["|" + "|".join(headers) + "|", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in frame.to_dict("records"):
        values = []
        for header in headers:
            value = row.get(header, "")
            if isinstance(value, float):
                values.append(f"{value:.6g}" if math.isfinite(value) else "")
            else:
                values.append(str(value))
        lines.append("|" + "|".join(values) + "|")
    return lines


def run_downstream_analysis(
    *,
    trajectories: pd.DataFrame,
    platforms: pd.DataFrame,
    scale_y_m_per_px: float,
    config: dict[str, Any],
    run_dir: str | Path | None = None,
) -> dict[str, Any]:
    if trajectories.empty:
        raise ValueError("empty_trajectories")
    if platforms.empty:
        raise ValueError("empty_voltage_platforms")
    if scale_y_m_per_px <= 0 or not math.isfinite(float(scale_y_m_per_px)):
        raise ValueError("invalid_scale_y_m_per_px")
    target = Path(run_dir) if run_dir is not None else _default_run_dir(config)
    target.mkdir(parents=True, exist_ok=True)

    drop_segments = _fit_all_segments(trajectories, platforms, float(scale_y_m_per_px), config)
    drop_results, multi_drop_results = _compute_drop_results(drop_segments, config)
    elementary = estimate_elementary_charge(drop_results, config)
    model_comparison = elementary.get("model_comparison", {})
    uncertainty_details = _build_uncertainty_details(drop_results, config)
    plots_data = {
        "elementary_profile": {
            "candidate_modes": elementary.get("harmonic_analysis", {}).get("candidate_modes", []),
        },
        "leave_one_drop_out": elementary.get("stability", {}).get("leave_one_drop_out", []),
    }

    drop_segments.to_csv(target / "drop_track_segments.csv", index=False)
    velocity_results = _write_velocity_results(target, drop_segments, drop_results)
    charge_results, charge_failures = _write_charge_outputs(target, drop_results)
    _write_json(target / "multi_drop_results.json", multi_drop_results)
    _write_json(target / "elementary_charge_result.json", elementary)
    _write_json(target / "model_comparison.json", model_comparison)
    _write_json(target / "uncertainty_details.json", uncertainty_details)
    _write_json(target / "plots_data.json", plots_data)

    result = {
        "run_dir": target,
        "platform_velocity_results": velocity_results,
        "drop_segments": drop_segments,
        "drop_results": drop_results,
        "multi_drop_results": multi_drop_results,
        "charge_results": charge_results,
        "charge_failures": charge_failures,
        "elementary": elementary,
        "model_comparison": model_comparison,
        "uncertainty_details": uncertainty_details,
        "plots_data": plots_data,
    }
    _write_report(target, result)
    return result
