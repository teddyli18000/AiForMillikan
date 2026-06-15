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


def _estimator_config(config: dict, profile_points: int, null_samples: int) -> dict:
    cfg = json.loads(json.dumps(config))
    cfg["elementary"]["profile_grid_points"] = int(profile_points)
    cfg["elementary"]["comparison_profile_grid_points"] = max(40, min(80, int(profile_points)))
    cfg["elementary"]["tau_lambda_profile_optimize_points"] = 2
    cfg["elementary"]["tau_lambda_optimizer_maxiter"] = 12
    cfg["elementary"]["e_bootstrap_samples"] = 50
    cfg["elementary"]["measurement_mc_samples"] = 50
    cfg["elementary"]["null_simulation_samples"] = int(null_samples)
    return cfg


def _run_quantized_case(rng: np.random.Generator, cfg: dict, n: int, noise: float, e_true: float) -> dict[str, object]:
    integers = rng.integers(2, 10, size=n)
    sigmas = np.full(n, noise * e_true)
    charges = integers * e_true + rng.normal(0.0, sigmas)
    result = estimate_elementary_charge(_drop_results(charges, sigmas), cfg)
    e_hat = result.get("elementary_charge", {}).get("e_hat_C")
    ci = result.get("elementary_charge", {}).get("ci_95_C", [None, None])
    width = float(ci[1] - ci[0]) if ci[0] is not None and ci[1] is not None else None
    return {
        "valid": bool(result.get("valid")),
        "e_hat_C": e_hat,
        "bias_C": float(e_hat - e_true) if e_hat is not None else None,
        "relative_bias": float((e_hat - e_true) / e_true) if e_hat is not None else None,
        "covered": bool(ci[0] <= e_true <= ci[1]) if ci[0] is not None and ci[1] is not None else False,
        "interval_width_C": width,
        "harmonic_ambiguity": bool(result.get("harmonic_analysis", {}).get("harmonic_ambiguity", False)),
        "evidence_label": result.get("model_comparison", {}).get("evidence_label"),
        "delta_elpd": result.get("model_comparison", {}).get("delta_elpd"),
    }


def _run_continuous_case(rng: np.random.Generator, cfg: dict, n: int, noise: float, e_scale: float) -> dict[str, object]:
    sigmas = np.full(n, noise * e_scale)
    means = rng.choice([2.4, 5.2, 8.0], size=n, p=[0.45, 0.35, 0.20]) * e_scale
    charges = rng.normal(means, sigmas)
    result = estimate_elementary_charge(_drop_results(charges, sigmas), cfg)
    return {
        "valid": bool(result.get("valid")),
        "delta_elpd": result.get("model_comparison", {}).get("delta_elpd"),
        "evidence_label": result.get("model_comparison", {}).get("evidence_label"),
        "p_null": result.get("model_comparison", {}).get("null_simulation", {}).get("empirical_p_value"),
    }


def run_simulation(
    config_path: str | Path,
    replicates: int,
    seed: int,
    profile_points: int,
    null_samples: int,
    n_values: tuple[int, ...] = (10, 15, 20, 40),
    noise_values: tuple[float, ...] = (0.02, 0.06, 0.12),
) -> dict[str, object]:
    started = time.perf_counter()
    config = _estimator_config(load_config(config_path), profile_points, null_samples)
    rng = np.random.default_rng(seed)
    e_true = 1.6e-19
    quantized = []
    continuous = []
    for n in n_values:
        for noise in noise_values:
            for _ in range(replicates):
                quantized.append({"n": n, "noise": noise, **_run_quantized_case(rng, config, n, noise, e_true)})
                continuous.append({"n": n, "noise": noise, **_run_continuous_case(rng, config, n, noise, e_true)})
    valid_quantized = [row for row in quantized if row["valid"] and row["bias_C"] is not None]
    false_strong = [row for row in continuous if row["evidence_label"] == "strong"]
    false_moderate_or_strong = [row for row in continuous if row["evidence_label"] in {"moderate", "strong"}]
    biases = np.asarray([row["bias_C"] for row in valid_quantized], dtype=float)
    widths = np.asarray([row["interval_width_C"] for row in valid_quantized if row["interval_width_C"] is not None], dtype=float)
    continuous_delta = np.asarray([row["delta_elpd"] for row in continuous if row["delta_elpd"] is not None], dtype=float)
    return {
        "config": {
            "replicates": replicates,
            "seed": seed,
            "profile_points": profile_points,
            "null_simulation_samples": null_samples,
            "n_values": list(n_values),
            "noise_values": list(noise_values),
        },
        "summary": {
            "quantized_valid_count": len(valid_quantized),
            "mean_bias_C": float(np.mean(biases)) if len(biases) else None,
            "mean_relative_bias": float(np.mean(biases / e_true)) if len(biases) else None,
            "rmse_C": float(np.sqrt(np.mean(np.square(biases)))) if len(biases) else None,
            "coverage_rate": float(np.mean([row["covered"] for row in valid_quantized])) if valid_quantized else None,
            "median_interval_width_C": float(np.median(widths)) if len(widths) else None,
            "harmonic_ambiguity_rate": float(np.mean([row["harmonic_ambiguity"] for row in valid_quantized])) if valid_quantized else None,
            "continuous_false_strong_rate": len(false_strong) / len(continuous) if continuous else None,
            "continuous_false_moderate_or_strong_rate": len(false_moderate_or_strong) / len(continuous) if continuous else None,
            "continuous_delta_elpd_mean": float(np.mean(continuous_delta)) if len(continuous_delta) else None,
            "continuous_delta_elpd_median": float(np.median(continuous_delta)) if len(continuous_delta) else None,
            "runtime_s": float(time.perf_counter() - started),
        },
        "quantized": quantized,
        "continuous": continuous,
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
        "",
        "## Summary",
        "",
        f"- quantized_valid_count: `{summary['quantized_valid_count']}`",
        f"- mean_bias_C: `{summary['mean_bias_C']}`",
        f"- mean_relative_bias: `{summary['mean_relative_bias']}`",
        f"- rmse_C: `{summary['rmse_C']}`",
        f"- coverage_rate: `{summary['coverage_rate']}`",
        f"- median_interval_width_C: `{summary['median_interval_width_C']}`",
        f"- harmonic_ambiguity_rate: `{summary['harmonic_ambiguity_rate']}`",
        f"- continuous_false_strong_rate: `{summary['continuous_false_strong_rate']}`",
        f"- continuous_false_moderate_or_strong_rate: `{summary['continuous_false_moderate_or_strong_rate']}`",
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
