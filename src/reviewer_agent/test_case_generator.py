"""Generates draft test cases (with test data) from a
:class:`~reviewer_agent.gap_models.GapAnalysisReport`.

This is the last step of the requested workflow: *Requirements docs ->
user-story gap analysis -> design gaps -> gap analysis report -> mandatory
information to generate test cases with test data*. For every acceptance
criterion that already has enough information (see
:mod:`reviewer_agent.gap_analysis`), a positive test case (and, where
implied, a negative/boundary counterpart) is drafted with concrete test
data. Criteria that are missing mandatory information instead produce a
test case stub flagged ``is_ready=False`` with the specific open questions
that need to be answered before test data can be filled in.
"""

from __future__ import annotations

import re

from .gap_models import FeatureGapAnalysis, GapAnalysisReport, TestDataRequirement
from .models import Feature
from .test_case_models import Priority, TestCase, TestCaseSuite, TestCaseType, TestDataRow

_ROLE_RE = re.compile(r"\bas an? ([^,]+),", re.IGNORECASE)
_INVALID_TERMS = {"invalid", "incorrect", "reject", "rejected", "fail", "failure", "denied", "cannot", "must not"}
_HIGH_PRIORITY_TERMS = {
    "security", "password", "auth", "token", "encrypt", "must not", "cannot",
    "unauthorized", "permission", "pii",
}


def _extract_role(description: str) -> str:
    m = _ROLE_RE.search(description)
    return m.group(1).strip() if m else "user"


def _primary_type(criterion_text: str) -> TestCaseType:
    lowered = criterion_text.lower()
    if any(term in lowered for term in _INVALID_TERMS):
        return TestCaseType.NEGATIVE
    return TestCaseType.POSITIVE


def _priority_for(criterion_text: str) -> Priority:
    lowered = criterion_text.lower()
    if any(term in lowered for term in _HIGH_PRIORITY_TERMS):
        return Priority.HIGH
    if "must" in lowered:
        return Priority.MEDIUM
    return Priority.MEDIUM


def _build_test_data(data_fields: list[str]) -> list[TestDataRow]:
    rows: list[TestDataRow] = []
    for f in data_fields:
        if f.startswith('"') and f.endswith('"'):
            rows.append(TestDataRow(field="value", value=f.strip('"')))
        else:
            rows.append(TestDataRow(field=f, value=f"<{f} test value>"))
    return rows or [TestDataRow(field="(none identified)", value="<add representative test data here>")]


def _steps_for(criterion_text: str, test_type: TestCaseType) -> list[str]:
    steps = ["Set up the preconditions and test data listed below."]
    if test_type == TestCaseType.NEGATIVE:
        steps.append(f"Attempt the action using the invalid/edge-case test data: '{criterion_text}'.")
    elif test_type == TestCaseType.BOUNDARY:
        steps.append(f"Attempt the action using boundary-value test data (minimum, maximum, and just-outside-range values) for: '{criterion_text}'.")
    else:
        steps.append(f"Perform the action described by the criterion: '{criterion_text}'.")
    steps.append("Observe and record the system's actual response/state.")
    return steps


def _expected_result_for(criterion_text: str, test_type: TestCaseType) -> str:
    if test_type == TestCaseType.NEGATIVE:
        return f"The system correctly rejects/handles the invalid input as described: {criterion_text}"
    if test_type == TestCaseType.BOUNDARY:
        return f"The system correctly handles values at and just beyond the boundary, consistent with: {criterion_text}"
    return f"The system behaves exactly as described: {criterion_text}"


def _preconditions_for(feature: Feature) -> list[str]:
    role = _extract_role(feature.description)
    return [f"A {role} account/context exists and the '{feature.title}' feature area is reachable."]


def generate_test_cases_for_requirement(
    feature: Feature, req: TestDataRequirement, start_index: int
) -> list[TestCase]:
    """Generate the test case(s) implied by a single acceptance criterion's
    :class:`TestDataRequirement`, returning them in generation order."""

    cases: list[TestCase] = []
    counter = start_index

    primary_type = _primary_type(req.criterion_text)
    cases.append(
        TestCase(
            id=f"TC-{feature.id}-{counter}",
            feature_id=feature.id,
            feature_title=feature.title,
            criterion_id=req.criterion_id,
            criterion_text=req.criterion_text,
            title=f"Verify: {req.criterion_text}",
            type=primary_type,
            priority=_priority_for(req.criterion_text),
            preconditions=_preconditions_for(feature),
            steps=_steps_for(req.criterion_text, primary_type),
            test_data=_build_test_data(req.data_fields),
            expected_result=_expected_result_for(req.criterion_text, primary_type),
            is_ready=not req.missing_info,
            open_questions=list(req.missing_info),
        )
    )

    missing_lower = " ".join(req.missing_info).lower()

    if "valid/success case is described" in missing_lower:
        counter += 1
        cases.append(_stub_case(feature, req, counter, TestCaseType.NEGATIVE, "the invalid/failure"))
    elif "invalid/failure case is described" in missing_lower:
        counter += 1
        cases.append(_stub_case(feature, req, counter, TestCaseType.POSITIVE, "the valid/success"))

    if "boundary values" in missing_lower:
        counter += 1
        cases.append(_stub_case(feature, req, counter, TestCaseType.BOUNDARY, "the boundary"))

    return cases


def _stub_case(
    feature: Feature,
    req: TestDataRequirement,
    counter: int,
    test_type: TestCaseType,
    missing_scenario_label: str,
) -> TestCase:
    return TestCase(
        id=f"TC-{feature.id}-{counter}",
        feature_id=feature.id,
        feature_title=feature.title,
        criterion_id=req.criterion_id,
        criterion_text=req.criterion_text,
        title=f"[Needs clarification] {test_type.value} counterpart for: {req.criterion_text}",
        type=test_type,
        priority=_priority_for(req.criterion_text),
        preconditions=_preconditions_for(feature),
        steps=_steps_for(req.criterion_text, test_type),
        test_data=[TestDataRow(field="(unspecified)", value="<awaiting requirements clarification>")],
        expected_result="Not specified in the requirements document.",
        is_ready=False,
        open_questions=[
            f"The requirements document does not specify {missing_scenario_label} test data/expected "
            f"behavior for '{req.criterion_id}'; confirm with the requirements author before automating."
        ],
    )


def generate_test_cases_for_feature(feature_analysis: FeatureGapAnalysis) -> list[TestCase]:
    cases: list[TestCase] = []
    counter = 0
    for req in feature_analysis.test_data_requirements:
        counter += 1
        generated = generate_test_cases_for_requirement(feature_analysis.feature, req, counter)
        cases.extend(generated)
        counter += len(generated) - 1
    return cases


def generate_test_case_suite(gap_report: GapAnalysisReport) -> TestCaseSuite:
    """Generate the full :class:`TestCaseSuite` for every feature in a
    :class:`GapAnalysisReport`."""

    cases: list[TestCase] = []
    for fa in gap_report.feature_analyses:
        cases.extend(generate_test_cases_for_feature(fa))
    return TestCaseSuite(requirements_source=gap_report.requirements_source, test_cases=cases)
