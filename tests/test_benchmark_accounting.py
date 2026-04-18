from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from metafrontier.benchmark_methods import MethodUnavailableError, _wrap_method
from metafrontier.benchmarking import _summarize_benchmarks, default_benchmark_scenarios
from metafrontier.reporting import overall_method_metrics
from metafrontier.simulation import SimulationConfig


def _toy_runs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario": "toy",
                "method": "demo",
                "status": "ok",
                "estimate": 0.1,
                "std_error": 0.2,
                "ci_low": -0.2,
                "ci_high": 0.4,
                "tau": 0.05,
                "elapsed_sec": 1.0,
                "true_target_effect": 0.0,
                "observed_study_count": 10,
            },
            {
                "scenario": "toy",
                "method": "demo",
                "status": "ok",
                "estimate": 0.2,
                "std_error": np.nan,
                "ci_low": -0.1,
                "ci_high": 0.5,
                "tau": 0.07,
                "elapsed_sec": 3.0,
                "true_target_effect": 0.0,
                "observed_study_count": 12,
            },
        ]
    )


def test_summary_counts_only_valid_ok_runs_as_success() -> None:
    summary = _summarize_benchmarks(_toy_runs())
    row = summary.iloc[0]

    assert row["ok_status_runs"] == 2
    assert row["successful_runs"] == 1
    assert row["invalid_ok_runs"] == 1
    assert row["success_rate"] == pytest.approx(0.5)
    assert row["mean_elapsed_sec"] == pytest.approx(1.0)
    assert row["mean_elapsed_sec_attempted"] == pytest.approx(2.0)


def test_overall_metrics_use_same_success_definition() -> None:
    overall = overall_method_metrics(_toy_runs())
    row = overall.iloc[0]

    assert row["attempted_runs"] == 2
    assert row["ok_status_runs"] == 2
    assert row["successful_runs"] == 1
    assert row["invalid_ok_runs"] == 1
    assert row["success_rate"] == pytest.approx(0.5)
    assert row["mean_elapsed_sec"] == pytest.approx(1.0)
    assert row["mean_elapsed_sec_attempted"] == pytest.approx(2.0)


def test_wrap_method_reports_contract_errors_as_errors() -> None:
    data = pd.DataFrame({"x": [1]})
    config = SimulationConfig()

    unavailable = _wrap_method("demo", lambda _data, _config: (_ for _ in ()).throw(MethodUnavailableError("missing")), data, config)
    invalid = _wrap_method("demo", lambda _data, _config: (_ for _ in ()).throw(ValueError("bad payload")), data, config)

    assert unavailable.status == "skipped"
    assert invalid.status == "error"


def test_default_benchmark_scenarios_use_distinct_base_seeds() -> None:
    seeds = [scenario.config.seed for scenario in default_benchmark_scenarios()]

    assert len(seeds) == len(set(seeds))
