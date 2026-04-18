from __future__ import annotations

import json
from pathlib import Path

from metafrontier import (
    SimulationConfig,
    make_tbema_analyzer,
    moderator_columns,
    naive_random_effects_log_or,
    profile_columns,
    simulate_publication_biased_binary_meta,
    target_moderators_for_config,
)


def main() -> None:
    root = Path(__file__).resolve().parent
    results_dir = root / "results"
    results_dir.mkdir(exist_ok=True)

    config = SimulationConfig(studies=20, moderator_count=2)
    observed, truth = simulate_publication_biased_binary_meta(config)
    analyzer = make_tbema_analyzer()
    result = analyzer.fit(
        observed,
        moderator_cols=moderator_columns(config.moderator_count),
        profile_cols=profile_columns(),
        target_profile=list(config.target_profile),
        target_moderators=target_moderators_for_config(config).tolist(),
        design_strength_col="design_strength",
    )
    naive = naive_random_effects_log_or(observed)

    observed.to_csv(results_dir / "observed_studies.csv", index=False)
    result.submodel_table.to_csv(results_dir / "submodel_table.csv", index=False)

    summary = {
        **truth,
        "frontier_estimate": result.estimate,
        "frontier_std_error": result.std_error,
        "frontier_ci_low": result.ci_low,
        "frontier_ci_high": result.ci_high,
        "frontier_tau": result.tau,
        "frontier_submodel_weights": result.submodel_weights,
        "naive_estimate": naive["estimate"],
        "naive_std_error": naive["std_error"],
        "naive_ci_low": naive["ci_low"],
        "naive_ci_high": naive["ci_high"],
        "naive_tau": naive["tau"],
        "frontier_error": result.estimate - truth["true_target_effect"],
        "naive_error": naive["estimate"] - truth["true_target_effect"],
    }
    (results_dir / "demo_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("MetaFrontierLab demo")
    print(f"Observed studies: {truth['observed_study_count']} / {truth['full_study_count']}")
    print(f"True target effect: {truth['true_target_effect']:.3f}")
    print(
        "Frontier estimate: "
        f"{result.estimate:.3f} "
        f"[{result.ci_low:.3f}, {result.ci_high:.3f}]"
    )
    print(
        "Naive RE estimate: "
        f"{naive['estimate']:.3f} "
        f"[{naive['ci_low']:.3f}, {naive['ci_high']:.3f}]"
    )
    print("Submodel weights:")
    for name, weight in sorted(result.submodel_weights.items(), key=lambda item: item[1], reverse=True):
        print(f"  {name}: {weight:.3f}")


if __name__ == "__main__":
    main()
