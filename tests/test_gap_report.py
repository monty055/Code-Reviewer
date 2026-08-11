import json

from reviewer_agent.gap_analysis import run_gap_analysis
from reviewer_agent.gap_report import render_html, render_json, render_markdown
from reviewer_agent.requirements_parser import parse_requirements_text

_TEXT = """# Task Creation

As a logged-in user, I want to create a task so that I can track my work.

### Acceptance Criteria

- AC-1: A task cannot be created without a title.
- AC-2: A newly created task defaults to status "pending".
"""


def _build_report():
    features = parse_requirements_text(_TEXT)
    return run_gap_analysis(features, requirements_source="inline")


def test_render_markdown_includes_sections():
    report = _build_report()
    md = render_markdown(report)
    assert "# Requirements Gap Analysis Report" in md
    assert "Task Creation" in md
    assert "User Story Gaps" in md
    assert "Design Gaps" in md
    assert "Mandatory Information for Test-Case Generation" in md
    assert "Document-Level Design Gaps" in md


def test_render_html_is_standalone_and_includes_sections():
    report = _build_report()
    rendered = render_html(report)
    assert rendered.startswith("<!DOCTYPE html>")
    assert "Requirements Gap Analysis Report" in rendered
    assert "Task Creation" in rendered
    assert "User Story Gaps" in rendered
    assert "Design Gaps" in rendered
    assert "Mandatory Information for Test-Case Generation" in rendered
    assert "Document-Level Design Gaps" in rendered
    assert "Overall Test-Data Readiness" in rendered


def test_render_json_round_trips():
    report = _build_report()
    payload = json.loads(render_json(report))
    assert payload["requirements_source"] == "inline"
    assert len(payload["features"]) == 1
    feature_payload = payload["features"][0]
    assert feature_payload["title"] == "Task Creation"
    assert len(feature_payload["test_data_requirements"]) == 2
    assert "readiness_score" in feature_payload
