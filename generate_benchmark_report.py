from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from metafrontier.reporting import write_benchmark_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate plots and a report from benchmark outputs.")
    parser.add_argument(
        "--benchmark-dir",
        default="results/benchmarks",
        help="Directory containing benchmark_runs.csv, benchmark_summary.csv, and benchmark_metadata.json.",
    )
    parser.add_argument(
        "--title",
        default="MetaFrontierLab Benchmark Report",
        help="Report title.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir)
    run_df = pd.read_csv(benchmark_dir / "benchmark_runs.csv")
    summary_df = pd.read_csv(benchmark_dir / "benchmark_summary.csv")
    metadata = json.loads((benchmark_dir / "benchmark_metadata.json").read_text(encoding="utf-8"))
    output = write_benchmark_report(benchmark_dir, run_df, summary_df, metadata, title=args.title)
    print("Benchmark report generated")
    for label, path in output.items():
        print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
