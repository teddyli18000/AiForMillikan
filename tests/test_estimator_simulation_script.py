from scripts.validate_estimator_simulation import run_simulation


def test_estimator_simulation_script_smoke_runs_small_case():
    result = run_simulation("configs/default.yaml", replicates=1, seed=123, profile_points=40, null_samples=0, n_values=(10,), noise_values=(0.06,))

    assert {"quantized_valid_count", "mean_bias_C", "coverage_rate", "continuous_false_strong_rate"}.issubset(result["summary"])
    assert result["summary"]["quantized_valid_count"] > 0
    assert len(result["quantized"]) == 1
    assert len(result["continuous"]) == 1
