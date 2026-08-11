import csv
import io
import json

import pytest

from reviewer_agent.gap_analysis import run_gap_analysis
from reviewer_agent.requirements_parser import parse_requirements_text
from reviewer_agent.test_case_export import render_csv, render_docx, render_json, render_markdown, render_pdf
from reviewer_agent.test_case_generator import generate_test_case_suite

_TEXT = """# Task Creation

As a logged-in user, I want to create a task so that I can track my work.

### Acceptance Criteria

- AC-1: A task cannot be created without a title.
- AC-2: A newly created task defaults to status "pending".
"""


def _build_suite():
    features = parse_requirements_text(_TEXT)
    report = run_gap_analysis(features, requirements_source="inline")
    return generate_test_case_suite(report)


def test_render_markdown_includes_test_cases():
    suite = _build_suite()
    md = render_markdown(suite)
    assert "# Generated Test Cases" in md
    assert "TC-F1-1" in md
    assert "Test data:" in md


def test_render_json_round_trips():
    suite = _build_suite()
    payload = json.loads(render_json(suite))
    assert payload["requirements_source"] == "inline"
    assert len(payload["test_cases"]) == len(suite.test_cases)
    assert "is_ready" in payload["test_cases"][0]


def test_render_csv_has_header_and_one_row_per_case():
    suite = _build_suite()
    csv_text = render_csv(suite)
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert rows[0][0] == "ID"
    assert len(rows) - 1 == len(suite.test_cases)


def test_render_docx_produces_valid_zip_bytes():
    pytest.importorskip("docx")
    suite = _build_suite()
    data = render_docx(suite)
    assert data[:2] == b"PK"  # .docx is a zip archive
    assert len(data) > 100


def test_render_pdf_produces_pdf_bytes():
    pytest.importorskip("reportlab")
    suite = _build_suite()
    data = render_pdf(suite)
    assert data[:5] == b"%PDF-"
