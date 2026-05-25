# sentinel:skip-file — hardcoded paths / templated placeholders are fixture/registry/audit-narrative data for this repo's research workflow, not portable application configuration. Same pattern as push_all_repos.py and E156 workbook files.
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _method_palette(methods: Iterable[str]) -> dict[str, tuple[float, float, float, float]]:
    methods_list = list(methods)
    cmap = plt.get_cmap("tab10")
    return {method: cmap(i % 10) for i, method in enumerate(methods_list)}


def _valid_completed_rows(run_df: pd.DataFrame) -> pd.DataFrame:
    required = ["estimate", "std_error", "ci_low", "ci_high"]
    ok = run_df.loc[run_df["status"] == "ok"].copy()
    if ok.empty:
        return ok
    valid_mask = np.isfinite(ok[required].to_numpy(dtype=float)).all(axis=1)
    return ok.loc[valid_mask].copy()


def overall_method_metrics(run_df: pd.DataFrame) -> pd.DataFrame:
    valid = _valid_completed_rows(run_df)
    if valid.empty:
        counts = (
            run_df.groupby("method", sort=False)
            .agg(
                attempted_runs=("method", "size"),
                ok_status_runs=("status", lambda s: int((s == "ok").sum())),
                skipped_runs=("status", lambda s: int((s == "skipped").sum())),
                error_runs=("status", lambda s: int((s == "error").sum())),
                mean_elapsed_sec_attempted=("elapsed_sec", "mean"),
            )
            .reset_index()
        )
        counts["successful_runs"] = 0
        counts["invalid_ok_runs"] = counts["ok_status_runs"]
        counts["success_rate"] = 0.0
        counts["scenario_count"] = 0
        counts["mean_elapsed_sec"] = np.nan
        counts["bias"] = np.nan
        counts["mean_absolute_error"] = np.nan
        counts["rmse"] = np.nan
        counts["coverage_95"] = np.nan
        counts["mean_ci_width"] = np.nan
        counts["mean_tau"] = np.nan
        return counts.sort_values(["mean_elapsed_sec_attempted", "method"], ignore_index=True)

    valid["error"] = valid["estimate"] - valid["true_target_effect"]
    valid["abs_error"] = valid["error"].abs()
    valid["covered"] = (valid["ci_low"] <= valid["true_target_effect"]) & (valid["true_target_effect"] <= valid["ci_high"])
    valid["ci_width"] = valid["ci_high"] - valid["ci_low"]

    counts = (
        run_df.groupby("method", sort=False)
        .agg(
            attempted_runs=("method", "size"),
            ok_status_runs=("status", lambda s: int((s == "ok").sum())),
            skipped_runs=("status", lambda s: int((s == "skipped").sum())),
            error_runs=("status", lambda s: int((s == "error").sum())),
            mean_elapsed_sec_attempted=("elapsed_sec", "mean"),
        )
        .reset_index()
    )
    metrics = (
        valid.groupby("method", sort=False)
        .agg(
            successful_runs=("method", "size"),
            scenario_count=("scenario", "nunique"),
            bias=("error", "mean"),
            mean_absolute_error=("abs_error", "mean"),
            rmse=("error", lambda s: float(np.sqrt(np.mean(s**2)))),
            coverage_95=("covered", "mean"),
            mean_ci_width=("ci_width", "mean"),
            mean_tau=("tau", lambda s: float(s.dropna().mean()) if s.notna().any() else np.nan),
            mean_elapsed_sec=("elapsed_sec", "mean"),
        )
        .reset_index()
    )
    overall = counts.merge(metrics, on="method", how="left")
    overall["successful_runs"] = overall["successful_runs"].fillna(0).astype(int)
    overall["scenario_count"] = overall["scenario_count"].fillna(0).astype(int)
    overall["invalid_ok_runs"] = overall["ok_status_runs"] - overall["successful_runs"]
    overall["success_rate"] = overall["successful_runs"] / overall["attempted_runs"].clip(lower=1)
    return overall.sort_values(
        ["success_rate", "rmse", "mean_elapsed_sec", "method"],
        ascending=[False, True, True, True],
        na_position="last",
        ignore_index=True,
    )


def _reportable_overall_rows(overall_df: pd.DataFrame) -> pd.DataFrame:
    return overall_df.loc[overall_df["successful_runs"] > 0].copy()


def _headline_overall_rows(overall_df: pd.DataFrame) -> pd.DataFrame:
    reportable = _reportable_overall_rows(overall_df)
    if reportable.empty:
        return reportable
    complete = reportable.loc[np.isclose(reportable["success_rate"], 1.0)].copy()
    return complete if not complete.empty else reportable


def _best_row(df: pd.DataFrame, by: list[str], ascending: list[bool] | None = None) -> pd.Series | None:
    if df.empty:
        return None
    if ascending is None:
        ascending = [True] * len(by)
    ranked = df.dropna(subset=[col for col in by if col in df.columns])
    if ranked.empty:
        return None
    return ranked.sort_values(by, ascending=ascending).iloc[0]


def _grouped_bar_plot(
    summary_df: pd.DataFrame,
    metric: str,
    title: str,
    ylabel: str,
    output_path: Path,
    *,
    ylim: tuple[float, float] | None = None,
) -> None:
    plot_df = summary_df.loc[summary_df["successful_runs"] > 0, ["scenario", "method", metric]].copy()
    plot_df = plot_df.dropna(subset=[metric])
    if plot_df.empty:
        return
    scenarios = list(plot_df["scenario"].drop_duplicates())
    methods = list(plot_df["method"].drop_duplicates())
    palette = _method_palette(methods)

    x = np.arange(len(scenarios), dtype=float)
    width = 0.8 / max(len(methods), 1)

    fig, ax = plt.subplots(figsize=(12, 6))
    for idx, method in enumerate(methods):
        method_df = plot_df.loc[plot_df["method"] == method].set_index("scenario").reindex(scenarios)
        heights = method_df[metric].to_numpy(dtype=float)
        ax.bar(
            x + (idx - (len(methods) - 1) / 2) * width,
            heights,
            width=width,
            label=method,
            color=palette[method],
            alpha=0.9,
        )

    ax.set_xticks(x)
    ax.set_xticklabels([scenario.replace("_", "\n") for scenario in scenarios])
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.legend(frameon=False, ncols=min(len(methods), 3))
    ax.grid(axis="y", alpha=0.25, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _speed_accuracy_plot(overall_df: pd.DataFrame, output_path: Path) -> None:
    plot_df = overall_df.dropna(subset=["rmse", "mean_elapsed_sec"]).copy()
    if plot_df.empty:
        return

    methods = plot_df["method"].tolist()
    palette = _method_palette(methods)
    fig, ax = plt.subplots(figsize=(9, 6))
    for _, row in plot_df.iterrows():
        ax.scatter(
            row["mean_elapsed_sec"],
            row["rmse"],
            s=220,
            color=palette[row["method"]],
            alpha=0.9,
            edgecolor="black",
            linewidth=0.5,
        )
        ax.annotate(
            row["method"],
            (row["mean_elapsed_sec"], row["rmse"]),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=9,
        )

    ax.set_xscale("log")
    ax.set_xlabel("Mean Runtime Per Fit (seconds, log scale)")
    ax.set_ylabel("Overall RMSE")
    ax.set_title("Speed-Accuracy Frontier")
    ax.grid(alpha=0.3, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _stringify(value: object) -> str:
    if isinstance(value, float):
        if np.isnan(value):
            return "NA"
        return f"{value:.3f}"
    return str(value)


def _markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    data = df.loc[:, columns].copy()
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in data.iterrows():
        rows.append("| " + " | ".join(_stringify(row[col]) for col in columns) + " |")
    return "\n".join([header, divider, *rows])


def _scenario_highlights(summary_df: pd.DataFrame) -> list[str]:
    highlights: list[str] = []
    for scenario, group in summary_df.groupby("scenario", sort=False):
        valid_group = group.loc[group["successful_runs"] > 0].copy()
        incomplete = group.loc[group["success_rate"] < 1.0, "method"].tolist()
        if valid_group.empty:
            line = f"- `{scenario}`: no methods produced a fully valid completed fit."
            if incomplete:
                line += f" Incomplete runs: {', '.join(f'`{name}`' for name in incomplete)}."
            highlights.append(line)
            continue
        headline_group = _headline_overall_rows(valid_group)
        best_rmse = _best_row(headline_group, ["rmse", "mean_elapsed_sec"])
        fastest = _best_row(valid_group, ["mean_elapsed_sec", "rmse"])
        widest = _best_row(valid_group, ["mean_ci_width"], ascending=[False])
        if best_rmse is None or fastest is None or widest is None:
            continue
        line = (
            f"- `{scenario}`: best RMSE was `{best_rmse['method']}` ({best_rmse['rmse']:.3f}); "
            f"fastest was `{fastest['method']}` ({fastest['mean_elapsed_sec']:.3f}s); "
            f"widest intervals came from `{widest['method']}` ({widest['mean_ci_width']:.3f})."
        )
        if incomplete:
            line += f" Incomplete runs: {', '.join(f'`{name}`' for name in incomplete)}."
        highlights.append(line)
    return highlights


def write_benchmark_report(
    benchmark_dir: str | Path,
    run_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    metadata: dict[str, object],
    *,
    title: str = "MetaFrontierLab Benchmark Report",
) -> dict[str, str]:
    benchmark_path = Path(benchmark_dir)
    report_dir = benchmark_path / "report"
    figures_dir = report_dir / "figures"
    report_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    overall_df = overall_method_metrics(run_df)
    reportable_overall = _reportable_overall_rows(overall_df)

    bias_plot = figures_dir / "bias_by_scenario.png"
    rmse_plot = figures_dir / "rmse_by_scenario.png"
    coverage_plot = figures_dir / "coverage_by_scenario.png"
    speed_plot = figures_dir / "speed_accuracy_frontier.png"

    _grouped_bar_plot(summary_df, "bias", "Mean Bias By Scenario", "Bias", bias_plot)
    _grouped_bar_plot(summary_df, "rmse", "RMSE By Scenario", "RMSE", rmse_plot)
    _grouped_bar_plot(summary_df, "coverage_95", "95% Interval Coverage By Scenario", "Coverage", coverage_plot, ylim=(0.0, 1.05))
    _speed_accuracy_plot(overall_df, speed_plot)

    headline_overall = _headline_overall_rows(overall_df)
    top_overall = _best_row(headline_overall, ["rmse", "mean_elapsed_sec"])
    fastest = _best_row(headline_overall.dropna(subset=["mean_elapsed_sec"]), ["mean_elapsed_sec", "rmse"])
    most_reliable = _best_row(headline_overall, ["coverage_95", "rmse"], ascending=[False, True])
    incomplete_methods = overall_df.loc[overall_df["success_rate"] < 1.0, "method"].tolist()
    figure_specs = [
        ("RMSE", "RMSE by scenario", bias_plot.parent / "rmse_by_scenario.png"),
        ("Bias", "Bias by scenario", bias_plot),
        ("Coverage", "Coverage by scenario", coverage_plot),
        ("Speed-Accuracy Frontier", "Speed accuracy frontier", speed_plot),
    ]
    available_figures = [(title_text, alt_text, path) for title_text, alt_text, path in figure_specs if path.exists()]

    scenario_df = summary_df.loc[
        :,
        [
            "scenario",
            "method",
            "replications_total",
            "successful_runs",
            "invalid_ok_runs",
            "skipped_runs",
            "error_runs",
            "success_rate",
            "bias",
            "rmse",
            "coverage_95",
            "mean_ci_width",
            "mean_elapsed_sec",
            "mean_elapsed_sec_attempted",
        ],
    ].copy()
    overall_table = overall_df.loc[
        :,
        [
            "method",
            "attempted_runs",
            "successful_runs",
            "invalid_ok_runs",
            "skipped_runs",
            "error_runs",
            "success_rate",
            "bias",
            "mean_absolute_error",
            "rmse",
            "coverage_95",
            "mean_ci_width",
            "mean_elapsed_sec",
            "mean_elapsed_sec_attempted",
        ],
    ].copy()

    created_at = metadata.get("created_at_utc") or datetime.now(timezone.utc).isoformat()
    methods = ", ".join(metadata.get("methods", []))
    replications = metadata.get("replications", "unknown")

    summary_lines = [
        f"# {title}",
        "",
        f"Generated: `{created_at}`",
        "",
        "## Scope",
        "",
        f"- Replications per scenario: `{replications}`",
        f"- Methods: `{methods}`",
        f"- Scenarios: `{len(metadata.get('scenarios', []))}`",
        "",
        "## Executive Summary",
        "",
    ]

    if top_overall is not None:
        summary_lines.append(
            f"- Best overall RMSE in this run: `{top_overall['method']}` with RMSE `{top_overall['rmse']:.3f}`."
        )
    if fastest is not None:
        summary_lines.append(
            f"- Fastest method in this run: `{fastest['method']}` at `{fastest['mean_elapsed_sec']:.3f}` seconds per fit on average."
        )
    if most_reliable is not None:
        summary_lines.append(
            f"- Highest observed 95% coverage in this run: `{most_reliable['method']}` at `{most_reliable['coverage_95']:.3f}`."
        )
    if incomplete_methods:
        summary_lines.append(
            f"- Methods with incomplete runs: {', '.join(f'`{method}`' for method in incomplete_methods)}."
        )
    if top_overall is None:
        summary_lines.append("- No methods produced a fully valid completed fit in this run.")
    summary_lines.append(
        "- Interpret these results as engineering benchmarks, not publication-grade evidence, unless you scale the replication count much higher."
    )
    summary_lines.append(
        "- `mean_elapsed_sec` summarizes valid completed fits only; `mean_elapsed_sec_attempted` includes failures and adapter startup overhead."
    )
    summary_lines.append("")
    summary_lines.append("## Overall Method Ranking")
    summary_lines.append("")
    summary_lines.append(_markdown_table(overall_table, overall_table.columns.tolist()))
    summary_lines.append("")
    summary_lines.append("## Scenario Highlights")
    summary_lines.append("")
    summary_lines.extend(_scenario_highlights(summary_df))
    summary_lines.append("")
    summary_lines.append("## Scenario Table")
    summary_lines.append("")
    summary_lines.append(_markdown_table(scenario_df, scenario_df.columns.tolist()))
    summary_lines.append("")
    summary_lines.append("## Figures")
    summary_lines.append("")
    if available_figures:
        for title_text, alt_text, path in available_figures:
            summary_lines.append(f"### {title_text}")
            summary_lines.append("")
            summary_lines.append(f"![{alt_text}](figures/{path.name})")
            summary_lines.append("")
    else:
        summary_lines.append("No figures were generated because no methods produced valid completed fits for plotting.")
        summary_lines.append("")
    summary_lines.append("## Reproducibility")
    summary_lines.append("")
    summary_lines.append(f"- Source run table: `{benchmark_path / 'benchmark_runs.csv'}`")
    summary_lines.append(f"- Source summary table: `{benchmark_path / 'benchmark_summary.csv'}`")
    summary_lines.append(f"- Source metadata: `{benchmark_path / 'benchmark_metadata.json'}`")
    summary_lines.append("")

    markdown_path = report_dir / "benchmark_report.md"
    markdown_path.write_text("\n".join(summary_lines), encoding="utf-8")

    highlight_items = _scenario_highlights(summary_df)
    executive_items: list[str] = []
    if top_overall is not None:
        executive_items.append(f"Best overall RMSE in this run: <code>{top_overall['method']}</code> with RMSE <code>{top_overall['rmse']:.3f}</code>.")
    if fastest is not None:
        executive_items.append(f"Fastest method in this run: <code>{fastest['method']}</code> at <code>{fastest['mean_elapsed_sec']:.3f}</code> seconds per fit on average.")
    if most_reliable is not None:
        executive_items.append(f"Highest observed 95% coverage in this run: <code>{most_reliable['method']}</code> at <code>{most_reliable['coverage_95']:.3f}</code>.")
    if incomplete_methods:
        executive_items.append(f"Methods with incomplete runs: {', '.join(f'<code>{method}</code>' for method in incomplete_methods)}.")
    if top_overall is None:
        executive_items.append("No methods produced a fully valid completed fit in this run.")
    executive_items.append("Interpret these results as engineering benchmarks, not publication-grade evidence, unless you scale the replication count much higher.")
    executive_items.append("<code>mean_elapsed_sec</code> summarizes valid completed fits only; <code>mean_elapsed_sec_attempted</code> includes failures and adapter startup overhead.")

    html_parts = [
        "<html><head><meta charset='utf-8'><title>MetaFrontierLab Benchmark Report</title>",
        "<style>",
        "body{font-family:Georgia,serif;max-width:1100px;margin:40px auto;padding:0 24px;line-height:1.5;color:#1c1c1c;}",
        "h1,h2,h3{font-family:'Trebuchet MS',sans-serif;}",
        "table{border-collapse:collapse;width:100%;margin:16px 0;}",
        "th,td{border:1px solid #d7d7d7;padding:8px 10px;text-align:left;font-size:14px;}",
        "th{background:#f2efe7;}",
        "img{max-width:100%;margin:12px 0 28px 0;border:1px solid #ddd;}",
        "code{background:#f7f4ef;padding:1px 4px;border-radius:4px;}",
        ".muted{color:#555;}",
        "</style></head><body>",
        f"<h1>{title}</h1>",
        f"<p class='muted'>Generated: <code>{created_at}</code></p>",
        "<h2>Scope</h2>",
        f"<p>Replications per scenario: <code>{replications}</code><br>Methods: <code>{methods}</code><br>Scenarios: <code>{len(metadata.get('scenarios', []))}</code></p>",
        "<h2>Executive Summary</h2>",
        "<ul>",
        *[f"<li>{item}</li>" for item in executive_items],
        "</ul>",
        "<h2>Overall Method Ranking</h2>",
        overall_table.to_html(index=False, float_format=lambda x: f"{x:.3f}"),
        "<h2>Scenario Highlights</h2>",
        "<ul>",
        *[f"<li>{item[2:] if item.startswith('- ') else item}</li>" for item in highlight_items],
        "</ul>",
        "<h2>Scenario Table</h2>",
        scenario_df.to_html(index=False, float_format=lambda x: f"{x:.3f}"),
        "<h2>Figures</h2>",
        *(["<p>No figures were generated because no methods produced valid completed fits for plotting.</p>"] if not available_figures else []),
        *[
            f"<h3>{title_text}</h3><img src='figures/{path.name}' alt='{alt_text}'>"
            for title_text, alt_text, path in available_figures
        ],
        "<h2>Reproducibility</h2>",
        f"<p>Source run table: <code>{benchmark_path / 'benchmark_runs.csv'}</code><br>"
        f"Source summary table: <code>{benchmark_path / 'benchmark_summary.csv'}</code><br>"
        f"Source metadata: <code>{benchmark_path / 'benchmark_metadata.json'}</code></p>",
        "</body></html>",
    ]
    html_path = report_dir / "benchmark_report.html"
    html_path.write_text("\n".join(html_parts), encoding="utf-8")

    report_metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_method_metrics": json.loads(overall_df.to_json(orient="records")),
        "figure_paths": {
            key: str(path)
            for key, path in {
                "bias": bias_plot,
                "rmse": rmse_plot,
                "coverage": coverage_plot,
                "speed_accuracy": speed_plot,
            }.items()
            if path.exists()
        },
    }
    metadata_path = report_dir / "report_metadata.json"
    metadata_path.write_text(json.dumps(report_metadata, indent=2), encoding="utf-8")

    return {
        "markdown_report": str(markdown_path),
        "html_report": str(html_path),
        "report_metadata": str(metadata_path),
        "figures_dir": str(figures_dir),
    }
