from __future__ import annotations

import argparse
import json
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
    return {
        "valid": bool(result.get("valid")),
        "e_hat_C": e_hat,
        "bias_C": float(e_hat - e_true) if e_hat is not None else None,
        "covered": bool(ci[0] <= e_true <= ci[1]) if ci[0] is not None and ci[1] is not None else False,
        "harmonic_ambiguity": bool(result.get("harmonic_analysis", {}).get("harmonic_ambiguity", False)),
        "evidence_label": result.get("model_comparison", {}).get("evidence_label"),
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
    return {
        "config": {
            "replicates": replicates,
            "seed": seed,
            "profile_points": profile_points,
            "null_simulation_samples": null_samples,
        },
        "summary": {
            "quantized_valid_count": len(valid_quantized),
            "mean_bias_C": float(np.mean([row["bias_C"] for row in valid_quantized])) if valid_quantized else None,
            "coverage_rate": float(np.mean([row["covered"] for row in valid_quantized])) if valid_quantized else None,
            "harmonic_ambiguity_rate": float(np.mean([row["harmonic_ambiguity"] for row in valid_quantized])) if valid_quantized else None,
            "continuous_false_strong_rate": len(false_strong) / len(continuous) if continuous else None,
        },
        "quantized": quantized,
        "continuous": continuous,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Slow synthetic validation for the downstream elementary-charge estimator.")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profile-points", type=int, default=80)
    parser.add_argument("--null-samples", type=int, default=20)
    parser.add_argument("--output", default="runs/estimator_simulation_validation.json")
    args = parser.parse_args()

    result = run_simulation(args.config, args.replicates, args.seed, args.profile_points, args.null_samples)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
