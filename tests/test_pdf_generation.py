from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from generate_benchmark_pdf import build_pdf
from metafrontier.benchmarking import _summarize_benchmarks


def test_pdf_generation_handles_no_valid_completed_fits(tmp_path: Path) -> None:
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

    runs.to_csv(benchmark_dir / "benchmark_runs.csv", index=False)
    summary.to_csv(benchmark_dir / "benchmark_summary.csv", index=False)
    (benchmark_dir / "benchmark_metadata.json").write_text(
        json.dumps({"replications": 1, "methods": ["demo"], "scenarios": [{"name": "toy"}]}),
        encoding="utf-8",
    )

    output_pdf = tmp_path / "report.pdf"
    build_pdf(benchmark_dir, output_pdf)

    assert output_pdf.exists()
    assert output_pdf.stat().st_size > 0
