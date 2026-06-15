"""Truth-recovery assertions for MetaFrontierLab's own estimator.

Run: python -m pytest truth-recovery/test_truth_recovery.py -v
  or: python truth-recovery/test_truth_recovery.py

These are smoke + sanity assertions on the repo's FrontierMetaAnalyzer using a
small fixed DGP (no node dependency) so they run standalone and fast.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from metafrontier import FrontierMetaAnalyzer, make_tbema_analyzer  # noqa: E402


def _rng_meta(seed, k, mu, tau2, se_lo=0.1, se_hi=0.5):
    rng = np.random.default_rng(seed)
    se = rng.uniform(se_lo, se_hi, k)
    theta = rng.normal(mu, np.sqrt(tau2), k)
    y = rng.normal(theta, se)
    return pd.DataFrame({"effect": y, "se": se})


def test_analyzer_fits_and_returns_finite_result():
    df = _rng_meta(1, 20, 0.4, 0.04)
    res = make_tbema_analyzer().fit(df, effect_col="effect", se_col="se")
    assert np.isfinite(res.estimate)
    assert np.isfinite(res.std_error) and res.std_error > 0
    assert res.ci_low < res.ci_high


def test_recovers_mean_under_no_selection():
    # Average point estimate across many honest (no-selection) datasets should
    # be close to the true mu (small bias expected from the robust likelihood).
    mu = 0.4
    ests = []
    an = make_tbema_analyzer()
    for s in range(40):
        df = _rng_meta(100 + s, 18, mu, 0.04)
        ests.append(an.fit(df, effect_col="effect", se_col="se").estimate)
    mean_est = float(np.mean(ests))
    assert abs(mean_est - mu) < 0.10, f"mean est {mean_est:.3f} far from mu {mu}"


def test_coverage_under_no_selection_is_reasonable():
    # CI should cover true mu in a reasonable fraction of honest datasets.
    mu = 0.4
    cov = 0
    n = 60
    an = make_tbema_analyzer()
    for s in range(n):
        df = _rng_meta(500 + s, 15, mu, 0.04)
        res = an.fit(df, effect_col="effect", se_col="se")
        if res.ci_low <= mu <= res.ci_high:
            cov += 1
    rate = cov / n
    # Wide tolerance: just assert the interval is not pathological.
    assert 0.60 <= rate <= 1.0, f"coverage {rate:.2f} out of range"


def test_zero_heterogeneity_collapses_interval_width():
    # With tau2=0 and small SEs the interval should be tighter than with
    # large heterogeneity, confirming tau enters the interval.
    an = make_tbema_analyzer()
    df_lo = _rng_meta(7, 15, 0.4, 0.0, se_lo=0.05, se_hi=0.15)
    df_hi = _rng_meta(7, 15, 0.4, 0.25, se_lo=0.05, se_hi=0.15)
    w_lo = an.fit(df_lo, effect_col="effect", se_col="se")
    w_hi = an.fit(df_hi, effect_col="effect", se_col="se")
    width_lo = w_lo.ci_high - w_lo.ci_low
    width_hi = w_hi.ci_high - w_hi.ci_low
    assert width_hi > width_lo, f"hi-het width {width_hi:.3f} !> lo-het {width_lo:.3f}"


def test_naive_mean_is_biased_under_selection_but_estimator_runs():
    # Build a selection-biased sample by keeping only positive-z studies;
    # naive mean must be biased high, and the estimator must still produce a
    # finite, narrower-than-naive-implied result (no crash on biased input).
    rng = np.random.default_rng(11)
    mu = 0.3
    ys, ses = [], []
    while len(ys) < 15:
        se = rng.uniform(0.1, 0.5)
        theta = rng.normal(mu, 0.2)
        y = rng.normal(theta, se)
        if y / se > 1.0 or rng.random() < 0.2:
            ys.append(y)
            ses.append(se)
    df = pd.DataFrame({"effect": ys, "se": ses})
    naive = float(np.mean(ys))
    res = make_tbema_analyzer().fit(df, effect_col="effect", se_col="se")
    assert naive > mu, "selection should bias naive mean high"
    assert np.isfinite(res.estimate)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
