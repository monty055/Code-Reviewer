"""Renders a :class:`~reviewer_agent.models.ReviewReport` into human-readable
formats: Markdown (default), JSON, and a plain-text summary."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from .models import CriterionStatus, ReviewReport


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


def _status_counts(fr) -> dict[CriterionStatus, int]:
    counts = {s: 0 for s in CriterionStatus}
    for cr in fr.criterion_results:
        counts[cr.status] += 1
    return counts


def _escape_pipe(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()
