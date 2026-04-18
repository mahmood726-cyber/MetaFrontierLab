from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark_methods import METHOD_REGISTRY, available_benchmark_methods
from .simulation import SimulationConfig, simulate_publication_biased_binary_meta


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    description: str
    config: SimulationConfig


def default_benchmark_scenarios() -> list[BenchmarkScenario]:
    return [
        BenchmarkScenario(
            name="moderate_bias",
            description="Moderate publication bias with modest heterogeneity and mostly randomized evidence.",
            config=SimulationConfig(
                seed=20260401,
                studies=24,
                moderator_count=2,
                heterogeneity=0.18,
                publication_strength=0.75,
                rare_event_logit=-3.1,
                observational_fraction=0.25,
                observational_design_strength=0.65,
            ),
        ),
        BenchmarkScenario(
            name="sparse_high_bias",
            description="Rare events and stronger publication bias, stressing sparse-data corrections.",
            config=SimulationConfig(
                seed=20261401,
                studies=24,
                moderator_count=2,
                heterogeneity=0.26,
                publication_strength=1.55,
                rare_event_logit=-4.1,
                observational_fraction=0.35,
                observational_design_strength=0.55,
            ),
        ),
        BenchmarkScenario(
            name="transport_shift",
            description="Study populations are shifted away from the target population, rewarding transport-aware pooling.",
            config=SimulationConfig(
                seed=20262401,
                studies=24,
                moderator_count=2,
                heterogeneity=0.24,
                publication_strength=1.0,
                rare_event_logit=-3.5,
                observational_fraction=0.35,
                study_profile_shift=(1.1, -0.9),
                target_profile=(0.0, 0.0),
            ),
        ),
        BenchmarkScenario(
            name="mixed_credibility",
            description="Heavy observational contamination and higher heterogeneity, stressing design-strength discounting.",
            config=SimulationConfig(
                seed=20263401,
                studies=26,
                moderator_count=2,
                heterogeneity=0.34,
                publication_strength=0.9,
                rare_event_logit=-3.3,
                observational_fraction=0.55,
                observational_design_strength=0.42,
                observational_bias_intercept=0.24,
                observational_bias_slope=0.16,
            ),
        ),
    ]


def run_benchmark_suite(
    scenarios: list[BenchmarkScenario] | None = None,
    methods: list[str] | None = None,
    replications: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    selected_scenarios = scenarios or default_benchmark_scenarios()
    selected_methods = methods or available_benchmark_methods(include_external=False)

    unknown = [name for name in selected_methods if name not in METHOD_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown benchmark methods: {unknown}")

    rows: list[dict[str, object]] = []
    for scenario in selected_scenarios:
        for replication in range(replications):
            config = replace(scenario.config, seed=scenario.config.seed + replication)
            observed, truth = simulate_publication_biased_binary_meta(config)
            for method_name in selected_methods:
                result = METHOD_REGISTRY[method_name](observed.copy(), config)
                rows.append(
                    {
                        "scenario": scenario.name,
                        "description": scenario.description,
                        "replication": replication,
                        "simulation_seed": config.seed,
                        "method": result.method,
                        "status": result.status,
                        "estimate": result.estimate,
                        "std_error": result.std_error,
                        "ci_low": result.ci_low,
                        "ci_high": result.ci_high,
                        "tau": result.tau,
                        "elapsed_sec": result.elapsed_sec,
                        "note": result.note,
                        "true_target_effect": truth["true_target_effect"],
                        "observed_study_count": truth["observed_study_count"],
                        "full_study_count": truth["full_study_count"],
                        "target_profile_1": truth["target_profile_1"],
                        "target_profile_2": truth["target_profile_2"],
                        "study_profile_shift_1": truth["study_profile_shift_1"],
                        "study_profile_shift_2": truth["study_profile_shift_2"],
                        "heterogeneity_setting": config.heterogeneity,
                        "publication_strength_setting": config.publication_strength,
                        "rare_event_logit_setting": config.rare_event_logit,
                        "observational_fraction_setting": config.observational_fraction,
                    }
                )

    run_df = pd.DataFrame(rows)
    summary_df = _summarize_benchmarks(run_df)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "replications": replications,
        "methods": selected_methods,
        "scenarios": [asdict(scenario) for scenario in selected_scenarios],
    }
    return run_df, summary_df, metadata


def _summarize_benchmarks(run_df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for (scenario, method), group in run_df.groupby(["scenario", "method"], sort=False):
        ok_status = group[group["status"] == "ok"].copy()
        valid_mask = np.isfinite(ok_status[["estimate", "std_error", "ci_low", "ci_high"]].to_numpy(dtype=float)).all(axis=1)
        ok = ok_status.loc[valid_mask].copy()
        ok["error"] = ok["estimate"] - ok["true_target_effect"]
        ok["covered"] = (ok["ci_low"] <= ok["true_target_effect"]) & (ok["true_target_effect"] <= ok["ci_high"])
        ok["ci_width"] = ok["ci_high"] - ok["ci_low"]
        successful_runs = int(len(ok))
        ok_status_runs = int(len(ok_status))

        record = {
            "scenario": scenario,
            "method": method,
            "replications_total": int(len(group)),
            "ok_status_runs": ok_status_runs,
            "successful_runs": successful_runs,
            "invalid_ok_runs": ok_status_runs - successful_runs,
            "skipped_runs": int((group["status"] == "skipped").sum()),
            "error_runs": int((group["status"] == "error").sum()),
            "success_rate": float(successful_runs / max(len(group), 1)),
            "mean_observed_studies": float(group["observed_study_count"].mean()),
            "mean_elapsed_sec_attempted": float(group["elapsed_sec"].mean()),
        }

        if not ok.empty:
            record.update(
                {
                    "mean_estimate": float(ok["estimate"].mean()),
                    "bias": float(ok["error"].mean()),
                    "mean_absolute_error": float(ok["error"].abs().mean()),
                    "rmse": float(np.sqrt(np.mean(ok["error"] ** 2))),
                    "coverage_95": float(ok["covered"].mean()),
                    "mean_ci_width": float(ok["ci_width"].mean()),
                    "mean_tau": float(ok["tau"].dropna().mean()) if ok["tau"].notna().any() else np.nan,
                    "mean_elapsed_sec": float(ok["elapsed_sec"].mean()),
                }
            )
        else:
            record.update(
                {
                    "mean_estimate": np.nan,
                    "bias": np.nan,
                    "mean_absolute_error": np.nan,
                    "rmse": np.nan,
                    "coverage_95": np.nan,
                    "mean_ci_width": np.nan,
                    "mean_tau": np.nan,
                    "mean_elapsed_sec": np.nan,
                }
            )

        records.append(record)

    return pd.DataFrame(records).sort_values(["scenario", "method"], ignore_index=True)


def write_benchmark_outputs(
    output_dir: str | Path,
    run_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    metadata: dict[str, object],
) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_path = out_dir / "benchmark_runs.csv"
    summary_path = out_dir / "benchmark_summary.csv"
    metadata_path = out_dir / "benchmark_metadata.json"
    summary_json_path = out_dir / "benchmark_summary.json"

    run_df.to_csv(run_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    summary_json_path.write_text(summary_df.to_json(orient="records", indent=2), encoding="utf-8")

    return {
        "run_csv": str(run_path),
        "summary_csv": str(summary_path),
        "metadata_json": str(metadata_path),
        "summary_json": str(summary_json_path),
    }
