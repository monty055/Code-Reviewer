from pathlib import Path

from reviewer_agent.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_cli_review_end_to_end(tmp_path, capsys):
    output_path = tmp_path / "report.md"
    exit_code = main(
        [
            "review",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--source",
            str(EXAMPLES / "sample_app"),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    content = output_path.read_text()
    assert "User Authentication" in content
    assert "Task Creation" in content
    assert "Email Notifications" in content


def test_cli_review_html_format(tmp_path):
    output_path = tmp_path / "report.html"
    exit_code = main(
        [
            "review",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--source",
            str(EXAMPLES / "sample_app"),
            "--output",
            str(output_path),
            "--format",
            "html",
        ]
    )

    assert exit_code == 0
    content = output_path.read_text()
    assert content.startswith("<!DOCTYPE html>")
    assert "Requirement Compliance Index (RCI) Report" in content
    assert "User Authentication" in content


def test_cli_missing_requirements_file_errors(capsys):
    exit_code = main(["review", "--requirements", "does/not/exist.md", "--source", "."])
    assert exit_code == 2


def test_cli_gap_analysis_end_to_end(tmp_path):
    output_path = tmp_path / "gap-report.md"
    exit_code = main(
        [
            "gap-analysis",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    content = output_path.read_text()
    assert "# Requirements Gap Analysis Report" in content
    assert "User Authentication" in content
    assert "Mandatory Information for Test-Case Generation" in content


def test_cli_gap_analysis_json_format(tmp_path):
    output_path = tmp_path / "gap-report.json"
    exit_code = main(
        [
            "gap-analysis",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--output",
            str(output_path),
            "--format",
            "json",
        ]
    )

    assert exit_code == 0
    content = output_path.read_text()
    assert '"requirements_source"' in content
    assert '"test_data_requirements"' in content


def test_cli_gap_analysis_missing_requirements_file_errors():
    exit_code = main(["gap-analysis", "--requirements", "does/not/exist.md"])
    assert exit_code == 2


def test_cli_generate_test_cases_markdown(tmp_path):
    output_path = tmp_path / "test-cases.md"
    exit_code = main(
        [
            "generate-test-cases",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    content = output_path.read_text()
    assert "# Generated Test Cases" in content
    assert "TC-F1-1" in content


def test_cli_generate_test_cases_csv(tmp_path):
    output_path = tmp_path / "test-cases.csv"
    exit_code = main(
        [
            "generate-test-cases",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--output",
            str(output_path),
            "--format",
            "csv",
        ]
    )

    assert exit_code == 0
    content = output_path.read_text()
    assert content.startswith("ID,Feature,Criterion")


def test_cli_generate_test_cases_binary_format_requires_output():
    exit_code = main(
        [
            "generate-test-cases",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--format",
            "pdf",
        ]
    )
    assert exit_code == 2


def test_cli_fail_below_threshold(tmp_path):
    exit_code = main(
        [
            "review",
            "--requirements",
            str(EXAMPLES / "PRD_example.md"),
            "--source",
            str(EXAMPLES / "sample_app"),
            "--output",
            str(tmp_path / "report.md"),
            "--fail-below",
            "0.99",
        ]
    )
    assert exit_code == 1


def test_cli_release_gap_analysis_end_to_end(tmp_path):
    output_path = tmp_path / "release-gap-report.md"
    exit_code = main(
        [
            "release-gap-analysis",
            "--user-stories",
            str(EXAMPLES / "release_24_user_stories.md"),
            "--release-notes",
            str(EXAMPLES / "release_24_development_notes.md"),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    content = output_path.read_text()
    assert "# Release Gap Analysis Report" in content
    assert "**Validation Status:** PASSED" in content
    assert "GAP-001" in content
    assert "R&D confirmation" in content


def test_cli_release_gap_analysis_returns_nonzero_on_release_mismatch(tmp_path):
    stories = tmp_path / "stories.md"
    notes = tmp_path / "notes.md"
    output = tmp_path / "report.json"
    stories.write_text("Release 24\nJIRA-1\nAs a user, I can log in.")
    notes.write_text("Release 23\n- Login")

    exit_code = main(
        [
            "release-gap-analysis",
            "--user-stories",
            str(stories),
            "--release-notes",
            str(notes),
            "--format",
            "json",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert '"validation_status": "FAILED"' in output.read_text()
