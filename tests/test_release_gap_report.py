import json

from reviewer_agent.release_gap_analyzer import analyze_release_gap
from reviewer_agent.release_gap_report import render_json, render_markdown


def test_markdown_report_contains_validation_summary_and_evidence():
    report = analyze_release_gap(
        """Release 24
JIRA-101
As a user, I should be able to upload an image.
Maximum file size is subject to R&D confirmation.
""",
        """Release 24
Included:
- Image upload functionality
""",
    )

    rendered = render_markdown(report)

    assert "# Release Gap Analysis Report" in rendered
    assert "**Validation Status:** PASSED" in rendered
    assert "**Total User Stories Analyzed:** 1" in rendered
    assert "GAP-001" in rendered
    assert "Maximum file size is subject to R&D confirmation." in rendered
    assert "Not found in the provided Development Release Notes." in rendered


def test_failed_validation_report_does_not_render_gap_table():
    report = analyze_release_gap(
        "Release 24\nJIRA-1\nAs a user, I can log in.",
        "Release 23\n- Login",
    )

    rendered = render_markdown(report)

    assert "**Validation Status:** FAILED" in rendered
    assert "Comparison was stopped" in rendered
    assert "## Gap Analysis" not in rendered


def test_json_report_is_machine_readable():
    report = analyze_release_gap(
        "Release 5\nJIRA-5\nAs a user, I can log in.",
        "Release 5\n- Login",
    )

    payload = json.loads(render_json(report))

    assert payload["release_validation"]["validation_status"] == "PASSED"
    assert payload["comparison_status"] == "Completed"
    assert payload["executive_summary"]["total_user_stories_analyzed"] == 1
    assert payload["findings"][0]["fact"]["source"] == "User Story"
