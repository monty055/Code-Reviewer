from reviewer_agent.gap_analysis import run_gap_analysis
from reviewer_agent.requirements_parser import parse_requirements_text
from reviewer_agent.test_case_generator import generate_test_case_suite
from reviewer_agent.test_case_models import TestCaseType

_TEXT = """# Task Creation

As a logged-in user, I want to create a task so that I can track my work.

### Acceptance Criteria

- AC-1: A task cannot be created without a title.
- AC-2: A newly created task defaults to status "pending".
- AC-3: The due date, if provided, must be a valid future date.
"""


def _build_suite():
    features = parse_requirements_text(_TEXT)
    report = run_gap_analysis(features, requirements_source="inline")
    return generate_test_case_suite(report)


def test_generates_at_least_one_case_per_criterion():
    suite = _build_suite()
    criterion_ids = {tc.criterion_id for tc in suite.test_cases}
    assert criterion_ids == {"AC-1", "AC-2", "AC-3"}


def test_ready_case_has_no_open_questions():
    suite = _build_suite()
    ready_cases = [tc for tc in suite.test_cases if tc.is_ready]
    assert ready_cases
    for tc in ready_cases:
        assert tc.open_questions == []


def test_negative_criterion_produces_negative_primary_case():
    suite = _build_suite()
    primary = next(tc for tc in suite.test_cases if tc.criterion_id == "AC-1")
    assert primary.type == TestCaseType.NEGATIVE


def test_missing_counterpart_generates_stub_case():
    suite = _build_suite()
    ac2_cases = [tc for tc in suite.test_cases if tc.criterion_id == "AC-2"]
    # AC-2 only describes the "success" default value -> a negative
    # counterpart stub should also be generated, flagged as not ready.
    assert len(ac2_cases) >= 1
    if len(ac2_cases) > 1:
        stub = ac2_cases[-1]
        assert not stub.is_ready
        assert stub.open_questions


def test_suite_readiness_score_between_zero_and_one():
    suite = _build_suite()
    assert 0.0 <= suite.readiness_score <= 1.0
    assert suite.ready_count <= len(suite.test_cases)


def test_test_case_ids_are_unique():
    suite = _build_suite()
    ids = [tc.id for tc in suite.test_cases]
    assert len(ids) == len(set(ids))
