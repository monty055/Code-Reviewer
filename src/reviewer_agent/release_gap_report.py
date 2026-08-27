"""Render release-notes gap analysis reports as Markdown or JSON."""

from __future__ import annotations

import json

from .release_gap_models import ReleaseGapFinding, ReleaseGapReport, ReleaseItemStatus


def render_markdown(report: ReleaseGapReport) -> str:
    lines = [
        "# Release Gap Analysis Report",
        "",
        "## Release Validation",
        "",
        f"- **User Stories Release:** {report.user_stories_release or 'Not identified'}",
        f"- **Development Release Notes Release:** {report.development_release_notes_release or 'Not identified'}",
        f"- **Validation Status:** {report.validation_status.value}",
        f"- **Result:** {report.validation_message}",
        "",
    ]
    if not report.comparison_completed:
        lines.extend(
            [
                "**Comparison was stopped. No gap findings were generated.**",
                "",
            ]
        )
        return "\n".join(lines)

    counts = report.counts
    lines.extend(
        [
            "## Executive Summary",
            "",
            f"- **Release:** {report.user_stories_release}",
            "- **Comparison Status:** Completed",
            f"- **Source Scope:** `{report.user_stories_source}` and `{report.development_release_notes_source}` for {report.user_stories_release} only",
            f"- **Total User Stories Analyzed:** {len(report.stories)}",
            f"- **Total Items Covered:** {counts[ReleaseItemStatus.COVERED.value]}",
            f"- **Total Partially Covered:** {counts[ReleaseItemStatus.PARTIALLY_COVERED.value]}",
            f"- **Total Missing:** {counts[ReleaseItemStatus.MISSING.value]}",
            f"- **Total Contradictory:** {counts[ReleaseItemStatus.CONTRADICTORY.value]}",
            f"- **Total Needs Clarification:** {counts[ReleaseItemStatus.NEEDS_CLARIFICATION.value]}",
            "",
            "## Gap Analysis",
            "",
        ]
    )

    gaps = [finding for finding in report.findings if finding.gap_id]
    if not gaps:
        lines.extend(["_No gaps identified from the provided inputs._", ""])
    else:
        lines.extend(
            [
                "| Gap ID | Ticket / User Story | Feature | FACT: Source Evidence from User Story | Dev Release Note Evidence | Status | Gap Category | GAP | Recommendation |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for finding in gaps:
            lines.append(_finding_row(finding))
        lines.append("")

    covered = [finding for finding in report.findings if not finding.gap_id]
    if covered:
        lines.extend(
            [
                "## Covered Items",
                "",
                "| Ticket / User Story | Feature | FACT: Source Evidence from User Story | Dev Release Note Evidence |",
                "|---|---|---|---|",
            ]
        )
        for finding in covered:
            lines.append(
                f"| {_escape(finding.item.ticket)} | {_escape(finding.item.feature)} | "
                f"{_escape(finding.item.source_evidence)} | "
                f"{_escape(finding.dev_release_note_evidence)} |"
            )
        lines.append("")

    lines.extend(
        [
            "---",
            "_This report compares only the two provided documents. It does not infer dependencies, functionality, limitations, or root causes._",
            "",
        ]
    )
    return "\n".join(lines)


def _finding_row(finding: ReleaseGapFinding) -> str:
    return (
        f"| {finding.gap_id} | {_escape(finding.item.ticket)} | "
        f"{_escape(finding.item.feature)} | {_escape(finding.item.source_evidence)} | "
        f"{_escape(finding.dev_release_note_evidence)} | {finding.status.value} | "
        f"{finding.item.category.value} | {_escape(finding.gap)} | "
        f"{_escape(finding.recommendation)} |"
    )


def render_json(report: ReleaseGapReport) -> str:
    payload = {
        "release_validation": {
            "user_stories_release": report.user_stories_release,
            "development_release_notes_release": report.development_release_notes_release,
            "validation_status": report.validation_status.value,
            "message": report.validation_message,
        },
        "comparison_status": "Completed" if report.comparison_completed else "Stopped",
        "source_scope": {
            "user_stories": report.user_stories_source,
            "development_release_notes": report.development_release_notes_source,
        },
        "executive_summary": {
            "total_user_stories_analyzed": len(report.stories),
            **{_count_key(status): count for status, count in report.counts.items()},
        },
        "findings": [_finding_dict(finding) for finding in report.findings],
    }
    return json.dumps(payload, indent=2)


def _count_key(status: str) -> str:
    return "total_" + status.lower().replace(" ", "_")


def _finding_dict(finding: ReleaseGapFinding) -> dict:
    return {
        "gap_id": finding.gap_id,
        "ticket": finding.item.ticket,
        "feature": finding.item.feature,
        "information_type": finding.item.information_type,
        "fact": {
            "source": "User Story",
            "evidence": finding.item.source_evidence,
            "detail": finding.item.detail,
        },
        "development_release_note_evidence": finding.dev_release_note_evidence,
        "status": finding.status.value,
        "gap_category": finding.item.category.value,
        "gap": finding.gap,
        "recommendation": finding.recommendation,
    }


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
