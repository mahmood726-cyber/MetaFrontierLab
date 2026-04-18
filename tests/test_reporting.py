from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from metafrontier.benchmarking import _summarize_benchmarks
from metafrontier.reporting import write_benchmark_report


def test_report_headline_prefers_complete_methods(tmp_path: Path) -> None:
    benchmark_dir = tmp_path / "bench"
    benchmark_dir.mkdir()

    runs = pd.DataFrame(
        [
            {
                "scenario": "toy",
                "description": "toy",
                "replication": 0,
                "method": "fragile",
                "status": "ok",
                "estimate": 0.01,
                "std_error": 0.1,
                "ci_low": -0.2,
                "ci_high": 0.2,
                "tau": 0.0,
                "elapsed_sec": 2.0,
                "note": "",
                "true_target_effect": 0.0,
                "observed_study_count": 10,
                "full_study_count": 10,
                "target_profile_1": 0.0,
                "target_profile_2": 0.0,
                "study_profile_shift_1": 0.0,
                "study_profile_shift_2": 0.0,
                "heterogeneity_setting": 0.0,
                "publication_strength_setting": 0.0,
                "rare_event_logit_setting": 0.0,
                "observational_fraction_setting": 0.0,
            },
            {
                "scenario": "toy",
                "description": "toy",
                "replication": 1,
                "method": "fragile",
                "status": "error",
                "estimate": None,
                "std_error": None,
                "ci_low": None,
                "ci_high": None,
                "tau": None,
                "elapsed_sec": 2.0,
                "note": "boom",
                "true_target_effect": 0.0,
                "observed_study_count": 10,
                "full_study_count": 10,
                "target_profile_1": 0.0,
                "target_profile_2": 0.0,
                "study_profile_shift_1": 0.0,
                "study_profile_shift_2": 0.0,
                "heterogeneity_setting": 0.0,
                "publication_strength_setting": 0.0,
                "rare_event_logit_setting": 0.0,
                "observational_fraction_setting": 0.0,
            },
            {
                "scenario": "toy",
                "description": "toy",
                "replication": 0,
                "method": "stable",
                "status": "ok",
                "estimate": 0.1,
                "std_error": 0.1,
                "ci_low": -0.1,
                "ci_high": 0.3,
                "tau": 0.0,
                "elapsed_sec": 1.0,
                "note": "",
                "true_target_effect": 0.0,
                "observed_study_count": 10,
                "full_study_count": 10,
                "target_profile_1": 0.0,
                "target_profile_2": 0.0,
                "study_profile_shift_1": 0.0,
                "study_profile_shift_2": 0.0,
                "heterogeneity_setting": 0.0,
                "publication_strength_setting": 0.0,
                "rare_event_logit_setting": 0.0,
                "observational_fraction_setting": 0.0,
            },
            {
                "scenario": "toy",
                "description": "toy",
                "replication": 1,
                "method": "stable",
                "status": "ok",
                "estimate": 0.1,
                "std_error": 0.1,
                "ci_low": -0.1,
                "ci_high": 0.3,
                "tau": 0.0,
                "elapsed_sec": 1.0,
                "note": "",
                "true_target_effect": 0.0,
                "observed_study_count": 10,
                "full_study_count": 10,
                "target_profile_1": 0.0,
                "target_profile_2": 0.0,
                "study_profile_shift_1": 0.0,
                "study_profile_shift_2": 0.0,
                "heterogeneity_setting": 0.0,
                "publication_strength_setting": 0.0,
                "rare_event_logit_setting": 0.0,
                "observational_fraction_setting": 0.0,
            },
        ]
    )
    summary = _summarize_benchmarks(runs)
    metadata = {"replications": 2, "methods": ["fragile", "stable"], "scenarios": [{"name": "toy"}]}

    paths = write_benchmark_report(benchmark_dir, runs, summary, metadata)
    markdown = Path(paths["markdown_report"]).read_text(encoding="utf-8")

    assert "Best overall RMSE in this run: `stable`" in markdown
    assert "Methods with incomplete runs: `fragile`." in markdown


def test_report_skips_missing_figures_and_html_keeps_summary_sections(tmp_path: Path) -> None:
    benchmark_dir = tmp_path / "bench"
    benchmark_dir.mkdir()

    runs = pd.DataFrame(
        [
            {
                "scenario": "toy",
                "description": "all skipped",
                "replication": 0,
                "method": "demo",
                "status": "skipped",
                "estimate": None,
                "std_error": None,
                "ci_low": None,
                "ci_high": None,
                "tau": None,
                "elapsed_sec": 0.1,
                "note": "missing dependency",
                "true_target_effect": 0.0,
                "observed_study_count": 0,
                "full_study_count": 0,
                "target_profile_1": 0.0,
                "target_profile_2": 0.0,
                "study_profile_shift_1": 0.0,
                "study_profile_shift_2": 0.0,
                "heterogeneity_setting": 0.0,
                "publication_strength_setting": 0.0,
                "rare_event_logit_setting": 0.0,
                "observational_fraction_setting": 0.0,
            }
        ]
    )
    summary = _summarize_benchmarks(runs)
    metadata = {"replications": 1, "methods": ["demo"], "scenarios": [{"name": "toy"}]}

    paths = write_benchmark_report(benchmark_dir, runs, summary, metadata)
    markdown = Path(paths["markdown_report"]).read_text(encoding="utf-8")
    html = Path(paths["html_report"]).read_text(encoding="utf-8")

    assert "No figures were generated because no methods produced valid completed fits for plotting." in markdown
    assert "figures/rmse_by_scenario.png" not in markdown
    assert "<h2>Executive Summary</h2>" in html
    assert "<h2>Reproducibility</h2>" in html
    assert "<img " not in html
