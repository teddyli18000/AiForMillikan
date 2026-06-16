from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

E_PRIOR_MIN_C = 1.35e-19
E_PRIOR_MAX_C = 1.90e-19


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


def _predeclared_prior_interval() -> tuple[float, float]:
    return E_PRIOR_MIN_C, E_PRIOR_MAX_C


def _prior_metadata(cfg: dict[str, Any]) -> dict[str, Any]:
    ignored_keys = [key for key in ["e_search_min_C", "e_search_max_C", "e_min_C", "e_max_C"] if key in cfg]
    return {
        "prior_constrained": True,
        "prior_type": "predeclared_physical_interval",
        "search_interval_C": [E_PRIOR_MIN_C, E_PRIOR_MAX_C],
        "exact_reference_e_used": False,
        "user_configurable": False,
        "search_interval_override_ignored": bool(ignored_keys),
        "ignored_override_keys": ignored_keys,
    }


def _usable_drops(drop_results: list[dict]) -> list[dict]:
    usable = []
    for drop in drop_results:
        result = drop.get("result", {}) or {}
        try:
            charge = float(result.get("charge_abs_C", math.nan))
            sigma = float(result.get("sigma_charge_C", math.nan))
        except (TypeError, ValueError):
            continue
        if drop.get("valid") and math.isfinite(charge) and charge > 0 and math.isfinite(sigma) and sigma > 0:
            usable.append(drop)
    return usable


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
    e_min, e_max = _predeclared_prior_interval()
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
    failed_candidate_log_likelihoods: list[float] = []
    retry_attempt_failures = 0
    optimize_count = min(len(e_grid), int(cfg.get("tau_lambda_profile_optimize_points", 16)))
    candidate_indices = set(np.argsort(profile_arr)[-optimize_count:].tolist())
    local_peak_indices = []
    for idx in range(1, len(profile_arr) - 1):
        if profile_arr[idx] >= profile_arr[idx - 1] and profile_arr[idx] >= profile_arr[idx + 1]:
            local_peak_indices.append(idx)
    max_local_modes = max(1, int(cfg.get("max_profile_modes_to_optimize", 96)))
    optimized_local_peak_indices = sorted(local_peak_indices, key=lambda item: profile_arr[item], reverse=True)[:max_local_modes]
    omitted_local_peak_indices = [idx for idx in local_peak_indices if idx not in set(optimized_local_peak_indices)]
    coarse_max = float(np.max(profile_arr))
    omitted_threshold = float(cfg.get("omitted_mode_relative_likelihood_threshold", cfg.get("mode_relative_likelihood_threshold", 0.02)))
    important_omitted_local_peaks = [
        idx
        for idx in omitted_local_peak_indices
        if math.exp(min(0.0, float(profile_arr[idx] - coarse_max))) >= omitted_threshold
    ]
    for idx in optimized_local_peak_indices:
        candidate_indices.add(idx)
    for idx in list(candidate_indices):
        if idx > 0:
            candidate_indices.add(idx - 1)
        if idx < len(e_grid) - 1:
            candidate_indices.add(idx + 1)
    tau_scale = max(median_sigma, 1e-30)

    def optimize_at_index(idx: int) -> tuple[float, float, float, bool, int, int]:
        e_C = float(e_grid[idx])
        _ll0, tau0, lambda0 = coarse_best_by_e[idx]

        def objective(params: np.ndarray) -> float:
            tau_factor = float(params[0])
            lambda_decay = float(params[1])
            tau_C = tau_factor * tau_scale
            return -_quantized_log_likelihood(charges, sigmas, e_C, tau_C, lambda_decay, nmax)

        starts: list[np.ndarray] = [
            np.array([max(0.0, tau0 / tau_scale), max(0.0, lambda0)], dtype=float),
        ]
        for neighbor in [idx - 1, idx + 1]:
            if 0 <= neighbor < len(coarse_best_by_e):
                _ll_neighbor, tau_neighbor, lambda_neighbor = coarse_best_by_e[neighbor]
                starts.append(np.array([max(0.0, tau_neighbor / tau_scale), max(0.0, lambda_neighbor)], dtype=float))
        starts.extend(
            [
                np.array([0.0, max(0.0, lambda0)], dtype=float),
                np.array([1.0, 0.75], dtype=float),
                np.array([4.0, 3.0], dtype=float),
            ]
        )
        unique_starts: list[np.ndarray] = []
        for start in starts:
            clipped = np.array([min(20.0, max(0.0, float(start[0]))), min(12.0, max(0.0, float(start[1])))])
            if not any(np.allclose(clipped, existing, rtol=0.0, atol=1e-12) for existing in unique_starts):
                unique_starts.append(clipped)
        maxiter = int(cfg.get("tau_lambda_optimizer_maxiter", 80))
        best_failed: tuple[float, float, float] | None = (float(_ll0), float(tau0), float(lambda0))
        eval_total = 0
        attempt_failures = 0
        methods = ["L-BFGS-B", "Powell"]
        for method in methods:
            for start in unique_starts:
                options = {"maxiter": maxiter if method == "L-BFGS-B" else max(maxiter * 2, 80)}
                result = minimize(
                    objective,
                    start,
                    method=method,
                    bounds=[(0.0, 20.0), (0.0, 12.0)],
                    options=options,
                )
                eval_total += int(getattr(result, "nfev", 0) or 0)
                fun = float(getattr(result, "fun", math.inf))
                x = np.asarray(getattr(result, "x", start), dtype=float)
                if math.isfinite(fun) and len(x) >= 2:
                    ll = -fun
                    tau_candidate = float(x[0]) * tau_scale
                    lambda_candidate = float(x[1])
                    if best_failed is None or ll > best_failed[0]:
                        best_failed = (ll, tau_candidate, lambda_candidate)
                    if bool(getattr(result, "success", False)):
                        return ll, tau_candidate, lambda_candidate, True, eval_total, attempt_failures
                attempt_failures += 1
        if best_failed is None:
            best_failed = (float(_ll0), float(tau0), float(lambda0))
        return best_failed[0], best_failed[1], best_failed[2], False, eval_total, attempt_failures

    for idx in sorted(candidate_indices):
        ll, tau_C, lambda_decay, success, eval_count, attempt_failures = optimize_at_index(idx)
        n_eval += eval_count
        retry_attempt_failures += attempt_failures
        if not success:
            failed_optimizations += 1
            failed_candidate_log_likelihoods.append(float(ll))
        profile_arr[idx] = ll
        if ll > best[0]:
            best = (ll, float(e_grid[idx]), tau_C, lambda_decay)
    local_modes_optimized = sum(1 for idx in local_peak_indices if idx in candidate_indices)
    failed_candidate_could_win = any(ll >= best[0] for ll in failed_candidate_log_likelihoods)
    profile_optimization_incomplete = bool(failed_optimizations > 0 or important_omitted_local_peaks)
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
            "retry_attempt_failures": int(retry_attempt_failures),
            "failed_candidate_could_win": bool(failed_candidate_could_win),
            "local_modes_found": int(len(local_peak_indices)),
            "local_modes_optimized": int(local_modes_optimized),
            "local_modes_omitted": int(max(0, len(local_peak_indices) - local_modes_optimized)),
            "important_local_modes_omitted": int(len(important_omitted_local_peaks)),
            "omitted_mode_relative_likelihood_threshold": float(omitted_threshold),
            "profile_optimization_incomplete": profile_optimization_incomplete,
            "selected_by": "maximum_profile_likelihood",
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
        effective_sigma = float(math.sqrt(float(sigmas[i]) ** 2 + fit.tau_C**2))
        rows.append(
            {
                "drop_id": drops[i].get("drop_id", f"drop_{i+1:03d}"),
                "charge_C": float(charges[i]),
                "sigma_charge_C": float(sigmas[i]),
                "n_hat": int(n_i),
                "assignment_probability": float(probabilities[i, n_i - 1]),
                "assignment_probability_given_e": float(probabilities[i, n_i - 1]),
                "conditional_on_e_C": float(fit.e_C),
                "nearest_quantized_charge_C": nearest,
                "residual_C": residual,
                "effective_sigma_C": effective_sigma,
                "normalized_residual": float(residual / max(effective_sigma, 1e-30)),
                "phase_residual": float((charges[i] / fit.e_C) - round(charges[i] / fit.e_C)),
            }
        )
    return rows


def _candidate_modes(fit: QuantizedFit, cfg: dict[str, Any] | None = None) -> list[dict[str, float]]:
    cfg = cfg or {}
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
    min_relative = float(cfg.get("candidate_mode_min_relative_likelihood", 1e-4))
    for idx in sorted(indices, key=lambda item: profile[item], reverse=True):
        relative = float(math.exp(min(0.0, float(profile[idx] - max_ll))))
        if relative >= min_relative:
            modes.append({"e_C": float(e_grid[idx]), "relative_likelihood": relative})
    unique: list[dict[str, float]] = []
    for mode in modes:
        if not any(abs(mode["e_C"] - existing["e_C"]) <= (e_grid[1] - e_grid[0]) * 2 for existing in unique):
            unique.append(mode)
    return unique[:8]


def _profile_intervals(fit: QuantizedFit) -> list[list[float]]:
    threshold = fit.log_likelihood - 0.5 * 1.96**2
    mask = fit.profile_log_likelihood >= threshold
    if not np.any(mask):
        return [[fit.e_C, fit.e_C]]
    intervals: list[list[float]] = []
    start: int | None = None
    for idx, keep in enumerate(mask.tolist()):
        if keep and start is None:
            start = idx
        if start is not None and (not keep or idx == len(mask) - 1):
            end = idx if keep and idx == len(mask) - 1 else idx - 1
            intervals.append([float(fit.profile_e_C[start]), float(fit.profile_e_C[end])])
            start = None
    return intervals


def _primary_profile_interval(fit: QuantizedFit, intervals: list[list[float]]) -> list[float]:
    for low, high in intervals:
        if low <= fit.e_C <= high:
            return [float(low), float(high)]
    return min(intervals, key=lambda item: min(abs(fit.e_C - item[0]), abs(fit.e_C - item[1]))) if intervals else [fit.e_C, fit.e_C]


def _profile_interval(fit: QuantizedFit) -> list[float]:
    intervals = _profile_intervals(fit)
    return _primary_profile_interval(fit, intervals)


def _is_harmonic_ratio(value_a: float, value_b: float, cfg: dict[str, Any]) -> bool:
    if value_a <= 0 or value_b <= 0:
        return False
    ratio = max(value_a, value_b) / min(value_a, value_b)
    tolerance = float(cfg.get("harmonic_ratio_tolerance", 0.04))
    max_integer = int(cfg.get("harmonic_integer_max", 4))
    for integer in range(2, max(2, max_integer) + 1):
        if abs(ratio - float(integer)) <= tolerance:
            return True
    return False


def _boundary_diagnostics(fit: QuantizedFit) -> dict[str, Any]:
    e_min, e_max = _predeclared_prior_interval()
    span = e_max - e_min
    grid_step = float(fit.profile_e_C[1] - fit.profile_e_C[0]) if len(fit.profile_e_C) > 1 else span
    distance = min(abs(float(fit.e_C) - e_min), abs(e_max - float(fit.e_C)))
    threshold = max(2.0 * grid_step, 0.02 * span)
    return {
        "search_boundary_hit": bool(distance <= threshold),
        "boundary_distance_C": float(distance),
        "boundary_distance_grid_steps": float(distance / grid_step) if grid_step > 0 else math.inf,
        "boundary_guard_threshold_C": float(threshold),
    }


def _gcd(values: list[int]) -> int:
    current = 0
    for value in values:
        current = math.gcd(current, int(abs(value)))
    return int(current)


def _primitive_assignment_diagnostics(assignments: list[dict[str, object]], cfg: dict[str, Any]) -> dict[str, Any]:
    confidence_threshold = float(cfg.get("assignment_confidence_threshold", 0.80))
    divisor_threshold = float(cfg.get("common_divisor_fraction_threshold", 0.80))
    min_samples = int(cfg.get("primitive_min_high_confidence_samples", 3))
    high_conf = [
        int(row["n_hat"])
        for row in assignments
        if float(row.get("assignment_probability_given_e", row.get("assignment_probability", 0.0)) or 0.0) >= confidence_threshold
    ]
    gcd_value = _gcd(high_conf) if high_conf else 0
    ratios: dict[str, float] = {}
    for divisor in range(2, 13):
        ratios[str(divisor)] = (
            float(sum(1 for value in high_conf if value % divisor == 0) / len(high_conf)) if high_conf else 0.0
        )
    has_common_divisor = bool(
        len(high_conf) >= min_samples
        and (gcd_value > 1 or any(value >= divisor_threshold for value in ratios.values()))
    )
    enough_support = len(high_conf) >= min_samples
    return {
        "primitive_assignment_supported": bool(enough_support and not has_common_divisor),
        "high_confidence_assignment_count": int(len(high_conf)),
        "high_confidence_threshold": float(confidence_threshold),
        "integer_gcd": int(gcd_value),
        "divisible_fraction_by_integer": ratios,
        "common_divisor_fraction_threshold": float(divisor_threshold),
        "min_high_confidence_samples": int(min_samples),
        "has_common_divisor_evidence": bool(has_common_divisor),
    }


def _mode_proportions(samples: list[float], fit: QuantizedFit, modes: list[dict[str, float]], cfg: dict[str, Any]) -> dict[str, Any]:
    if not samples:
        return {"samples": 0, "main_mode_fraction": None, "harmonic_mode_fraction": None, "other_mode_fraction": None}
    e_min, e_max = _predeclared_prior_interval()
    grid_step = float(fit.profile_e_C[1] - fit.profile_e_C[0]) if len(fit.profile_e_C) > 1 else (e_max - e_min)
    tolerance = max(2.0 * grid_step, 0.02 * (e_max - e_min))
    main = 0
    harmonic = 0
    other = 0
    harmonic_modes = [float(mode["e_C"]) for mode in modes if _is_harmonic_ratio(float(mode["e_C"]), float(fit.e_C), cfg)]
    for value in samples:
        sample = float(value)
        if abs(sample - float(fit.e_C)) <= tolerance:
            main += 1
        elif any(abs(sample - mode) <= tolerance for mode in harmonic_modes):
            harmonic += 1
        else:
            other += 1
    total = len(samples)
    return {
        "samples": int(total),
        "main_mode_fraction": float(main / total),
        "harmonic_mode_fraction": float(harmonic / total),
        "other_mode_fraction": float(other / total),
        "mode_tolerance_C": float(tolerance),
    }


def _quantization_supported(comparison: dict[str, Any], cfg: dict[str, Any]) -> bool | None:
    null = comparison.get("null_simulation")
    delta = comparison.get("delta_elpd")
    if not null or not bool(cfg.get("enable_calibrated_evidence_labels", False)):
        return None
    try:
        p_value = float(null.get("empirical_p_value"))
        delta_value = float(delta)
    except (TypeError, ValueError):
        return False
    return bool(math.isfinite(p_value) and math.isfinite(delta_value) and delta_value > 0 and p_value <= 0.05)


def _quantization_favored(comparison: dict[str, Any]) -> bool | None:
    try:
        delta = float(comparison.get("delta_elpd"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(delta):
        return None
    return bool(delta > 0)


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
            "continuous_model": "approximate_heteroscedastic_deconvolved_gmm",
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
        e_min, _e_max = _predeclared_prior_interval()
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
        "continuous_model": "approximate_heteroscedastic_deconvolved_gmm",
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
        if bool(cfg.get("enable_calibrated_evidence_labels", False)):
            if p_null <= 0.01 and delta > 0:
                label = "strong"
            elif p_null <= 0.05 and delta > 0:
                label = "moderate"
            elif p_null <= 0.20 and delta > 0:
                label = "weak"
            else:
                label = "insufficient"
        else:
            label = "not_calibrated"
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
            "fit_valid": False,
            "bounded_estimate_available": False,
            "quantization_favored": None,
            "quantization_supported": None,
            "primitive_assignment_supported": False,
            "fundamental_spacing_identified": False,
            "status": "insufficient_independent_drops",
            "flags": ["insufficient_independent_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": 1,
            "reason": "Blind elementary-charge estimation requires multiple independent q_i values.",
        }
    if len(valid) < min_drops:
        return {
            "valid": False,
            "fit_valid": False,
            "bounded_estimate_available": False,
            "quantization_favored": None,
            "quantization_supported": None,
            "primitive_assignment_supported": False,
            "fundamental_spacing_identified": False,
            "status": "insufficient_drops",
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
            "fit_valid": False,
            "bounded_estimate_available": False,
            "quantization_favored": None,
            "quantization_supported": None,
            "primitive_assignment_supported": False,
            "fundamental_spacing_identified": False,
            "status": "insufficient_finite_drops",
            "flags": ["insufficient_finite_drops"],
            "num_total_drops": len(drop_results),
            "num_used_drops": len(valid),
        }
    positive_sigmas = sigmas[sigmas > 0]
    numerical_floor = max(float(np.median(positive_sigmas)) * 1e-6, 1e-30) if len(positive_sigmas) else 1e-30
    sigmas = np.maximum(sigmas, numerical_floor)
    fit = _fit_quantized_profile(charges, sigmas, cfg)
    assignments = _assignment_rows(charges, sigmas, fit, valid)
    modes = _candidate_modes(fit, cfg)
    significant_threshold = float(cfg.get("mode_relative_likelihood_threshold", 0.02))
    significant_modes = [mode for mode in modes if mode["relative_likelihood"] >= significant_threshold]
    profile_multimodal = len(significant_modes) >= 2
    harmonic = any(
        _is_harmonic_ratio(float(a["e_C"]), float(b["e_C"]), cfg)
        for index, a in enumerate(significant_modes)
        for b in significant_modes[index + 1 :]
    )
    boot = _bootstrap_e(charges, sigmas, cfg)
    ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))] if boot else [fit.e_C, fit.e_C]
    measurement_mc = _measurement_mc_e(charges, sigmas, cfg)
    measurement_ci = (
        [float(np.percentile(measurement_mc, 2.5)), float(np.percentile(measurement_mc, 97.5))]
        if measurement_mc
        else [fit.e_C, fit.e_C]
    )
    e_min, e_max = _predeclared_prior_interval()
    if bool(cfg.get("skip_model_comparison", False)):
        comparison = {
            "continuous_model": "approximate_heteroscedastic_deconvolved_gmm",
            "heteroscedastic": True,
            "comparison_method": "skipped",
            "quantized_elpd": math.nan,
            "continuous_elpd": math.nan,
            "delta_elpd": math.nan,
            "delta_elpd_se": math.nan,
            "evidence_label": "not_run",
        }
    else:
        comparison = _predictive_model_comparison(charges, sigmas, cfg)
    leave_one_drop_out = [] if bool(cfg.get("skip_stability_diagnostics", False)) else _leave_one_drop_out_stability(charges, sigmas, valid, cfg, fit.e_C)
    profile_intervals = _profile_intervals(fit)
    primary_profile_interval = _primary_profile_interval(fit, profile_intervals)
    boundary = _boundary_diagnostics(fit)
    primitive = _primitive_assignment_diagnostics(assignments, cfg)
    bootstrap_modes = _mode_proportions(boot, fit, modes, cfg)
    measurement_modes = _mode_proportions(measurement_mc, fit, modes, cfg)
    mode_threshold = float(cfg.get("mode_stability_min_main_fraction", 0.80))
    mode_instability = any(
        mode_info["samples"] > 0 and float(mode_info["main_mode_fraction"]) < mode_threshold
        for mode_info in [bootstrap_modes, measurement_modes]
    )
    quantization_favored = _quantization_favored(comparison)
    quantization_supported = _quantization_supported(comparison, cfg)
    fit_valid = bool(math.isfinite(float(fit.e_C)) and math.isfinite(float(fit.log_likelihood)))
    bounded_estimate_available = bool(fit_valid and e_min <= float(fit.e_C) <= e_max)
    profile_incomplete = bool(fit.optimizer.get("profile_optimization_incomplete", False))
    flags: list[str] = []
    if boundary["search_boundary_hit"]:
        flags.append("prior_boundary_hit")
    if profile_incomplete:
        flags.append("profile_optimization_incomplete")
    if harmonic:
        flags.append("harmonic_ambiguity")
    if mode_instability:
        flags.append("mode_instability")
    if not primitive["primitive_assignment_supported"]:
        flags.append("integer_assignments_nonprimitive")
    if quantization_supported is None:
        flags.append("evidence_not_calibrated")
    elif not quantization_supported:
        flags.append("quantization_not_supported")
    if not bounded_estimate_available:
        status = "bounded_estimate_unavailable"
    elif boundary["search_boundary_hit"]:
        status = "prior_boundary_hit"
    elif profile_incomplete:
        status = "profile_optimization_incomplete"
    elif not primitive["primitive_assignment_supported"]:
        status = "integer_assignments_nonprimitive"
    elif harmonic or mode_instability:
        status = "mode_instability"
    elif quantization_supported is not True:
        status = "bounded_estimate_evidence_not_calibrated" if quantization_supported is None else "quantization_not_supported"
    else:
        status = "fundamental_spacing_identified"
    fundamental_identified = bool(
        fit_valid
        and bounded_estimate_available
        and not boundary["search_boundary_hit"]
        and not profile_incomplete
        and not harmonic
        and not mode_instability
        and primitive["primitive_assignment_supported"]
        and quantization_supported is True
    )
    comparison["quantization_favored"] = quantization_favored
    comparison["quantization_supported"] = quantization_supported
    comparison["fundamental_spacing_identified"] = fundamental_identified
    return {
        "valid": True,
        "fit_valid": fit_valid,
        "bounded_estimate_available": bounded_estimate_available,
        "quantization_favored": quantization_favored,
        "quantization_supported": quantization_supported,
        "primitive_assignment_supported": primitive["primitive_assignment_supported"],
        "fundamental_spacing_identified": fundamental_identified,
        "status": status,
        "num_total_drops": len(drop_results),
        "num_used_drops": len(valid),
        "elementary_charge": {
            "e_hat_C": float(fit.e_C),
            "e_hat_1e_minus_19_C": float(fit.e_C / 1e-19),
            "sigma_e_C": float(np.std(boot, ddof=1)) if len(boot) > 1 else 0.0,
            "ci_95_C": ci,
            "e_ci_95_C": ci,
            "profile_intervals_C": profile_intervals,
            "primary_profile_interval_C": primary_profile_interval,
            "profile_ci_95_C": primary_profile_interval,
            "measurement_mc_ci_95_C": measurement_ci,
            "uncertainty_method": "profile_bootstrap_measurement_mc",
            "bootstrap_samples_used": int(len(boot)),
            "measurement_mc_samples_used": int(len(measurement_mc)),
            "search_interval_C": [e_min, e_max],
            "prior": _prior_metadata(cfg),
            "blind_estimation": "predeclared_physical_interval_no_exact_reference_e_input",
            "tau_C": float(fit.tau_C),
            "lambda_decay": float(fit.lambda_decay),
        },
        "optimizer": fit.optimizer,
        "drops": assignments,
        "harmonic_analysis": {
            "profile_multimodal": bool(profile_multimodal),
            "harmonic_ambiguity": bool(harmonic),
            "candidate_modes": modes,
            "mode_relative_likelihood_threshold": significant_threshold,
            "harmonic_ratio_tolerance": float(cfg.get("harmonic_ratio_tolerance", 0.04)),
        },
        "model_comparison": {
            "weighted_residual_rms_C": float(
                math.sqrt(np.mean([row["residual_C"] ** 2 for row in assignments]))
            ),
            "method": "bounded_profile_quantized_likelihood",
            "log_likelihood": float(fit.log_likelihood),
            **comparison,
        },
        "boundary_guard": boundary,
        "primitive_assignment": primitive,
        "mode_stability": {
            "main_mode_min_fraction_required": mode_threshold,
            "mode_instability": bool(mode_instability),
            "bootstrap": bootstrap_modes,
            "measurement_mc": measurement_modes,
        },
        "stability": {
            "leave_one_drop_out": leave_one_drop_out,
        },
        "flags": flags,
    }
