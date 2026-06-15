from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import reduce
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


@dataclass(frozen=True)
class QuantizedFit:
    e_C: float
    tau_C: float
    lambda_decay: float
    log_likelihood: float
    profile_e_C: np.ndarray
    profile_log_likelihood: np.ndarray
    optimizer: dict[str, Any]


def _cfg_value(cfg: dict[str, Any], new_key: str, old_key: str | None, default: Any) -> Any:
    if new_key in cfg:
        return cfg[new_key]
    if old_key and old_key in cfg:
        return cfg[old_key]
    return default


def _usable_drops(drop_results: list[dict]) -> list[dict]:
    return [
        drop
        for drop in drop_results
        if drop.get("valid")
        and drop.get("result", {}).get("charge_abs_C") is not None
        and drop.get("result", {}).get("sigma_charge_C") is not None
    ]


def _normal_logpdf(x: np.ndarray, mean: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    return -0.5 * (np.log(2 * math.pi * sigma**2) + ((x - mean) / sigma) ** 2)


def _quantized_log_likelihood(
    charges: np.ndarray,
    sigmas: np.ndarray,
    e_C: float,
    tau_C: float,
    lambda_decay: float,
    nmax: int,
) -> float:
    n_values = np.arange(1, nmax + 1, dtype=float)
    log_prior = -float(lambda_decay) * (n_values - 1.0)
    log_prior = log_prior - logsumexp(log_prior)
    sigma_total = np.sqrt(np.square(sigmas[:, None]) + float(tau_C) ** 2)
    log_components = log_prior[None, :] + _normal_logpdf(charges[:, None], n_values[None, :] * float(e_C), sigma_total)
    return float(np.sum(logsumexp(log_components, axis=1)))


def _fit_quantized_profile(charges: np.ndarray, sigmas: np.ndarray, cfg: dict[str, Any]) -> QuantizedFit:
    e_min = float(_cfg_value(cfg, "e_search_min_C", "e_min_C", 0.5e-19))
    e_max = float(_cfg_value(cfg, "e_search_max_C", "e_max_C", 2.5e-19))
    grid_points = int(_cfg_value(cfg, "profile_grid_points", "grid_points", 800))
    if not (0 < e_min < e_max) or grid_points < 10:
        raise ValueError("invalid_elementary_search_config")
    e_grid = np.linspace(e_min, e_max, grid_points)
    nmax = max(1, int(math.ceil(float(np.max(charges)) / e_min)) + 1)
    median_sigma = float(np.median(sigmas))
    tau_grid = np.array([0.0, 1.0, 4.0], dtype=float) * max(median_sigma, 1e-30)
    lambda_grid = np.array([0.0, 0.75, 3.0], dtype=float)
    best: tuple[float, float, float, float] | None = None
    profile = []
    coarse_best_by_e: list[tuple[float, float, float]] = []
    for e_C in e_grid:
        best_for_e: tuple[float, float, float] | None = None
        for tau_C in tau_grid:
            for lambda_decay in lambda_grid:
                ll = _quantized_log_likelihood(charges, sigmas, float(e_C), float(tau_C), float(lambda_decay), nmax)
                if best_for_e is None or ll > best_for_e[0]:
                    best_for_e = (ll, float(tau_C), float(lambda_decay))
        assert best_for_e is not None
        profile.append(best_for_e[0])
        coarse_best_by_e.append(best_for_e)
        if best is None or best_for_e[0] > best[0]:
            best = (best_for_e[0], float(e_C), best_for_e[1], best_for_e[2])
    assert best is not None
    profile_arr = np.asarray(profile, dtype=float)
    n_eval = 0
    failed_optimizations = 0
    optimize_count = min(len(e_grid), int(cfg.get("tau_lambda_profile_optimize_points", 16)))
    candidate_indices = set(np.argsort(profile_arr)[-optimize_count:].tolist())
    for idx in list(candidate_indices):
        if idx > 0:
            candidate_indices.add(idx - 1)
        if idx < len(e_grid) - 1:
            candidate_indices.add(idx + 1)
    tau_scale = max(median_sigma, 1e-30)

    def optimize_at_index(idx: int) -> tuple[float, float, float, bool, int]:
        e_C = float(e_grid[idx])
        _ll0, tau0, lambda0 = coarse_best_by_e[idx]

        def objective(params: np.ndarray) -> float:
            tau_factor = float(params[0])
            lambda_decay = float(params[1])
            tau_C = tau_factor * tau_scale
            return -_quantized_log_likelihood(charges, sigmas, e_C, tau_C, lambda_decay, nmax)

        result = minimize(
            objective,
            np.array([max(0.0, tau0 / tau_scale), max(0.0, lambda0)], dtype=float),
            method="L-BFGS-B",
            bounds=[(0.0, 20.0), (0.0, 12.0)],
            options={"maxiter": int(cfg.get("tau_lambda_optimizer_maxiter", 80))},
        )
        if not result.success:
            return float(_ll0), float(tau0), float(lambda0), False, int(getattr(result, "nfev", 0) or 0)
        return -float(result.fun), float(result.x[0]) * tau_scale, float(result.x[1]), True, int(getattr(result, "nfev", 0) or 0)

    for idx in sorted(candidate_indices):
        ll, tau_C, lambda_decay, success, eval_count = optimize_at_index(idx)
        n_eval += eval_count
        if not success:
            failed_optimizations += 1
        profile_arr[idx] = ll
        if ll > best[0]:
            best = (ll, float(e_grid[idx]), tau_C, lambda_decay)
    selected_by = "maximum_profile_likelihood"
    n_hat = np.maximum(1, np.rint(charges / best[1]).astype(int))
    common_divisor = int(reduce(math.gcd, n_hat.tolist())) if len(n_hat) else 1
    if common_divisor > 1:
        target_e = best[1] * common_divisor
        e_max = float(_cfg_value(cfg, "e_search_max_C", "e_max_C", 2.5e-19))
        if target_e <= e_max:
            target_idx = int(np.argmin(np.abs(e_grid - target_e)))
            ll, tau_C, lambda_decay, success, eval_count = optimize_at_index(target_idx)
            n_eval += eval_count
            if success:
                profile_arr[target_idx] = ll
                relative = math.exp(min(0.0, ll - best[0]))
                if relative >= float(cfg.get("harmonic_resolution_min_relative", 0.05)):
                    best = (ll, float(e_grid[target_idx]), tau_C, lambda_decay)
                    selected_by = "common_divisor_harmonic_resolution"
    return QuantizedFit(
        e_C=best[1],
        tau_C=best[2],
        lambda_decay=best[3],
        log_likelihood=best[0],
        profile_e_C=e_grid,
        profile_log_likelihood=profile_arr,
        optimizer={
            "tau_lambda_optimizer": "scipy_minimize",
            "converged": bool(n_eval > 0 and failed_optimizations < max(1, len(candidate_indices))),
            "n_eval": int(n_eval),
            "bounds": {"tau_factor": [0.0, 20.0], "lambda_decay": [0.0, 12.0]},
            "optimized_profile_points": int(len(candidate_indices)),
            "failed_optimizations": int(failed_optimizations),
            "selected_by": selected_by,
        },
    )


def _assignment_rows(charges: np.ndarray, sigmas: np.ndarray, fit: QuantizedFit, drops: list[dict]) -> list[dict[str, object]]:
    nmax = max(1, int(math.ceil(float(np.max(charges)) / fit.e_C)) + 2)
    n_values = np.arange(1, nmax + 1, dtype=float)
    log_prior = -fit.lambda_decay * (n_values - 1.0)
    log_prior = log_prior - logsumexp(log_prior)
    sigma_total = np.sqrt(np.square(sigmas[:, None]) + fit.tau_C**2)
    log_post = log_prior[None, :] + _normal_logpdf(charges[:, None], n_values[None, :] * fit.e_C, sigma_total)
    log_post = log_post - logsumexp(log_post, axis=1)[:, None]
    probabilities = np.exp(log_post)
    n_hat = np.argmax(probabilities, axis=1) + 1
    rows = []
    for i, n_i in enumerate(n_hat):
        nearest = float(n_i * fit.e_C)
        residual = float(charges[i] - nearest)
        rows.append(
            {
                "drop_id": drops[i].get("drop_id", f"drop_{i+1:03d}"),
                "charge_C": float(charges[i]),
                "sigma_charge_C": float(sigmas[i]),
                "n_hat": int(n_i),
                "assignment_probability": float(probabilities[i, n_i - 1]),
                "nearest_quantized_charge_C": nearest,
                "residual_C": residual,
                "normalized_residual": float(residual / max(sigmas[i], 1e-30)),
                "phase_residual": float((charges[i] / fit.e_C) - round(charges[i] / fit.e_C)),
            }
        )
    return rows


def _candidate_modes(fit: QuantizedFit) -> list[dict[str, float]]:
    e_grid = fit.profile_e_C
    profile = fit.profile_log_likelihood
    max_ll = float(np.max(profile))
    indices: set[int] = set()
    for idx in range(1, len(profile) - 1):
        if profile[idx] >= profile[idx - 1] and profile[idx] >= profile[idx + 1]:
            indices.add(idx)
    for target in (fit.e_C / 2.0, fit.e_C * 2.0):
        if e_grid[0] <= target <= e_grid[-1]:
            indices.add(int(np.argmin(np.abs(e_grid - target))))
    indices.add(int(np.argmax(profile)))
    modes = []
    for idx in sorted(indices, key=lambda item: profile[item], reverse=True):
        relative = float(math.exp(min(0.0, float(profile[idx] - max_ll))))
        if relative >= 1e-4:
            modes.append({"e_C": float(e_grid[idx]), "relative_likelihood": relative})
    unique: list[dict[str, float]] = []
    for mode in modes:
        if not any(abs(mode["e_C"] - existing["e_C"]) <= (e_grid[1] - e_grid[0]) * 2 for existing in unique):
            unique.append(mode)
    return unique[:8]


def _profile_interval(fit: QuantizedFit) -> list[float]:
    threshold = fit.log_likelihood - 0.5 * 1.96**2
    mask = fit.profile_log_likelihood >= threshold
    if not np.any(mask):
        return [fit.e_C, fit.e_C]
    return [float(np.min(fit.profile_e_C[mask])), float(np.max(fit.profile_e_C[mask]))]


def _fit_gmm(values: np.ndarray, sigmas: np.ndarray, max_components: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    best: dict[str, Any] | None = None
    values = np.asarray(values, dtype=float)
    n = len(values)
    variance_floor = max(float(np.var(values)) * 1e-4, 1e-60)
    for k in range(1, max(1, max_components) + 1):
        if k == 1:
            weights = np.array([1.0])
            means = np.array([float(np.mean(values))])
            variances = np.array([max(float(np.var(values)), variance_floor)])
        else:
            quantiles = np.linspace(0.1, 0.9, k)
            means = np.quantile(values, quantiles)
            means = means + rng.normal(0.0, math.sqrt(variance_floor), size=k)
            variances = np.full(k, max(float(np.var(values)), variance_floor))
            weights = np.full(k, 1.0 / k)
            for _ in range(80):
                total_sigma = np.sqrt(variances[None, :] + np.square(sigmas[:, None]))
                log_resp = np.log(weights[None, :]) + _normal_logpdf(values[:, None], means[None, :], total_sigma)
                log_norm = logsumexp(log_resp, axis=1)
                resp = np.exp(log_resp - log_norm[:, None])
                nk = np.maximum(resp.sum(axis=0), 1e-12)
                weights = nk / n
                precision = 1.0 / np.maximum(variances[None, :] + np.square(sigmas[:, None]), variance_floor)
                means = (resp * precision * values[:, None]).sum(axis=0) / np.maximum((resp * precision).sum(axis=0), 1e-12)
                raw_variance = (resp * np.square(values[:, None] - means[None, :])).sum(axis=0) / nk
                noise_variance = (resp * np.square(sigmas[:, None])).sum(axis=0) / nk
                variances = np.maximum(raw_variance - noise_variance, variance_floor)
        ll = _continuous_log_likelihood(values, sigmas, {"weights": weights, "means": means, "variances": variances})
        params = 3 * k - 1
        bic = -2 * ll + params * math.log(max(n, 2))
        model = {"weights": weights, "means": means, "variances": variances, "components": k, "log_likelihood": ll, "bic": bic}
        if best is None or bic < best["bic"]:
            best = model
    assert best is not None
    return best


def _continuous_log_likelihood(charges: np.ndarray, sigmas: np.ndarray, model: dict[str, Any]) -> float:
    weights = np.asarray(model["weights"], dtype=float)
    means = np.asarray(model["means"], dtype=float)
    variances = np.asarray(model["variances"], dtype=float)
    total_sigma = np.sqrt(variances[None, :] + np.square(sigmas[:, None]))
    log_components = np.log(weights[None, :]) + _normal_logpdf(charges[:, None], means[None, :], total_sigma)
    return float(np.sum(logsumexp(log_components, axis=1)))


def _cv_splits(n: int, cfg: dict[str, Any]) -> tuple[str, list[tuple[np.ndarray, np.ndarray]], int, int]:
    seed = int(cfg.get("random_seed", 42))
    if n < 20:
        splits = []
        for held_out in range(n):
            test = np.array([held_out], dtype=int)
            train = np.setdiff1d(np.arange(n), test)
            splits.append((train, test))
        return "leave_one_out_predictive_likelihood", splits, n, 1
    folds = 5
    repeats = int(cfg.get("cv_repeats", 3))
    rng = np.random.default_rng(seed)
    splits = []
    for _repeat in range(repeats):
        order = rng.permutation(n)
        for fold in np.array_split(order, folds):
            test = np.asarray(fold, dtype=int)
            train = np.setdiff1d(np.arange(n), test)
            splits.append((train, test))
    return "repeated_5fold_predictive_likelihood", splits, folds, repeats


def _comparison_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    comparison_grid = int(cfg.get("comparison_profile_grid_points", min(int(_cfg_value(cfg, "profile_grid_points", "grid_points", 800)), 120)))
    return {
        **cfg,
        "profile_grid_points": max(40, comparison_grid),
        "tau_lambda_profile_optimize_points": int(cfg.get("comparison_tau_lambda_profile_optimize_points", min(int(cfg.get("tau_lambda_profile_optimize_points", 16)), 2))),
        "tau_lambda_optimizer_maxiter": int(cfg.get("comparison_tau_lambda_optimizer_maxiter", min(int(cfg.get("tau_lambda_optimizer_maxiter", 80)), 20))),
    }


def _predictive_model_comparison(charges: np.ndarray, sigmas: np.ndarray, cfg: dict[str, Any], *, include_null: bool = True) -> dict[str, object]:
    if len(charges) < 3:
        return {
            "continuous_model": "heteroscedastic_error_convolved_gmm",
            "heteroscedastic": True,
            "comparison_method": "insufficient_drops",
            "quantized_elpd": math.nan,
            "continuous_elpd": math.nan,
            "delta_elpd": math.nan,
            "evidence_label": "insufficient",
        }
    seed = int(cfg.get("random_seed", 42))
    fit_cfg = _comparison_cfg(cfg)
    quantized_scores = []
    continuous_scores = []
    method, splits, folds, repeats = _cv_splits(len(charges), cfg)
    per_split_delta = []
    for split_index, (train_idx, test_idx) in enumerate(splits):
        train_charges = charges[train_idx]
        train_sigmas = sigmas[train_idx]
        test_charge = charges[test_idx]
        test_sigma = sigmas[test_idx]
        q_fit = _fit_quantized_profile(train_charges, train_sigmas, fit_cfg)
        e_min = float(_cfg_value(cfg, "e_search_min_C", "e_min_C", 0.5e-19))
        nmax = max(1, int(math.ceil(float(max(np.max(train_charges), np.max(test_charge))) / e_min)) + 1)
        q_score = _quantized_log_likelihood(test_charge, test_sigma, q_fit.e_C, q_fit.tau_C, q_fit.lambda_decay, nmax)
        max_components = min(4, max(1, len(train_charges) // 3))
        c_model = _fit_gmm(train_charges, train_sigmas, max_components=max_components, seed=seed + split_index)
        c_score = _continuous_log_likelihood(test_charge, test_sigma, c_model)
        quantized_scores.append(q_score)
        continuous_scores.append(c_score)
        per_split_delta.append(float(q_score - c_score))
    quantized_elpd = float(np.sum(quantized_scores))
    continuous_elpd = float(np.sum(continuous_scores))
    delta = quantized_elpd - continuous_elpd
    final_model = _fit_gmm(charges, sigmas, max_components=min(4, max(1, len(charges) // 3)), seed=seed)
    delta_arr = np.asarray(per_split_delta, dtype=float)
    comparison: dict[str, object] = {
        "continuous_model": "heteroscedastic_error_convolved_gmm",
        "heteroscedastic": True,
        "continuous_components": int(final_model["components"]),
        "continuous_bic": float(final_model["bic"]),
        "comparison_method": method,
        "folds": int(folds),
        "repeats": int(repeats),
        "per_split_delta_elpd": per_split_delta,
        "delta_elpd_se": float(np.std(delta_arr, ddof=1) / math.sqrt(len(delta_arr))) if len(delta_arr) > 1 else 0.0,
        "quantized_elpd": quantized_elpd,
        "continuous_elpd": continuous_elpd,
        "delta_elpd": delta,
        "evidence_label": "not_calibrated",
    }
    null_samples = int(cfg.get("null_simulation_samples", 0)) if include_null else 0
    if null_samples > 0:
        rng = np.random.default_rng(seed + 7919)
        weights = np.asarray(final_model["weights"], dtype=float)
        means = np.asarray(final_model["means"], dtype=float)
        variances = np.asarray(final_model["variances"], dtype=float)
        null_delta = []
        for _ in range(null_samples):
            components = rng.choice(len(weights), size=len(charges), p=weights)
            latent = rng.normal(means[components], np.sqrt(variances[components]))
            simulated = rng.normal(latent, sigmas)
            sim = _predictive_model_comparison(simulated, sigmas, {**fit_cfg, "null_simulation_samples": 0}, include_null=False)
            null_delta.append(float(sim["delta_elpd"]))
        count = sum(1 for value in null_delta if value >= delta)
        p_null = (1 + count) / (null_samples + 1)
        if p_null <= 0.01 and delta > 0:
            label = "strong"
        elif p_null <= 0.05 and delta > 0:
            label = "moderate"
        elif p_null <= 0.20 and delta > 0:
            label = "weak"
        else:
            label = "insufficient"
        comparison["evidence_label"] = label
        comparison["null_simulation"] = {
            "samples": int(null_samples),
            "empirical_p_value": float(p_null),
            "observed_delta_elpd": float(delta),
            "null_delta_elpd_distribution": null_delta,
            "seed": int(seed + 7919),
        }
    return comparison


def _bootstrap_e(charges: np.ndarray, sigmas: np.ndarray, cfg: dict[str, Any]) -> list[float]:
    samples = int(_cfg_value(cfg, "e_bootstrap_samples", "bootstrap_samples", 0))
    if samples <= 0:
        return []
    rng = random.Random(int(cfg.get("random_seed", 42)))
    boot = []
    for _ in range(samples):
        indices = [rng.randrange(len(charges)) for _ in range(len(charges))]
        try:
            sample_fit = _fit_quantized_profile(charges[indices], sigmas[indices], cfg)
            boot.append(float(sample_fit.e_C))
        except ValueError:
            continue
    return boot


def _measurement_mc_e(charges: np.ndarray, sigmas: np.ndarray, cfg: dict[str, Any]) -> list[float]:
    samples = int(cfg.get("measurement_mc_samples", 0))
    if samples <= 0:
        return []
    rng = np.random.default_rng(int(cfg.get("random_seed", 42)) + 104729)
    estimates = []
    for _ in range(samples):
        sampled = rng.normal(charges, sigmas)
        sampled = np.maximum(sampled, 1e-30)
        try:
            sample_fit = _fit_quantized_profile(sampled, sigmas, cfg)
            estimates.append(float(sample_fit.e_C))
        except ValueError:
            continue
    return estimates


def _leave_one_drop_out_stability(charges: np.ndarray, sigmas: np.ndarray, drops: list[dict], cfg: dict[str, Any], e_hat: float) -> list[dict[str, object]]:
    if len(charges) < 4:
        return []
    fit_cfg = _comparison_cfg(cfg)
    rows = []
    for index, drop in enumerate(drops):
        mask = np.ones(len(charges), dtype=bool)
        mask[index] = False
        try:
            fit = _fit_quantized_profile(charges[mask], sigmas[mask], fit_cfg)
            rows.append(
                {
                    "drop_id": drop.get("drop_id", f"drop_{index+1:03d}"),
                    "valid": True,
                    "e_hat_C": float(fit.e_C),
                    "delta_from_full_C": float(fit.e_C - e_hat),
                }
            )
        except ValueError as exc:
            rows.append(
                {
                    "drop_id": drop.get("drop_id", f"drop_{index+1:03d}"),
                    "valid": False,
                    "reason": str(exc),
                }
            )
    return rows


def estimate_elementary_charge(drop_results: list[dict], config: dict) -> dict[str, object]:
    cfg = config["elementary"]
    valid = _usable_drops(drop_results)
    min_drops = int(_cfg_value(cfg, "min_drops_for_estimation", "min_drops", 3))
    if len(valid) == 1:
        return {
            "valid": False,
            "flags": ["insufficient_independent_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": 1,
            "reason": "Blind elementary-charge estimation requires multiple independent q_i values.",
        }
    if len(valid) < min_drops:
        return {
            "valid": False,
            "flags": ["insufficient_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": len(valid),
        }
    charges = np.array([float(drop["result"]["charge_abs_C"]) for drop in valid], dtype=float)
    sigmas = np.array([float(drop["result"]["sigma_charge_C"]) for drop in valid], dtype=float)
    finite = np.isfinite(charges) & np.isfinite(sigmas) & (charges > 0) & (sigmas >= 0)
    charges = charges[finite]
    sigmas = sigmas[finite]
    valid = [drop for drop, keep in zip(valid, finite.tolist()) if keep]
    if len(valid) < min_drops:
        return {
            "valid": False,
            "flags": ["insufficient_finite_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": len(valid),
        }
    positive_sigmas = sigmas[sigmas > 0]
    numerical_floor = max(float(np.median(positive_sigmas)) * 1e-6, 1e-30) if len(positive_sigmas) else 1e-30
    sigmas = np.maximum(sigmas, numerical_floor)
    fit = _fit_quantized_profile(charges, sigmas, cfg)
    assignments = _assignment_rows(charges, sigmas, fit, valid)
    modes = _candidate_modes(fit)
    significant_modes = [mode for mode in modes if mode["relative_likelihood"] >= 0.02]
    harmonic = len(significant_modes) >= 2
    boot = _bootstrap_e(charges, sigmas, cfg)
    ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))] if boot else [fit.e_C, fit.e_C]
    measurement_mc = _measurement_mc_e(charges, sigmas, cfg)
    measurement_ci = (
        [float(np.percentile(measurement_mc, 2.5)), float(np.percentile(measurement_mc, 97.5))]
        if measurement_mc
        else [fit.e_C, fit.e_C]
    )
    e_min = float(_cfg_value(cfg, "e_search_min_C", "e_min_C", 0.5e-19))
    e_max = float(_cfg_value(cfg, "e_search_max_C", "e_max_C", 2.5e-19))
    comparison = _predictive_model_comparison(charges, sigmas, cfg)
    leave_one_drop_out = _leave_one_drop_out_stability(charges, sigmas, valid, cfg, fit.e_C)
    return {
        "valid": True,
        "num_total_drops": len(drop_results),
        "num_used_drops": len(valid),
        "elementary_charge": {
            "e_hat_C": float(fit.e_C),
            "e_hat_1e_minus_19_C": float(fit.e_C / 1e-19),
            "sigma_e_C": float(np.std(boot, ddof=1)) if len(boot) > 1 else 0.0,
            "ci_95_C": ci,
            "e_ci_95_C": ci,
            "profile_ci_95_C": _profile_interval(fit),
            "measurement_mc_ci_95_C": measurement_ci,
            "uncertainty_method": "profile_bootstrap_measurement_mc",
            "bootstrap_samples_used": int(len(boot)),
            "measurement_mc_samples_used": int(len(measurement_mc)),
            "search_interval_C": [e_min, e_max],
            "blind_estimation": "bounded_interval_no_reference_e_input",
            "tau_C": float(fit.tau_C),
            "lambda_decay": float(fit.lambda_decay),
        },
        "optimizer": fit.optimizer,
        "drops": assignments,
        "harmonic_analysis": {
            "harmonic_ambiguity": bool(harmonic),
            "candidate_modes": modes,
        },
        "model_comparison": {
            "weighted_residual_rms_C": float(
                math.sqrt(np.mean([row["residual_C"] ** 2 for row in assignments]))
            ),
            "method": "bounded_profile_quantized_likelihood",
            "log_likelihood": float(fit.log_likelihood),
            **comparison,
        },
        "stability": {
            "leave_one_drop_out": leave_one_drop_out,
        },
        "flags": ["harmonic_ambiguity"] if harmonic else [],
    }
