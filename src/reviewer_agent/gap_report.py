"""Renders a :class:`~reviewer_agent.gap_models.GapAnalysisReport` into
Markdown (default, human-friendly) or JSON (machine-readable)."""

from __future__ import annotations

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
