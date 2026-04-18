from __future__ import annotations

import argparse
from pathlib import Path

from metafrontier import available_benchmark_methods, default_benchmark_scenarios, run_benchmark_suite, write_benchmark_outputs, write_benchmark_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MetaFrontierLab benchmark scenarios.")
    parser.add_argument("--replications", type=int, default=4, help="Number of replications per scenario.")
    parser.add_argument(
        "--methods",
        nargs="*",
        default=None,
        help="Benchmark methods to run. Defaults to the locally available methods.",
    )
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=None,
        help="Scenario names to run. Defaults to all built-in scenarios.",
    )
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Include external adapters such as RoBMA when they are available in the environment.",
    )
    parser.add_argument(
        "--output-dir",
        default="results/benchmarks",
        help="Directory where benchmark outputs will be written.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate figures and a benchmark report after the run completes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenarios = default_benchmark_scenarios()
    if args.scenarios:
        scenario_map = {scenario.name: scenario for scenario in scenarios}
        missing = [name for name in args.scenarios if name not in scenario_map]
        if missing:
            raise SystemExit(f"Unknown scenarios: {missing}")
        scenarios = [scenario_map[name] for name in args.scenarios]

    methods = args.methods or available_benchmark_methods(include_external=args.include_external)
    run_df, summary_df, metadata = run_benchmark_suite(scenarios=scenarios, methods=methods, replications=args.replications)
    output_paths = write_benchmark_outputs(Path(args.output_dir), run_df, summary_df, metadata)

    print("MetaFrontierLab benchmark suite")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Replications per scenario: {args.replications}")
    print(f"Methods: {', '.join(methods)}")
    print(f"Run rows: {len(run_df)}")
    print("")
    print(summary_df.to_string(index=False))
    print("")
    print("Outputs:")
    for label, path in output_paths.items():
        print(f"  {label}: {path}")
    if args.report:
        report_paths = write_benchmark_report(Path(args.output_dir), run_df, summary_df, metadata)
        print("")
        print("Report:")
        for label, path in report_paths.items():
            print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
