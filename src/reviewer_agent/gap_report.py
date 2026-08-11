"""Renders a :class:`~reviewer_agent.gap_models.GapAnalysisReport` into
Markdown (default, human-friendly), JSON (machine-readable), or a standalone
HTML report suitable for sharing with non-technical stakeholders."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from .gap_models import FeatureGapAnalysis, GapAnalysisReport, GapFinding


def render_markdown(report: GapAnalysisReport) -> str:
    lines: list[str] = []
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# Requirements Gap Analysis Report")
    lines.append("")
    lines.append(f"- **Requirements document:** `{report.requirements_source}`")
    lines.append(f"- **Generated:** {generated_at}")
    lines.append(f"- **Total gaps identified:** {report.total_gap_count}")
    lines.append(
        f"- **Overall test-data readiness:** {report.overall_readiness_score:.0%} of acceptance "
        "criteria already have enough information to generate test cases with test data."
    )
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Feature | User Story Gaps | Design Gaps | Test-Data Ready |")
    lines.append("|---|---|---|---|")
    for fa in report.feature_analyses:
        lines.append(
            f"| {fa.feature.id}: {fa.feature.title} | {len(fa.user_story_gaps)} | "
            f"{len(fa.design_gaps)} | {fa.readiness_score:.0%} |"
        )
    lines.append("")

    lines.append("## Detailed Findings")
    lines.append("")
    for fa in report.feature_analyses:
        lines.append(f"### {fa.feature.id}: {fa.feature.title}")
        lines.append("")
        if fa.feature.description.strip():
            lines.append(f"> {fa.feature.description.strip()}")
            lines.append("")

        lines.append("#### User Story Gaps")
        lines.append("")
        _render_findings_md(lines, fa.user_story_gaps)

        lines.append("#### Design Gaps")
        lines.append("")
        _render_findings_md(lines, fa.design_gaps)

        lines.append("#### Mandatory Information for Test-Case Generation")
        lines.append("")
        if not fa.test_data_requirements:
            lines.append("_No acceptance criteria to analyze for test data._")
            lines.append("")
        else:
            lines.append("| Criterion | Identified Data Fields | Missing Mandatory Info |")
            lines.append("|---|---|---|")
            for req in fa.test_data_requirements:
                fields_str = ", ".join(req.data_fields) or "_none identified_"
                missing_str = "; ".join(req.missing_info) or "✅ Ready for test-case generation"
                lines.append(
                    f"| {req.criterion_id}: {_escape_pipe(req.criterion_text)} | {fields_str} | {missing_str} |"
                )
            lines.append("")

    if report.document_level_design_gaps:
        lines.append("## Document-Level Design Gaps")
        lines.append("")
        lines.append(
            "Non-functional requirement categories that are not mentioned anywhere in the "
            "document, across any feature:"
        )
        lines.append("")
        _render_findings_md(lines, report.document_level_design_gaps)

    lines.append("---")
    lines.append(
        "_Legend: 🔴 High severity · 🟠 Medium severity · 🟡 Low severity. This report is "
        "generated automatically using heuristics over the requirements document text; it is "
        "a starting point for a human reviewer/BA/QA lead, not a final judgement._"
    )

    return "\n".join(lines) + "\n"


def _render_findings_md(lines: list[str], findings: list[GapFinding]) -> None:
    if not findings:
        lines.append("_No gaps identified._")
        lines.append("")
        return
    for f in findings:
        lines.append(f"- {f.severity.emoji} **{f.severity.value}** — {_escape_pipe(f.description)}")
        lines.append(f"  - _Recommendation:_ {_escape_pipe(f.recommendation)}")
    lines.append("")


def render_json(report: GapAnalysisReport) -> str:
    def finding_dict(f: GapFinding) -> dict:
        return {
            "category": f.category.value,
            "severity": f.severity.value,
            "description": f.description,
            "recommendation": f.recommendation,
            "criterion_id": f.criterion_id,
        }

    payload = {
        "requirements_source": report.requirements_source,
        "total_gap_count": report.total_gap_count,
        "overall_readiness_score": report.overall_readiness_score,
        "document_level_design_gaps": [finding_dict(f) for f in report.document_level_design_gaps],
        "features": [_feature_analysis_dict(fa, finding_dict) for fa in report.feature_analyses],
    }
    return json.dumps(payload, indent=2)


def _feature_analysis_dict(fa: FeatureGapAnalysis, finding_dict) -> dict:
    return {
        "id": fa.feature.id,
        "title": fa.feature.title,
        "description": fa.feature.description,
        "user_story_gaps": [finding_dict(f) for f in fa.user_story_gaps],
        "design_gaps": [finding_dict(f) for f in fa.design_gaps],
        "readiness_score": fa.readiness_score,
        "test_data_requirements": [
            {
                "criterion_id": r.criterion_id,
                "criterion_text": r.criterion_text,
                "data_fields": r.data_fields,
                "missing_info": r.missing_info,
                "is_ready_for_test_case_generation": r.is_ready_for_test_case_generation,
            }
            for r in fa.test_data_requirements
        ],
    }


def _escape_pipe(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_html(report: GapAnalysisReport) -> str:
    """Render a standalone, self-contained HTML Gap Analysis report --
    written in plain English, suitable for sharing with a requirements
    author, BA, or QA lead who doesn't want to read Markdown/JSON."""

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    overall_pct = round(report.overall_readiness_score * 100)

    feature_sections = "\n".join(_render_feature_section_html(fa) for fa in report.feature_analyses)

    doc_level_html = ""
    if report.document_level_design_gaps:
        doc_level_html = f"""
        <section class="section">
          <h2>Document-Level Design Gaps</h2>
          <p>
            Non-functional requirement categories that are not mentioned anywhere in the
            document, across any feature:
          </p>
          {_render_findings_html(report.document_level_design_gaps)}
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Requirements Gap Analysis Report</title>
<style>{_HTML_REPORT_CSS}</style>
</head>
<body>
  <div class="report">
    <header class="report-header">
      <h1>Requirements Gap Analysis Report</h1>
      <p class="subtitle">
        A plain-English breakdown of user-story gaps, design gaps, and the information still
        needed to generate test cases with test data, for every feature in the requirements
        document below.
      </p>
      <table class="meta-table">
        <tr><th>Requirements document</th><td>{html.escape(report.requirements_source)}</td></tr>
        <tr><th>Report generated</th><td>{generated_at}</td></tr>
        <tr><th>Total gaps identified</th><td>{report.total_gap_count}</td></tr>
      </table>
    </header>

    <section class="rci-banner {_readiness_css_class(report.overall_readiness_score)}">
      <div class="rci-score">{overall_pct}%</div>
      <div class="rci-explanation">
        <h2>Overall Test-Data Readiness: {overall_pct}%</h2>
        <p>{_overall_narrative(report)}</p>
      </div>
    </section>

    <section class="section">
      <h2>What This Report Means</h2>
      <p>
        For every feature/user story parsed from the requirements document, this report checks
        three things: whether the story and its acceptance criteria are complete and unambiguous
        (<strong>User Story Gaps</strong>), whether common non-functional requirement categories
        are addressed (<strong>Design Gaps</strong>), and whether each acceptance criterion
        already has enough concrete information (example values, formats, boundaries, and
        valid/invalid coverage) to generate a test case with real test data
        (<strong>Test-Data Readiness</strong>).
      </p>
      <ul class="legend">
        <li><span class="pill severity-high">High</span> Blocks reliable implementation, review, or test-case generation -- resolve first.</li>
        <li><span class="pill severity-medium">Medium</span> Should be clarified before test cases/automation are written.</li>
        <li><span class="pill severity-low">Low</span> Worth confirming, but may be intentionally out of scope.</li>
      </ul>
      <p class="disclaimer">
        This report is produced automatically using heuristics over the requirements document
        text. It does not know your product context, so use it as a checklist for a human
        reviewer (BA/PM/QA lead) rather than a final judgement.
      </p>
    </section>

    <section class="section">
      <h2>Feature-by-Feature Summary</h2>
      <table class="summary-table">
        <thead>
          <tr><th>Feature</th><th>User Story Gaps</th><th>Design Gaps</th><th>Test-Data Readiness</th></tr>
        </thead>
        <tbody>
          {_render_summary_rows_html(report)}
        </tbody>
      </table>
    </section>

    {feature_sections}

    {doc_level_html}

    <footer class="report-footer">
      <p>Generated automatically by the Requirements Gap Analysis Agent &middot; {generated_at}</p>
    </footer>
  </div>
</body>
</html>
"""


def _render_summary_rows_html(report: GapAnalysisReport) -> str:
    rows = []
    for fa in report.feature_analyses:
        pct = round(fa.readiness_score * 100)
        rows.append(
            f"""<tr>
              <td><a href="#{_anchor(fa.feature.id)}">{html.escape(fa.feature.id)}: {html.escape(fa.feature.title)}</a></td>
              <td>{len(fa.user_story_gaps)}</td>
              <td>{len(fa.design_gaps)}</td>
              <td><span class="mini-bar"><span class="mini-bar-fill {_readiness_css_class(fa.readiness_score)}" style="width:{pct}%"></span></span> {pct}%</td>
            </tr>"""
        )
    return "\n".join(rows)


def _render_feature_section_html(fa: FeatureGapAnalysis) -> str:
    description_html = (
        f'<p class="feature-description">{html.escape(fa.feature.description.strip())}</p>'
        if fa.feature.description.strip()
        else ""
    )

    if not fa.test_data_requirements:
        test_data_html = "<p><em>No acceptance criteria to analyze for test data.</em></p>"
    else:
        rows = []
        for r in fa.test_data_requirements:
            fields_html = (
                "".join(f'<span class="test-data-chip">{html.escape(f)}</span>' for f in r.data_fields)
                or "<em>none identified</em>"
            )
            missing_html = (
                "".join(f"<div>{html.escape(m)}</div>" for m in r.missing_info)
                or '<span class="pill ready">&#9989; Ready</span>'
            )
            rows.append(
                f"""<tr>
                  <td><strong>{html.escape(r.criterion_id)}</strong>: {html.escape(r.criterion_text)}</td>
                  <td>{fields_html}</td>
                  <td>{missing_html}</td>
                </tr>"""
            )
        test_data_html = f"""<table class="criteria-table">
          <thead>
            <tr><th>Acceptance Criterion</th><th>Identified Data Fields</th><th>Missing Mandatory Info</th></tr>
          </thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""

    pct = round(fa.readiness_score * 100)
    return f"""
    <section class="section feature-section" id="{_anchor(fa.feature.id)}">
      <h2>{html.escape(fa.feature.id)}: {html.escape(fa.feature.title)} <span class="feature-pct {_readiness_css_class(fa.readiness_score)}">{pct}% ready</span></h2>
      {description_html}
      <h3 class="subheading">User Story Gaps</h3>
      {_render_findings_html(fa.user_story_gaps)}
      <h3 class="subheading">Design Gaps</h3>
      {_render_findings_html(fa.design_gaps)}
      <h3 class="subheading">Mandatory Information for Test-Case Generation</h3>
      {test_data_html}
    </section>
    """


def _render_findings_html(findings: list[GapFinding]) -> str:
    if not findings:
        return "<p><em>No gaps identified.</em></p>"
    items = "".join(
        f"""<div class="gap-finding">
          <span class="pill severity-{f.severity.value.lower()}">{html.escape(f.severity.value)}</span>
          {html.escape(f.description)}
          <p class="recommendation"><strong>Recommendation:</strong> {html.escape(f.recommendation)}</p>
        </div>"""
        for f in findings
    )
    return f'<div class="gap-findings">{items}</div>'


def _overall_narrative(report: GapAnalysisReport) -> str:
    total_user_story_gaps = sum(len(fa.user_story_gaps) for fa in report.feature_analyses)
    total_design_gaps = sum(len(fa.design_gaps) for fa in report.feature_analyses) + len(
        report.document_level_design_gaps
    )
    return (
        f"Across {len(report.feature_analyses)} feature(s), this report identified "
        f"{total_user_story_gaps} user-story gap(s) and {total_design_gaps} design gap(s). "
        + _overall_recommendation(report.overall_readiness_score)
    )


def _overall_recommendation(readiness: float) -> str:
    if readiness >= 0.9:
        return "Most acceptance criteria already have enough concrete information to generate test cases with test data."
    if readiness >= 0.5:
        return "Some acceptance criteria are ready for test-case generation, but many still need clarification -- see the feature sections below for the specific missing information."
    return "Most acceptance criteria are missing information (example values, formats, boundaries, or valid/invalid coverage) needed to generate test cases with test data -- see the feature sections below for what to clarify first."


def _readiness_css_class(readiness: float) -> str:
    if readiness >= 0.9:
        return "cov-high"
    if readiness >= 0.5:
        return "cov-medium"
    return "cov-low"


def _anchor(feature_id: str) -> str:
    return f"gap-feature-{feature_id.lower()}"


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
.subheading { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); margin: 18px 0 8px; }
.legend { list-style: none; padding: 0; margin: 12px 0; }
.legend li { margin-bottom: 6px; font-size: 0.92rem; }
.disclaimer { font-size: 0.85rem; color: var(--muted); border-top: 1px dashed var(--border); padding-top: 12px; margin-top: 14px; }
.pill {
  display: inline-block; padding: 2px 10px; border-radius: 999px; font-weight: 700;
  font-size: 0.78rem; margin-right: 4px;
}
.pill.severity-high { color: #c62839; background: #fbe6e9; }
.pill.severity-medium { color: #a56b00; background: #fdf1dc; }
.pill.severity-low { color: #5c6270; background: #eceef3; }
.pill.ready { color: #1e8e4f; background: #e6f6ec; }
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
.feature-section h2 { display: flex; align-items: center; gap: 10px; font-size: 1.1rem; flex-wrap: wrap; }
.feature-pct { font-size: 0.85rem; padding: 2px 10px; border-radius: 999px; background: var(--border); }
.feature-pct.cov-high { background: #e6f6ec; color: #1e8e4f; }
.feature-pct.cov-medium { background: #fdf1dc; color: #a56b00; }
.feature-pct.cov-low { background: #fbe6e9; color: #c62839; }
.feature-description { color: var(--muted); font-style: italic; }
.gap-finding { border-bottom: 1px solid var(--border); padding: 10px 0; font-size: 0.92rem; }
.gap-finding:last-child { border-bottom: none; }
.gap-finding .recommendation { margin: 4px 0 0; color: var(--muted); font-size: 0.85rem; }
.test-data-chip {
  display: inline-block; background: #eef1f8; border-radius: 6px; padding: 2px 8px; margin: 2px 4px 2px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem; color: var(--accent);
}
.report-footer { text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 28px; }
code { background: #eef1f8; padding: 1px 5px; border-radius: 4px; font-size: 0.85em; }
@media print {
  body { background: white; }
  .section, .rci-banner { break-inside: avoid; }
}
"""
