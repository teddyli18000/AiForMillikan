from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from millikan_ai.config import load_config
from millikan_ai.elementary.estimate import estimate_elementary_charge


def _drop_results(charges: np.ndarray, sigmas: np.ndarray) -> list[dict[str, object]]:
    return [
        {
            "drop_id": f"sim_{index:03d}",
            "track_id": f"sim_{index:03d}",
            "valid": True,
            "result": {"charge_abs_C": float(charge), "sigma_charge_C": float(sigma)},
        }
        for index, (charge, sigma) in enumerate(zip(charges, sigmas), start=1)
    ]


def _estimator_config(config: dict, profile_points: int, null_samples: int, bootstrap_samples: int, measurement_mc_samples: int) -> dict:
    cfg = json.loads(json.dumps(config))
    cfg["elementary"]["profile_grid_points"] = int(profile_points)
    cfg["elementary"]["comparison_profile_grid_points"] = max(40, min(80, int(profile_points)))
    cfg["elementary"]["tau_lambda_profile_optimize_points"] = 2
    cfg["elementary"]["tau_lambda_optimizer_maxiter"] = 12
    cfg["elementary"]["e_bootstrap_samples"] = int(bootstrap_samples)
    cfg["elementary"]["measurement_mc_samples"] = int(measurement_mc_samples)
    cfg["elementary"]["null_simulation_samples"] = int(null_samples)
    return cfg


def _run_quantized_case(rng: np.random.Generator, cfg: dict, n: int, noise: float, e_true: float) -> dict[str, object]:
    base = np.array([1, 1, 2, 2, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], dtype=int)
    integers = rng.choice(base, size=n, replace=True)
    sigmas = np.full(n, noise * e_true)
    charges = integers * e_true + rng.normal(0.0, sigmas)
    return _summarize_estimator_result(estimate_elementary_charge(_drop_results(charges, sigmas), cfg), e_true=e_true, case_kind="quantized")


def _summarize_estimator_result(result: dict[str, object], *, e_true: float | None, case_kind: str) -> dict[str, object]:
    elementary = result.get("elementary_charge", {}) or {}
    e_hat = elementary.get("e_hat_C")
    ci = elementary.get("ci_95_C", [None, None])
    width = float(ci[1] - ci[0]) if ci[0] is not None and ci[1] is not None else None
    mode_stability = result.get("mode_stability", {}) or {}
    bootstrap_mode = mode_stability.get("bootstrap", {}) or {}
    measurement_mode = mode_stability.get("measurement_mc", {}) or {}
    comparison = result.get("model_comparison", {}) or {}
    boundary = result.get("boundary_guard", {}) or {}
    optimizer = result.get("optimizer", {}) or {}
    primitive = result.get("primitive_assignment", {}) or {}
    relative_bias = float((e_hat - e_true) / e_true) if e_true is not None and e_hat is not None else None
    return {
        "case_kind": case_kind,
        "valid": bool(result.get("valid")),
        "fit_valid": bool(result.get("fit_valid")),
        "bounded_estimate_available": bool(result.get("bounded_estimate_available")),
        "quantization_favored": result.get("quantization_favored"),
        "quantization_supported": result.get("quantization_supported"),
        "primitive_assignment_supported": result.get("primitive_assignment_supported"),
        "fundamental_spacing_identified": bool(result.get("fundamental_spacing_identified")),
        "status": result.get("status"),
        "e_hat_C": e_hat,
        "bias_C": float(e_hat - e_true) if e_true is not None and e_hat is not None else None,
        "relative_bias": relative_bias,
        "covered": bool(ci[0] <= e_true <= ci[1]) if e_true is not None and ci[0] is not None and ci[1] is not None else False,
        "interval_width_C": width,
        "harmonic_ambiguity": bool(result.get("harmonic_analysis", {}).get("harmonic_ambiguity", False)),
        "search_boundary_hit": bool(boundary.get("search_boundary_hit", False)),
        "profile_optimization_incomplete": bool(optimizer.get("profile_optimization_incomplete", False)),
        "failed_optimizations": int(optimizer.get("failed_optimizations", 0) or 0),
        "local_modes_omitted": int(optimizer.get("local_modes_omitted", 0) or 0),
        "important_local_modes_omitted": int(optimizer.get("important_local_modes_omitted", 0) or 0),
        "primitive_assignment_failure": not bool(primitive.get("primitive_assignment_supported", False)),
        "bootstrap_mode_instability": bool(bootstrap_mode.get("samples", 0) and bootstrap_mode.get("main_mode_fraction", 1.0) < mode_stability.get("main_mode_min_fraction_required", 0.80)),
        "measurement_mc_mode_instability": bool(measurement_mode.get("samples", 0) and measurement_mode.get("main_mode_fraction", 1.0) < mode_stability.get("main_mode_min_fraction_required", 0.80)),
        "catastrophic_error": bool(relative_bias is not None and abs(relative_bias) > 0.25),
        "evidence_label": comparison.get("evidence_label"),
        "delta_elpd": comparison.get("delta_elpd"),
        "p_null": comparison.get("null_simulation", {}).get("empirical_p_value"),
    }


def _run_continuous_case(rng: np.random.Generator, cfg: dict, n: int, noise: float, e_scale: float) -> dict[str, object]:
    case_cfg = json.loads(json.dumps(cfg))
    case_cfg["elementary"]["e_bootstrap_samples"] = 0
    case_cfg["elementary"]["measurement_mc_samples"] = 0
    sigmas = np.full(n, noise * e_scale)
    means = rng.choice([2.4, 5.2, 8.0], size=n, p=[0.45, 0.35, 0.20]) * e_scale
    charges = rng.normal(means, sigmas)
    return _summarize_estimator_result(estimate_elementary_charge(_drop_results(charges, sigmas), case_cfg), e_true=None, case_kind="continuous")


def _difficult_charge_case(rng: np.random.Generator, case_name: str, n: int, noise: float, e_true: float) -> tuple[np.ndarray, np.ndarray]:
    n = max(3, int(n))
    if case_name == "even_multiples":
        integers = 2 * (1 + np.arange(n) % 8)
        scale = 1.0
        sigmas = np.full(n, noise * e_true)
    elif case_name == "multiples_of_3":
        integers = 3 * (1 + np.arange(n) % 6)
        scale = 1.0
        sigmas = np.full(n, noise * e_true)
    elif case_name == "missing_n1":
        integers = 2 + np.arange(n) % 10
        scale = 1.0
        sigmas = np.full(n, noise * e_true)
    elif case_name == "sparse_multiples":
        integers = np.resize(np.array([1, 4, 8, 13, 19, 25], dtype=int), n)
        scale = 1.0
        sigmas = np.full(n, noise * e_true)
    elif case_name == "adjacent_insufficient":
        integers = np.resize(np.array([5, 6, 7, 18, 19, 20], dtype=int), n)
        scale = 1.0
        sigmas = np.full(n, noise * e_true)
    elif case_name == "heteroscedastic":
        integers = np.resize(np.array([1, 2, 3, 4, 5, 7, 9, 11], dtype=int), n)
        scale = 1.0
        sigmas = np.linspace(0.012, 0.03, n) * e_true
    elif case_name == "outliers":
        integers = np.resize(np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=int), n)
        scale = 1.0
        sigmas = np.full(n, noise * e_true)
    elif case_name == "near_lower_boundary":
        integers = np.resize(np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=int), n)
        scale = 0.845
        sigmas = np.full(n, noise * e_true)
    elif case_name == "near_upper_boundary":
        integers = np.resize(np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=int), n)
        scale = 1.185
        sigmas = np.full(n, noise * e_true)
    elif case_name == "override_config_attempt":
        integers = np.resize(np.array([1, 2, 3, 4, 5, 6], dtype=int), n)
        scale = 1.0
        sigmas = np.full(n, noise * e_true)
    else:
        raise ValueError(f"unknown difficult case: {case_name}")
    charges = integers.astype(float) * e_true * scale + rng.normal(0.0, sigmas)
    if case_name == "outliers" and n >= 5:
        charges[-1] *= 1.37
    return charges, sigmas


def _run_difficult_case(rng: np.random.Generator, cfg: dict, case_name: str, n: int, noise: float, e_true: float) -> dict[str, object]:
    case_cfg = json.loads(json.dumps(cfg))
    case_cfg["elementary"]["e_bootstrap_samples"] = 0
    case_cfg["elementary"]["measurement_mc_samples"] = 0
    case_cfg["elementary"]["null_simulation_samples"] = 0
    if case_name == "override_config_attempt":
        case_cfg["elementary"]["e_search_min_C"] = 0.5e-19
        case_cfg["elementary"]["e_search_max_C"] = 2.5e-19
    charges, sigmas = _difficult_charge_case(rng, case_name, n, noise, e_true)
    result = estimate_elementary_charge(_drop_results(charges, sigmas), case_cfg)
    summary = _summarize_estimator_result(result, e_true=e_true, case_kind="difficult")
    summary["case"] = case_name
    summary["search_interval_C"] = result.get("elementary_charge", {}).get("search_interval_C")
    summary["search_interval_override_ignored"] = result.get("elementary_charge", {}).get("prior", {}).get("search_interval_override_ignored")
    return summary


def run_simulation(
    config_path: str | Path,
    replicates: int,
    seed: int,
    profile_points: int,
    null_samples: int,
    n_values: tuple[int, ...] = (10, 15, 20, 40),
    noise_values: tuple[float, ...] = (0.02, 0.06, 0.12),
    bootstrap_samples: int = 10,
    measurement_mc_samples: int = 10,
    difficult_replicates: int = 1,
) -> dict[str, object]:
    started = time.perf_counter()
    config = _estimator_config(load_config(config_path), profile_points, null_samples, bootstrap_samples, measurement_mc_samples)
    rng = np.random.default_rng(seed)
    e_true = 1.6e-19
    quantized = []
    continuous = []
    difficult = []
    difficult_cases = [
        "even_multiples",
        "multiples_of_3",
        "missing_n1",
        "sparse_multiples",
        "adjacent_insufficient",
        "heteroscedastic",
        "outliers",
        "near_lower_boundary",
        "near_upper_boundary",
        "override_config_attempt",
    ]
    for n in n_values:
        for noise in noise_values:
            for _ in range(replicates):
                quantized.append({"n": n, "noise": noise, **_run_quantized_case(rng, config, n, noise, e_true)})
                continuous.append({"n": n, "noise": noise, **_run_continuous_case(rng, config, n, noise, e_true)})
            for _ in range(max(0, int(difficult_replicates))):
                for case_name in difficult_cases:
                    difficult.append({"n": n, "noise": noise, **_run_difficult_case(rng, config, case_name, n, noise, e_true)})
    valid_quantized = [row for row in quantized if row["valid"] and row["bias_C"] is not None]
    fit_valid_quantized = [row for row in quantized if row["fit_valid"] and row["bias_C"] is not None]
    biases = np.asarray([row["bias_C"] for row in valid_quantized], dtype=float)
    fit_biases = np.asarray([row["bias_C"] for row in fit_valid_quantized], dtype=float)
    widths = np.asarray([row["interval_width_C"] for row in valid_quantized if row["interval_width_C"] is not None], dtype=float)
    continuous_delta = np.asarray([row["delta_elpd"] for row in continuous if row["delta_elpd"] is not None], dtype=float)
    continuous_p = np.asarray([row["p_null"] for row in continuous if row["p_null"] is not None], dtype=float)
    def rate(rows: list[dict[str, object]], key: str) -> float | None:
        return float(np.mean([bool(row.get(key)) for row in rows])) if rows else None

    return {
        "config": {
            "replicates": replicates,
            "seed": seed,
            "profile_points": profile_points,
            "null_simulation_samples": null_samples,
            "n_values": list(n_values),
            "noise_values": list(noise_values),
            "bootstrap_samples": int(bootstrap_samples),
            "measurement_mc_samples": int(measurement_mc_samples),
            "difficult_replicates": int(difficult_replicates),
        },
        "summary": {
            "quantized_valid_count": len(valid_quantized),
            "fit_valid_rate": rate(quantized, "fit_valid"),
            "bounded_estimate_available_rate": rate(quantized, "bounded_estimate_available"),
            "fundamental_spacing_identified_rate": rate(quantized, "fundamental_spacing_identified"),
            "mean_bias_C": float(np.mean(biases)) if len(biases) else None,
            "mean_relative_bias": float(np.mean(biases / e_true)) if len(biases) else None,
            "rmse_C": float(np.sqrt(np.mean(np.square(biases)))) if len(biases) else None,
            "fit_valid_mean_relative_bias": float(np.mean(fit_biases / e_true)) if len(fit_biases) else None,
            "fit_valid_rmse_C": float(np.sqrt(np.mean(np.square(fit_biases)))) if len(fit_biases) else None,
            "coverage_rate": float(np.mean([row["covered"] for row in valid_quantized])) if valid_quantized else None,
            "median_interval_width_C": float(np.median(widths)) if len(widths) else None,
            "harmonic_ambiguity_rate": float(np.mean([row["harmonic_ambiguity"] for row in valid_quantized])) if valid_quantized else None,
            "search_boundary_hit_rate": rate(quantized, "search_boundary_hit"),
            "profile_optimization_incomplete_rate": rate(quantized, "profile_optimization_incomplete"),
            "primitive_assignment_failure_rate": rate(quantized, "primitive_assignment_failure"),
            "bootstrap_mode_instability_rate": rate(quantized, "bootstrap_mode_instability"),
            "measurement_mc_mode_instability_rate": rate(quantized, "measurement_mc_mode_instability"),
            "catastrophic_error_rate": rate(quantized, "catastrophic_error"),
            "continuous_bounded_estimate_available_rate": rate(continuous, "bounded_estimate_available"),
            "continuous_quantization_favored_rate": rate(continuous, "quantization_favored"),
            "continuous_quantization_supported_rate": rate(continuous, "quantization_supported"),
            "continuous_false_fundamental_identification_rate": rate(continuous, "fundamental_spacing_identified"),
            "continuous_delta_elpd_mean": float(np.mean(continuous_delta)) if len(continuous_delta) else None,
            "continuous_delta_elpd_median": float(np.median(continuous_delta)) if len(continuous_delta) else None,
            "continuous_delta_elpd_distribution": continuous_delta.tolist(),
            "continuous_null_p_value_distribution": continuous_p.tolist(),
            "difficult_case_count": len(difficult),
            "difficult_catastrophic_error_rate": rate(difficult, "catastrophic_error"),
            "difficult_false_fundamental_identification_rate": rate(difficult, "fundamental_spacing_identified"),
            "runtime_s": float(time.perf_counter() - started),
        },
        "quantized": quantized,
        "continuous": continuous,
        "difficult_cases": difficult,
    }


def _write_markdown(path: Path, result: dict[str, object]) -> None:
    summary = result["summary"]
    config = result["config"]
    lines = [
        "# Estimator Simulation Validation",
        "",
        "## Configuration",
        "",
        f"- replicates: `{config['replicates']}`",
        f"- n_values: `{config['n_values']}`",
        f"- noise_values: `{config['noise_values']}`",
        f"- profile_points: `{config['profile_points']}`",
        f"- null_simulation_samples: `{config['null_simulation_samples']}`",
        f"- bootstrap_samples: `{config['bootstrap_samples']}`",
        f"- measurement_mc_samples: `{config['measurement_mc_samples']}`",
        f"- difficult_replicates: `{config['difficult_replicates']}`",
        "",
        "## Summary",
        "",
        f"- quantized_valid_count: `{summary['quantized_valid_count']}`",
        f"- fit_valid_rate: `{summary['fit_valid_rate']}`",
        f"- bounded_estimate_available_rate: `{summary['bounded_estimate_available_rate']}`",
        f"- fundamental_spacing_identified_rate: `{summary['fundamental_spacing_identified_rate']}`",
        f"- mean_bias_C: `{summary['mean_bias_C']}`",
        f"- mean_relative_bias: `{summary['mean_relative_bias']}`",
        f"- rmse_C: `{summary['rmse_C']}`",
        f"- coverage_rate: `{summary['coverage_rate']}`",
        f"- median_interval_width_C: `{summary['median_interval_width_C']}`",
        f"- harmonic_ambiguity_rate: `{summary['harmonic_ambiguity_rate']}`",
        f"- search_boundary_hit_rate: `{summary['search_boundary_hit_rate']}`",
        f"- profile_optimization_incomplete_rate: `{summary['profile_optimization_incomplete_rate']}`",
        f"- primitive_assignment_failure_rate: `{summary['primitive_assignment_failure_rate']}`",
        f"- catastrophic_error_rate: `{summary['catastrophic_error_rate']}`",
        f"- continuous_quantization_favored_rate: `{summary['continuous_quantization_favored_rate']}`",
        f"- continuous_quantization_supported_rate: `{summary['continuous_quantization_supported_rate']}`",
        f"- continuous_false_fundamental_identification_rate: `{summary['continuous_false_fundamental_identification_rate']}`",
        f"- difficult_catastrophic_error_rate: `{summary['difficult_catastrophic_error_rate']}`",
        f"- runtime_s: `{summary['runtime_s']}`",
        "",
        "## Interpretation",
        "",
        "This validation uses synthetic accepted q values with known truth. It is not based on raw video smoke runs.",
        "Evidence labels remain `not_calibrated` unless calibrated thresholds are explicitly enabled in config.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Slow synthetic validation for the downstream elementary-charge estimator.")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--preset", choices=["smoke", "quick_validation", "full_validation"], default="smoke")
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profile-points", type=int, default=80)
    parser.add_argument("--null-samples", type=int, default=20)
    parser.add_argument("--bootstrap-samples", type=int, default=10)
    parser.add_argument("--measurement-mc-samples", type=int, default=10)
    parser.add_argument("--difficult-replicates", type=int, default=1)
    parser.add_argument("--n-values", default=None, help="Comma-separated N values; preset defaults are used when omitted.")
    parser.add_argument("--noise-values", default=None, help="Comma-separated sigma/e noise values; preset defaults are used when omitted.")
    parser.add_argument("--output", default="runs/estimator_simulation_validation.json")
    parser.add_argument("--markdown-output", default=None)
    args = parser.parse_args()

    if args.n_values:
        n_values = tuple(int(item.strip()) for item in args.n_values.split(",") if item.strip())
    elif args.preset == "smoke":
        n_values = (10,)
    else:
        n_values = (10, 15, 20, 40)
    if args.noise_values:
        noise_values = tuple(float(item.strip()) for item in args.noise_values.split(",") if item.strip())
    elif args.preset == "smoke":
        noise_values = (0.06,)
    else:
        noise_values = (0.02, 0.06, 0.12)

    if args.preset == "quick_validation":
        args.replicates = max(args.replicates, 50)
    elif args.preset == "full_validation":
        args.replicates = max(args.replicates, 200)

    result = run_simulation(
        args.config,
        args.replicates,
        args.seed,
        args.profile_points,
        args.null_samples,
        n_values=n_values,
        noise_values=noise_values,
        bootstrap_samples=args.bootstrap_samples,
        measurement_mc_samples=args.measurement_mc_samples,
        difficult_replicates=args.difficult_replicates,
    )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_target = Path(args.markdown_output) if args.markdown_output else target.with_suffix(".md")
    _write_markdown(markdown_target, result)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print(f"wrote {target}")
    print(f"wrote {markdown_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
