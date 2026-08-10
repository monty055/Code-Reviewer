import json

from reviewer_agent.models import (
    AcceptanceCriterion,
    CriterionResult,
    CriterionStatus,
    Evidence,
    Feature,
    FeatureReport,
    ReviewReport,
)
from reviewer_agent.report import render_html, render_json, render_markdown


def build_sample_report() -> ReviewReport:
    feature = Feature(id="F1", title="Login", description="Users can log in.")
    criterion = AcceptanceCriterion(id="F1-AC1", text="Reject invalid passwords")
    result = CriterionResult(
        criterion=criterion,
        status=CriterionStatus.MET,
        confidence=0.8,
        rationale="Found matching validation logic.",
        evidence=[Evidence(file="login.py", line_number=3, snippet="if invalid(password):")],
    )
    feature_report = FeatureReport(feature=feature, matched_files=["login.py"], criterion_results=[result])
    return ReviewReport(
        requirements_source="prd.md",
        codebase_source="src/",
        feature_reports=[feature_report],
        unmatched_files=["unused.py"],
    )


def test_render_markdown_contains_key_sections():
    report = build_sample_report()
    md = render_markdown(report)

    assert "# Source Code Review Report" in md
    assert "F1: Login" in md
    assert "Reject invalid passwords" in md
    assert "login.py:3" in md
    assert "unused.py" in md
    assert "✅ Met" in md


def test_render_html_is_a_standalone_document_with_readable_narrative():
    report = build_sample_report()
    doc = render_html(report)

    assert doc.startswith("<!DOCTYPE html>")
    assert "Requirement Compliance Index (RCI) Report" in doc
    assert "<style>" in doc  # self-contained, no external assets
    assert "F1: Login" in doc
    assert "Reject invalid passwords" in doc
    assert "login.py:3" in doc
    assert "unused.py" in doc
    # Narrative sentence describing feature-level compliance in plain English.
    assert "acceptance criteria are fully met" in doc
    assert "100%" in doc  # single Met criterion -> full compliance for this feature


def test_render_html_escapes_untrusted_content():
    feature = Feature(id="F1", title="<script>alert(1)</script>", description="")
    criterion = AcceptanceCriterion(id="AC-1", text="Do <b>the</b> thing & validate")
    result = CriterionResult(
        criterion=criterion,
        status=CriterionStatus.NOT_MET,
        confidence=0.1,
        rationale="No evidence found",
    )
    feature_report = FeatureReport(feature=feature, matched_files=[], criterion_results=[result])
    report = ReviewReport(
        requirements_source="prd.md", codebase_source="src/", feature_reports=[feature_report]
    )

    doc = render_html(report)

    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;" in doc


def test_render_json_roundtrips_expected_fields():
    report = build_sample_report()
    data = json.loads(render_json(report))

    assert data["requirements_source"] == "prd.md"
    assert data["features"][0]["id"] == "F1"
    assert data["features"][0]["criteria"][0]["status"] == "Met"
    assert data["unmatched_files"] == ["unused.py"]
