from __future__ import annotations

import numpy as np
import pytest

from metafrontier.core import FrontierMetaAnalyzer


def test_numeric_covariance_matches_quadratic_hessian() -> None:
    analyzer = FrontierMetaAnalyzer()

    def objective(params: np.ndarray) -> float:
        x, y = params
        return (x - 1.0) ** 2 + 4.0 * (y + 2.0) ** 2

    cov = analyzer._extract_covariance(objective, np.array([1.0, -2.0]))

    assert cov is not None
    assert cov[0, 0] == pytest.approx(0.5, rel=1e-2)
    assert cov[1, 1] == pytest.approx(0.125, rel=1e-2)
    assert cov[0, 1] == pytest.approx(0.0, abs=1e-6)


def test_profile_target_se_matches_quadratic_profile_curvature() -> None:
    analyzer = FrontierMetaAnalyzer()
    variance = 0.49
    x_target = np.array([2.0])
    params = np.array([0.4, 0.0, 0.3])

    def objective(raw_params: np.ndarray) -> float:
        mu, log_tau, beta = raw_params
        target = mu + 2.0 * beta
        return 0.5 * ((target - 1.0) ** 2) / variance + 0.5 * ((beta - 0.3) ** 2) / 0.2 + 0.5 * (log_tau**2) / 0.1

    se = analyzer._profile_target_se(objective, params, x_target, include_small=False)

    assert se is not None
    assert se == pytest.approx(np.sqrt(variance), rel=5e-2)


def test_mixture_interval_matches_single_normal_quantiles() -> None:
    analyzer = FrontierMetaAnalyzer()
    weights = np.array([1.0])
    means = np.array([0.2])
    variances = np.array([0.49])

    ci_low, ci_high, method = analyzer._mixture_interval(weights, means, variances, fallback_mean=0.2, fallback_se=0.7)

    assert method == "stacked_normal_mixture"
    assert ci_low == pytest.approx(0.2 - 1.959963984540054 * 0.7, rel=1e-4)
    assert ci_high == pytest.approx(0.2 + 1.959963984540054 * 0.7, rel=1e-4)
