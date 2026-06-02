from __future__ import annotations

import random

import numpy as np


def estimate_elementary_charge(drop_results: list[dict], config: dict) -> dict[str, object]:
    cfg = config["elementary"]
    valid = [
        drop
        for drop in drop_results
        if drop.get("valid") and drop.get("result", {}).get("charge_abs_C") and drop.get("result", {}).get("sigma_charge_C")
    ]
    if len(valid) < int(cfg["min_drops"]):
        return {
            "valid": False,
            "flags": ["insufficient_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": len(valid),
        }
    charges = np.array([float(drop["result"]["charge_abs_C"]) for drop in valid])
    sigmas = np.array([float(drop["result"]["sigma_charge_C"]) for drop in valid])
    weights = 1.0 / np.maximum(sigmas, 1e-30) ** 2
    grid = np.linspace(float(cfg["e_min_C"]), float(cfg["e_max_C"]), int(cfg["grid_points"]))
    objective = []
    for e in grid:
        n = np.maximum(1, np.rint(charges / e))
        residuals = charges - n * e
        objective.append(float(np.sum(weights * residuals**2) / np.sum(weights)))
    min_objective = min(objective)
    sigma_scale = float(np.median(sigmas) ** 2)
    tolerance = max(min_objective * 1.05, sigma_scale * 0.10)
    candidate_indices = [idx for idx, value in enumerate(objective) if value <= min_objective + tolerance]
    e_hat = float(grid[max(candidate_indices)])
    n_hat = np.maximum(1, np.rint(charges / e_hat)).astype(int)
    residuals = charges - n_hat * e_hat
    rng = random.Random(int(cfg.get("random_seed", 42)))
    boot = []
    for _ in range(int(cfg.get("bootstrap_samples", 50))):
        sample = [rng.randrange(len(charges)) for _ in range(len(charges))]
        sample_charges = charges[sample]
        sample_weights = weights[sample]
        scores = []
        for e in grid:
            n = np.maximum(1, np.rint(sample_charges / e))
            scores.append(float(np.sum(sample_weights * (sample_charges - n * e) ** 2) / np.sum(sample_weights)))
        boot.append(float(grid[int(np.argmin(scores))]))
    return {
        "valid": True,
        "num_total_drops": len(drop_results),
        "num_used_drops": len(valid),
        "elementary_charge": {
            "e_hat_C": e_hat,
            "e_hat_1e_minus_19_C": e_hat / 1e-19,
            "sigma_e_C": float(np.std(boot)) if boot else 0.0,
            "ci_95_C": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))] if boot else [e_hat, e_hat],
            "blind_estimation": True,
        },
        "drops": [
            {
                "drop_id": valid[i].get("drop_id", f"drop_{i+1:03d}"),
                "charge_C": float(charges[i]),
                "sigma_charge_C": float(sigmas[i]),
                "n_hat": int(n_hat[i]),
                "nearest_quantized_charge_C": float(n_hat[i] * e_hat),
                "residual_C": float(residuals[i]),
                "normalized_residual": float(residuals[i] / max(sigmas[i], 1e-30)),
            }
            for i in range(len(valid))
        ],
        "model_comparison": {
            "weighted_residual_rms_C": float(np.sqrt(min(objective))),
            "method": "weighted_grid_search_integer_assignment",
        },
        "flags": [],
    }
