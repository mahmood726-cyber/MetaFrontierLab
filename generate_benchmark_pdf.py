# sentinel:skip-file — hardcoded paths / templated placeholders are fixture/registry/audit-narrative data for this repo's research workflow, not portable application configuration. Same pattern as push_all_repos.py and E156 workbook files.
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:
    colors = None
    ParagraphStyle = Any
    getSampleStyleSheet = None
    BaseDocTemplate = Frame = Image = PageBreak = PageTemplate = Paragraph = Spacer = Table = TableStyle = Any
    A4 = (595.2756, 841.8898)
    REPORTLAB_AVAILABLE = False

from metafrontier.reporting import overall_method_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a PDF benchmark report.")
    parser.add_argument(
        "--benchmark-dir",
        default="results/benchmarks_scaled_full",
        help="Directory containing benchmark outputs and the HTML/Markdown report.",
    )
    parser.add_argument(
        "--output-pdf",
        default="output/pdf/metafrontier_benchmark_report.pdf",
        help="Destination PDF path.",
    )
    return parser.parse_args()


def _styles() -> dict[str, ParagraphStyle]:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab styles requested when reportlab is unavailable.")
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "MetaTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=colors.HexColor("#17324d"),
            spaceAfter=18,
        ),
        "subtitle": ParagraphStyle(
            "MetaSubtitle",
            parent=styles["Heading2"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#4a5568"),
            spaceAfter=10,
        ),
        "heading": ParagraphStyle(
            "MetaHeading",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#17324d"),
            spaceBefore=6,
            spaceAfter=10,
        ),
        "body": ParagraphStyle(
            "MetaBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "MetaBullet",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=5,
        ),
        "caption": ParagraphStyle(
            "MetaCaption",
            parent=styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#555555"),
            spaceAfter=8,
        ),
    }


def _page_number(canvas, doc) -> None:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab page numbering requested when reportlab is unavailable.")
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(doc.pagesize[0] - 36, 18, f"Page {doc.page}")
    canvas.restoreState()


def _build_table(df: pd.DataFrame, max_rows: int | None = None) -> Any:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab tables requested when reportlab is unavailable.")
    if max_rows is not None:
        df = df.head(max_rows)
    data = [list(df.columns)] + df.astype(object).values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f0f7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324d")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c9d4e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbfe")]),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _format_df(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.loc[:, columns].copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    return out


def _headline_rows(overall: pd.DataFrame) -> pd.DataFrame:
    reportable = overall[overall["successful_runs"] > 0].copy()
    if reportable.empty:
        return reportable
    complete = reportable[reportable["success_rate"].round(12) >= 1.0].copy()
    return complete if not complete.empty else reportable


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_fallback_pdf(lines: list[str], output_pdf: Path) -> Path:
    lines_per_page = 44
    top_y = 792
    leading = 16
    pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [["MetaFrontierLab Benchmark Report"]]

    objects: list[bytes] = []

    def add_object(payload: str | bytes) -> int:
        data = payload.encode("latin-1") if isinstance(payload, str) else payload
        objects.append(data)
        return len(objects)

    catalog_id = add_object("<< /Type /Catalog /Pages 2 0 R >>")
    assert catalog_id == 1
    pages_id = add_object("<< /Type /Pages /Kids [] /Count 0 >>")
    assert pages_id == 2

    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    content_ids: list[int] = []

    for page_index, page_lines in enumerate(pages, start=1):
        content_lines = ["BT", "/F1 11 Tf", f"1 0 0 1 72 {top_y} Tm", f"{leading} TL"]
        for line in page_lines:
            content_lines.append(f"({_pdf_escape(line)}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", errors="replace")
        content_id = add_object(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
        content_ids.append(content_id)
        page_id = add_object(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {A4[0]:.0f} {A4[1]:.0f}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id, payload in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )

    output_pdf.write_bytes(pdf)
    return output_pdf


def _fallback_report_lines(
    benchmark_dir: Path,
    metadata: dict[str, Any],
    overall: pd.DataFrame,
    summary_df: pd.DataFrame,
) -> list[str]:
    lines = [
        "MetaFrontierLab Benchmark Report",
        f"Generated from: {benchmark_dir}",
        f"Replications per scenario: {metadata['replications']}",
        f"Methods benchmarked: {', '.join(metadata['methods'])}",
        "",
        "Executive Summary",
    ]
    headline_overall = _headline_rows(overall)
    if not headline_overall.empty:
        top = headline_overall.sort_values(["rmse", "mean_elapsed_sec"]).iloc[0]
        coverage_leader = headline_overall.sort_values(["coverage_95", "rmse"], ascending=[False, True]).iloc[0]
        lines.append(f"Best overall RMSE: {top['method']} ({top['rmse']:.3f})")
        lines.append(f"Highest observed coverage: {coverage_leader['method']} ({coverage_leader['coverage_95']:.3f})")
    else:
        lines.append("No methods produced a fully valid completed fit in this run.")
    fast_pool = headline_overall.dropna(subset=["mean_elapsed_sec"])
    if not fast_pool.empty:
        fastest = fast_pool.sort_values(["mean_elapsed_sec", "method"]).iloc[0]
        lines.append(f"Fastest method: {fastest['method']} ({fastest['mean_elapsed_sec']:.3f} seconds per fit)")
    incomplete = overall.loc[overall["success_rate"] < 1.0, "method"].tolist()
    if incomplete:
        lines.append(f"Methods with incomplete runs: {', '.join(incomplete)}")

    lines.extend(["", "Overall Method Ranking"])
    ranking = _format_df(
        overall,
        [
            "method",
            "attempted_runs",
            "successful_runs",
            "invalid_ok_runs",
            "skipped_runs",
            "error_runs",
            "success_rate",
            "rmse",
            "coverage_95",
            "mean_elapsed_sec",
        ],
    )
    lines.append(" | ".join(ranking.columns))
    for row in ranking.astype(str).itertuples(index=False, name=None):
        lines.append(" | ".join(row))

    lines.extend(["", "Scenario Highlights"])
    for scenario, group in summary_df.groupby("scenario", sort=False):
        valid = group[group["successful_runs"] > 0].copy()
        incomplete = group.loc[group["success_rate"] < 1.0, "method"].tolist()
        if valid.empty:
            suffix = f" Incomplete runs: {', '.join(incomplete)}." if incomplete else ""
            lines.append(f"{scenario}: no methods produced a fully valid completed fit.{suffix}")
            continue
        headline_valid = _headline_rows(valid)
        best = headline_valid.sort_values(["rmse", "mean_elapsed_sec"]).iloc[0]
        cov = headline_valid.sort_values(["coverage_95", "rmse"], ascending=[False, True]).iloc[0]
        suffix = f" Incomplete runs: {', '.join(incomplete)}." if incomplete else ""
        lines.append(
            f"{scenario}: best RMSE was {best['method']} ({best['rmse']:.3f}); "
            f"highest coverage was {cov['method']} ({cov['coverage_95']:.3f}).{suffix}"
        )

    return lines


def build_pdf(benchmark_dir: Path, output_pdf: Path) -> Path:
    report_dir = benchmark_dir / "report"
    figures_dir = report_dir / "figures"
    summary_df = pd.read_csv(benchmark_dir / "benchmark_summary.csv")
    runs_df = pd.read_csv(benchmark_dir / "benchmark_runs.csv")
    metadata = json.loads((benchmark_dir / "benchmark_metadata.json").read_text(encoding="utf-8"))

    overall = overall_method_metrics(runs_df)
    reportable_overall = overall[overall["successful_runs"] > 0].copy()
    headline_overall = _headline_rows(overall)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    if not REPORTLAB_AVAILABLE:
        lines = _fallback_report_lines(benchmark_dir, metadata, overall, summary_df)
        return _write_fallback_pdf(lines, output_pdf)

    styles = _styles()
    doc = BaseDocTemplate(
        str(output_pdf),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=30,
        title="MetaFrontierLab Benchmark Report",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame], onPage=_page_number)])

    story = []
    story.append(Paragraph("MetaFrontierLab Benchmark Report", styles["title"]))
    story.append(Paragraph(f"Generated from: {benchmark_dir}", styles["subtitle"]))
    story.append(Paragraph(f"Replications per scenario: {metadata['replications']}", styles["body"]))
    story.append(Paragraph(f"Methods benchmarked: {', '.join(metadata['methods'])}", styles["body"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Executive Summary", styles["heading"]))
    if not headline_overall.empty:
        top = headline_overall.sort_values(["rmse", "mean_elapsed_sec"]).iloc[0]
        coverage_leader = headline_overall.sort_values(["coverage_95", "rmse"], ascending=[False, True]).iloc[0]
        story.append(Paragraph(f"Best overall RMSE in this run: <b>{top['method']}</b> at {top['rmse']:.3f}.", styles["bullet"], bulletText="-"))
        story.append(Paragraph(f"Highest observed coverage: <b>{coverage_leader['method']}</b> at {coverage_leader['coverage_95']:.3f}.", styles["bullet"], bulletText="-"))
    else:
        story.append(Paragraph("No methods produced a fully valid completed fit in this run.", styles["bullet"], bulletText="-"))
    fast_pool = headline_overall.dropna(subset=["mean_elapsed_sec"])
    if not fast_pool.empty:
        fastest = fast_pool.sort_values(["mean_elapsed_sec", "method"]).iloc[0]
        story.append(Paragraph(f"Fastest method: <b>{fastest['method']}</b> at {fastest['mean_elapsed_sec']:.3f} seconds per fit.", styles["bullet"], bulletText="-"))
    incomplete = overall.loc[overall["success_rate"] < 1.0, "method"].tolist()
    if incomplete:
        story.append(Paragraph(f"Methods with incomplete runs: {', '.join(incomplete)}.", styles["bullet"], bulletText="-"))
    story.append(Paragraph("<b>mean_elapsed_sec</b> summarizes valid completed fits only; <b>mean_elapsed_sec_attempted</b> includes failures and adapter startup overhead.", styles["bullet"], bulletText="-"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Overall Method Ranking", styles["heading"]))
    story.append(
        _build_table(
            _format_df(
                overall,
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
            )
        )
    )
    story.append(Spacer(1, 12))
    story.append(Paragraph("Scenario Highlights", styles["heading"]))
    for scenario, group in summary_df.groupby("scenario", sort=False):
        valid = group[group["successful_runs"] > 0].copy()
        incomplete = group.loc[group["success_rate"] < 1.0, "method"].tolist()
        if valid.empty:
            suffix = f" Incomplete runs: {', '.join(incomplete)}." if incomplete else ""
            story.append(Paragraph(f"<b>{scenario}</b>: no methods produced a fully valid completed fit.{suffix}", styles["bullet"], bulletText="-"))
            continue
        headline_valid = _headline_rows(valid)
        best = headline_valid.sort_values(["rmse", "mean_elapsed_sec"]).iloc[0]
        cov = headline_valid.sort_values(["coverage_95", "rmse"], ascending=[False, True]).iloc[0]
        suffix = f" Incomplete runs: {', '.join(incomplete)}." if incomplete else ""
        story.append(
            Paragraph(
                f"<b>{scenario}</b>: best RMSE was {best['method']} ({best['rmse']:.3f}); highest coverage was {cov['method']} ({cov['coverage_95']:.3f}).{suffix}",
                styles["bullet"],
                bulletText="-",
            )
        )

    story.append(PageBreak())
    story.append(Paragraph("Scenario Table", styles["heading"]))
    scenario_table = _format_df(
        summary_df,
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
    )
    story.append(_build_table(scenario_table, max_rows=len(scenario_table)))

    figure_pages = [
        ("RMSE by Scenario", figures_dir / "rmse_by_scenario.png"),
        ("Bias by Scenario", figures_dir / "bias_by_scenario.png"),
        ("Coverage by Scenario", figures_dir / "coverage_by_scenario.png"),
        ("Speed-Accuracy Frontier", figures_dir / "speed_accuracy_frontier.png"),
    ]
    for title, img_path in figure_pages:
        if not img_path.exists():
            continue
        story.append(PageBreak())
        story.append(Paragraph(title, styles["heading"]))
        story.append(Paragraph("Figure generated from the benchmark summary.", styles["caption"]))
        img = Image(str(img_path))
        aspect = img.imageHeight / float(img.imageWidth)
        img.drawWidth = doc.width
        img.drawHeight = doc.width * aspect
        if img.drawHeight > doc.height - 90:
            img.drawHeight = doc.height - 90
            img.drawWidth = img.drawHeight / aspect
        story.append(img)

    story.append(PageBreak())
    story.append(Paragraph("Methods Appendix", styles["heading"]))
    appendix_lines = [
        "TBEMA: exact sparse-data meta-analysis with stacked bias tempering, transport weighting, and ridge-regularized target-aware meta-regression.",
        "DerSimonian-Laird: standard normal-normal random-effects benchmark.",
        "Henmi-Copas: publication-bias-robust interval method.",
        "metafor trimfill: trim-and-fill adjustment from metafor.",
        "metafor selmodel: step-function selection model from metafor.",
        "Copas selection: Copas model from metasens.",
        "RoBMA BiBMA: Bayesian model averaging for binary outcomes, using the fast spike-and-slab algorithm.",
    ]
    for line in appendix_lines:
        story.append(Paragraph(line, styles["bullet"], bulletText="-"))

    doc.build(story)
    return output_pdf


def main() -> None:
    args = parse_args()
    pdf_path = build_pdf(Path(args.benchmark_dir), Path(args.output_pdf))
    print(f"Benchmark PDF generated: {pdf_path}")


if __name__ == "__main__":
    main()
