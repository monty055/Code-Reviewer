"""Renders a :class:`~reviewer_agent.models.ReviewReport` into human-readable
formats: Markdown (default), JSON, and a standalone HTML "Requirement
Compliance Index" (RCI) report written in plain English."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime, timezone

from .models import CriterionStatus, FeatureReport, ReviewReport


def render_markdown(report: ReviewReport) -> str:
    lines: list[str] = []
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# Source Code Review Report")
    lines.append("")
    lines.append(f"- **Requirements document:** `{report.requirements_source}`")
    lines.append(f"- **Source code:** `{report.codebase_source}`")
    lines.append(f"- **Generated:** {generated_at}")
    lines.append(f"- **Overall acceptance-criteria coverage:** {report.overall_coverage:.0%}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Feature | Matched Files | Criteria | Met | Partially Met | Not Met | Needs Review | Coverage |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for fr in report.feature_reports:
        counts = _status_counts(fr)
        total = len(fr.criterion_results)
        files_str = ", ".join(f"`{p}`" for p in fr.matched_files) or "_none found_"
        lines.append(
            f"| {fr.feature.id}: {fr.feature.title} | {files_str} | {total} | "
            f"{counts[CriterionStatus.MET]} | {counts[CriterionStatus.PARTIALLY_MET]} | "
            f"{counts[CriterionStatus.NOT_MET]} | {counts[CriterionStatus.NEEDS_REVIEW]} | "
            f"{fr.coverage:.0%} |"
        )
    lines.append("")

    lines.append("## Detailed Findings")
    lines.append("")
    for fr in report.feature_reports:
        lines.append(f"### {fr.feature.id}: {fr.feature.title}")
        lines.append("")
        if fr.feature.description.strip():
            lines.append(f"> {fr.feature.description.strip()}")
            lines.append("")
        files_str = ", ".join(f"`{p}`" for p in fr.matched_files) or "_No matching source files were found._"
        lines.append(f"**Matched source files:** {files_str}")
        lines.append("")

        if not fr.criterion_results:
            lines.append("_No acceptance criteria were found for this feature in the requirements document._")
            lines.append("")
            continue

        lines.append("| Acceptance Criterion | Status | Confidence | Rationale | Evidence |")
        lines.append("|---|---|---|---|---|")
        for cr in fr.criterion_results:
            evidence_str = "; ".join(
                f"`{e.file}:{e.line_number}` — {_escape_pipe(e.snippet)}" for e in cr.evidence
            ) or "—"
            lines.append(
                f"| {cr.criterion.id}: {_escape_pipe(cr.criterion.text)} "
                f"| {cr.status.emoji} {cr.status.value} "
                f"| {cr.confidence:.0%} "
                f"| {_escape_pipe(cr.rationale)} "
                f"| {evidence_str} |"
            )
        lines.append("")

    if report.unmatched_files:
        lines.append("## Source Files Not Linked To Any Feature")
        lines.append("")
        lines.append(
            "These files did not score highly against any feature's keywords. They may be "
            "infrastructure/utility code, or may indicate undocumented functionality:"
        )
        lines.append("")
        for path in report.unmatched_files:
            lines.append(f"- `{path}`")
        lines.append("")

    lines.append("---")
    lines.append(
        "_Legend: ✅ Met · 🟡 Partially Met · ❌ Not Met · ❓ Needs Manual Review. "
        "This report is generated automatically and should be validated by a human reviewer, "
        "especially for ❓ and 🟡 results._"
    )

    return "\n".join(lines) + "\n"


def render_json(report: ReviewReport) -> str:
    def default(obj):
        if isinstance(obj, CriterionStatus):
            return obj.value
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    payload = {
        "requirements_source": report.requirements_source,
        "codebase_source": report.codebase_source,
        "overall_coverage": report.overall_coverage,
        "unmatched_files": report.unmatched_files,
        "features": [
            {
                "id": fr.feature.id,
                "title": fr.feature.title,
                "description": fr.feature.description,
                "matched_files": fr.matched_files,
                "coverage": fr.coverage,
                "criteria": [
                    {
                        "id": cr.criterion.id,
                        "text": cr.criterion.text,
                        "status": cr.status.value,
                        "confidence": cr.confidence,
                        "rationale": cr.rationale,
                        "evidence": [asdict(e) for e in cr.evidence],
                    }
                    for cr in fr.criterion_results
                ],
            }
            for fr in report.feature_reports
        ],
    }
    return json.dumps(payload, indent=2, default=default)


_STATUS_COLORS = {
    CriterionStatus.MET: "#1e8e4f",
    CriterionStatus.PARTIALLY_MET: "#a56b00",
    CriterionStatus.NOT_MET: "#c62839",
    CriterionStatus.NEEDS_REVIEW: "#5c6270",
}

_STATUS_BG = {
    CriterionStatus.MET: "#e6f6ec",
    CriterionStatus.PARTIALLY_MET: "#fdf1dc",
    CriterionStatus.NOT_MET: "#fbe6e9",
    CriterionStatus.NEEDS_REVIEW: "#eceef3",
}


def render_html(report: ReviewReport) -> str:
    """Render a standalone, self-contained HTML "Requirement Compliance
    Index" (RCI) report, written in plain human-readable English so it can
    be opened directly in a browser or shared with non-technical
    stakeholders (product managers, QA, auditors, etc.)."""

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    overall_pct = round(report.overall_coverage * 100)

    feature_sections = "\n".join(_render_feature_section_html(fr) for fr in report.feature_reports)

    unmatched_html = ""
    if report.unmatched_files:
        items = "\n".join(f"<li><code>{html.escape(p)}</code></li>" for p in report.unmatched_files)
        unmatched_html = f"""
        <section class="section">
          <h2>Source Files Not Linked to Any Feature</h2>
          <p>
            The following source files did not closely match any feature described in the
            requirements document. This is often normal (shared utilities, configuration,
            infrastructure code), but it can also point to functionality that was built
            without being documented, so it is worth a quick sanity check:
          </p>
          <ul class="file-list">{items}</ul>
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Requirement Compliance Index (RCI) Report</title>
<style>{_HTML_REPORT_CSS}</style>
</head>
<body>
  <div class="report">
    <header class="report-header">
      <h1>Requirement Compliance Index (RCI) Report</h1>
      <p class="subtitle">
        A plain-English summary of how well the reviewed source code satisfies the acceptance
        criteria described in the requirements document below.
      </p>
      <table class="meta-table">
        <tr><th>Requirements document</th><td>{html.escape(report.requirements_source)}</td></tr>
        <tr><th>Source code reviewed</th><td>{html.escape(report.codebase_source)}</td></tr>
        <tr><th>Report generated</th><td>{generated_at}</td></tr>
      </table>
    </header>

    <section class="rci-banner {_coverage_css_class(report.overall_coverage)}">
      <div class="rci-score">{overall_pct}%</div>
      <div class="rci-explanation">
        <h2>Overall Requirement Compliance Index: {overall_pct}%</h2>
        <p>{_overall_narrative(report)}</p>
      </div>
    </section>

    <section class="section">
      <h2>What This Report Means</h2>
      <p>
        The <strong>Requirement Compliance Index (RCI)</strong> is the percentage of acceptance
        criteria, across every feature in the requirements document, that this automated review
        found to be <strong>Met</strong> or <strong>Partially Met</strong> by the current source
        code. For every feature below, each individual acceptance criterion is explained in plain
        English along with the evidence (specific files and lines) that led to the verdict.
      </p>
      <ul class="legend">
        <li><span class="pill met">Met</span> Strong evidence the criterion is implemented.</li>
        <li><span class="pill partial">Partially Met</span> Some supporting evidence was found, but it isn't conclusive -- please double check.</li>
        <li><span class="pill not-met">Not Met</span> No meaningful evidence was found in the matched source files.</li>
        <li><span class="pill needs-review">Needs Manual Review</span> No relevant source files could be identified at all -- a human should look into this.</li>
      </ul>
      <p class="disclaimer">
        This report is produced automatically by keyword-based (or, when configured, LLM-assisted)
        analysis. It does not execute the code or run your test suite, so treat every verdict --
        especially <span class="pill partial">Partially Met</span> and
        <span class="pill needs-review">Needs Manual Review</span> -- as a prompt for human
        review rather than a final judgement.
      </p>
    </section>

    <section class="section">
      <h2>Feature-by-Feature Summary</h2>
      <table class="summary-table">
        <thead>
          <tr><th>Feature</th><th>Acceptance Criteria</th><th>Compliance</th></tr>
        </thead>
        <tbody>
          {_render_summary_rows_html(report)}
        </tbody>
      </table>
    </section>

    {feature_sections}

    {unmatched_html}

    <footer class="report-footer">
      <p>Generated automatically by the Source Code Reviewer Agent · {generated_at}</p>
    </footer>
  </div>
</body>
</html>
"""


def _render_summary_rows_html(report: ReviewReport) -> str:
    rows = []
    for fr in report.feature_reports:
        pct = round(fr.coverage * 100)
        rows.append(
            f"""<tr>
              <td><a href="#{_anchor(fr.feature.id)}">{html.escape(fr.feature.id)}: {html.escape(fr.feature.title)}</a></td>
              <td>{len(fr.criterion_results)}</td>
              <td><span class="mini-bar"><span class="mini-bar-fill {_coverage_css_class(fr.coverage)}" style="width:{pct}%"></span></span> {pct}%</td>
            </tr>"""
        )
    return "\n".join(rows)


def _render_feature_section_html(fr: FeatureReport) -> str:
    files_html = (
        ", ".join(f"<code>{html.escape(p)}</code>" for p in fr.matched_files)
        if fr.matched_files
        else "<em>No matching source files were found.</em>"
    )
    description_html = (
        f'<p class="feature-description">{html.escape(fr.feature.description.strip())}</p>'
        if fr.feature.description.strip()
        else ""
    )

    if not fr.criterion_results:
        criteria_html = "<p><em>No acceptance criteria were found for this feature in the requirements document.</em></p>"
    else:
        rows = []
        for cr in fr.criterion_results:
            evidence_html = (
                "".join(
                    f'<div class="evidence-line"><code>{html.escape(e.file)}:{e.line_number}</code> '
                    f"&mdash; {html.escape(e.snippet)}</div>"
                    for e in cr.evidence
                )
                or '<span class="muted">No supporting lines found.</span>'
            )
            status_class = cr.status.name.lower().replace("_", "-")
            rows.append(
                f"""<tr>
                  <td><strong>{html.escape(cr.criterion.id)}</strong>: {html.escape(cr.criterion.text)}</td>
                  <td><span class="pill {status_class}">{cr.status.emoji} {html.escape(cr.status.value)}</span></td>
                  <td>{round(cr.confidence * 100)}%</td>
                  <td>{html.escape(cr.rationale)}</td>
                  <td>{evidence_html}</td>
                </tr>"""
            )
        criteria_html = f"""<table class="criteria-table">
          <thead>
            <tr><th>Acceptance Criterion</th><th>Status</th><th>Confidence</th><th>Explanation</th><th>Evidence</th></tr>
          </thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""

    pct = round(fr.coverage * 100)
    return f"""
    <section class="section feature-section" id="{_anchor(fr.feature.id)}">
      <h2>{html.escape(fr.feature.id)}: {html.escape(fr.feature.title)} <span class="feature-pct {_coverage_css_class(fr.coverage)}">{pct}%</span></h2>
      {description_html}
      <p class="narrative">{_feature_narrative(fr)}</p>
      <p class="matched-files"><strong>Matched source files:</strong> {files_html}</p>
      {criteria_html}
    </section>
    """


def _overall_narrative(report: ReviewReport) -> str:
    total_criteria = sum(len(fr.criterion_results) for fr in report.feature_reports)
    total_met = sum(
        1
        for fr in report.feature_reports
        for cr in fr.criterion_results
        if cr.status == CriterionStatus.MET
    )
    total_partial = sum(
        1
        for fr in report.feature_reports
        for cr in fr.criterion_results
        if cr.status == CriterionStatus.PARTIALLY_MET
    )
    total_not_met = sum(
        1
        for fr in report.feature_reports
        for cr in fr.criterion_results
        if cr.status == CriterionStatus.NOT_MET
    )
    total_needs_review = sum(
        1
        for fr in report.feature_reports
        for cr in fr.criterion_results
        if cr.status == CriterionStatus.NEEDS_REVIEW
    )
    return (
        f"Across {len(report.feature_reports)} feature(s) and {total_criteria} acceptance "
        f"criteria, the source code fully satisfies {total_met} criteria, partially satisfies "
        f"{total_partial}, does not appear to satisfy {total_not_met}, and {total_needs_review} "
        "could not be checked automatically because no relevant source files were found. "
        + _overall_recommendation(report.overall_coverage)
    )


def _overall_recommendation(coverage: float) -> str:
    if coverage >= 0.9:
        return "Overall, the codebase appears to closely match the documented requirements."
    if coverage >= 0.6:
        return "Overall, the codebase covers most of the documented requirements, but some gaps remain -- see the feature sections below for details."
    return "Overall, there are significant gaps between the documented requirements and what the reviewed source code appears to implement -- see the feature sections below for details."


def _feature_narrative(fr: FeatureReport) -> str:
    counts = _status_counts(fr)
    total = len(fr.criterion_results)
    if total == 0:
        return "This feature has no acceptance criteria listed in the requirements document, so it could not be evaluated."
    pct = round(fr.coverage * 100)
    parts = [
        f"{counts[CriterionStatus.MET]} of {total} acceptance criteria are fully met, "
        f"{counts[CriterionStatus.PARTIALLY_MET]} are partially met, "
        f"{counts[CriterionStatus.NOT_MET]} are not met, and "
        f"{counts[CriterionStatus.NEEDS_REVIEW]} need manual review, "
        f"for an overall compliance of {pct}%."
    ]
    if fr.matched_files:
        parts.append(f"This assessment is based on {len(fr.matched_files)} matched source file(s).")
    else:
        parts.append("No source files could be confidently matched to this feature, so a human reviewer should investigate where (or whether) it was implemented.")
    return " ".join(parts)


def _coverage_css_class(coverage: float) -> str:
    if coverage >= 0.9:
        return "cov-high"
    if coverage >= 0.6:
        return "cov-medium"
    return "cov-low"


def _anchor(feature_id: str) -> str:
    return f"feature-{feature_id.lower()}"


_HTML_REPORT_CSS = """
:root {
  --ink: #1b1f2a;
  --muted: #5c6270;
  --border: #e2e5ec;
  --bg: #f7f8fb;
  --card: #ffffff;
  --accent: #3355dd;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.55;
}
.report { max-width: 900px; margin: 0 auto; padding: 32px 24px 64px; }
.report-header h1 { margin: 0 0 6px; font-size: 1.7rem; }
.subtitle { color: var(--muted); margin: 0 0 16px; }
.meta-table { border-collapse: collapse; font-size: 0.88rem; margin-bottom: 24px; }
.meta-table th { text-align: left; color: var(--muted); padding: 3px 12px 3px 0; font-weight: 600; white-space: nowrap; }
.meta-table td { padding: 3px 0; }
.rci-banner {
  display: flex; align-items: center; gap: 24px;
  background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; margin-bottom: 28px;
  border-left: 6px solid var(--accent);
}
.rci-banner.cov-high { border-left-color: #1e8e4f; }
.rci-banner.cov-medium { border-left-color: #a56b00; }
.rci-banner.cov-low { border-left-color: #c62839; }
.rci-score { font-size: 2.6rem; font-weight: 800; min-width: 110px; text-align: center; }
.rci-explanation h2 { margin: 0 0 6px; font-size: 1.1rem; }
.rci-explanation p { margin: 0; color: var(--muted); }
.section { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 22px 24px; margin-bottom: 20px; }
.section h2 { margin-top: 0; font-size: 1.2rem; }
.legend { list-style: none; padding: 0; margin: 12px 0; }
.legend li { margin-bottom: 6px; font-size: 0.92rem; }
.disclaimer { font-size: 0.85rem; color: var(--muted); border-top: 1px dashed var(--border); padding-top: 12px; margin-top: 14px; }
.pill {
  display: inline-block; padding: 2px 10px; border-radius: 999px; font-weight: 700;
  font-size: 0.78rem; margin-right: 4px;
}
.pill.met { color: #1e8e4f; background: #e6f6ec; }
.pill.partially-met, .pill.partial { color: #a56b00; background: #fdf1dc; }
.pill.not-met { color: #c62839; background: #fbe6e9; }
.pill.needs-review, .pill.needs-manual-review { color: #5c6270; background: #eceef3; }
table.summary-table, table.criteria-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-top: 8px; }
table.summary-table th, table.summary-table td, table.criteria-table th, table.criteria-table td {
  text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top;
}
table.summary-table th, table.criteria-table th { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }
.mini-bar { display: inline-block; width: 90px; height: 8px; background: var(--border); border-radius: 999px; overflow: hidden; vertical-align: middle; margin-right: 6px; }
.mini-bar-fill { display: block; height: 100%; }
.mini-bar-fill.cov-high { background: #1e8e4f; }
.mini-bar-fill.cov-medium { background: #d99a1b; }
.mini-bar-fill.cov-low { background: #c62839; }
.feature-section h2 { display: flex; align-items: center; gap: 10px; font-size: 1.1rem; }
.feature-pct { font-size: 0.85rem; padding: 2px 10px; border-radius: 999px; background: var(--border); }
.feature-pct.cov-high { background: #e6f6ec; color: #1e8e4f; }
.feature-pct.cov-medium { background: #fdf1dc; color: #a56b00; }
.feature-pct.cov-low { background: #fbe6e9; color: #c62839; }
.feature-description { color: var(--muted); font-style: italic; }
.narrative { margin: 8px 0 14px; }
.matched-files { font-size: 0.88rem; color: var(--muted); margin-bottom: 10px; }
.evidence-line { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem; color: var(--muted); margin-bottom: 2px; }
.muted { color: var(--muted); font-size: 0.85rem; }
.file-list { columns: 2; font-size: 0.88rem; color: var(--muted); }
.report-footer { text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 28px; }
code { background: #eef1f8; padding: 1px 5px; border-radius: 4px; font-size: 0.85em; }
@media print {
  body { background: white; }
  .section, .rci-banner { break-inside: avoid; }
}
"""


def _status_counts(fr) -> dict[CriterionStatus, int]:
    counts = {s: 0 for s in CriterionStatus}
    for cr in fr.criterion_results:
        counts[cr.status] += 1
    return counts


def _escape_pipe(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()
