"""Data structures for generated test cases (with test data), derived from a
:class:`~reviewer_agent.gap_models.GapAnalysisReport`."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TestCaseType(str, Enum):
    __test__ = False  # not a pytest test class -- this models a QA test case's type

    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    BOUNDARY = "Boundary"


class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class TestDataRow:
    """One row of test data (field -> value) for a test case."""

    field: str
    value: str


@dataclass
class TestCase:
    """A single generated test case, with test data, ready to be handed to
    a QA engineer or automation framework -- or flagged as needing more
    information from the requirements author first."""

    __test__ = False  # not a pytest test class -- this models a QA test case

    id: str
    feature_id: str
    feature_title: str
    criterion_id: str
    criterion_text: str
    title: str
    type: TestCaseType
    priority: Priority
    preconditions: list[str]
    steps: list[str]
    test_data: list[TestDataRow]
    expected_result: str
    is_ready: bool
    open_questions: list[str] = field(default_factory=list)


@dataclass
class TestCaseSuite:
    """The full set of generated test cases for a requirements document."""

    __test__ = False  # not a pytest test class -- this models a suite of QA test cases

    requirements_source: str
    test_cases: list[TestCase] = field(default_factory=list)

    @property
    def ready_count(self) -> int:
        return sum(1 for tc in self.test_cases if tc.is_ready)

    @property
    def readiness_score(self) -> float:
        if not self.test_cases:
            return 0.0
        return self.ready_count / len(self.test_cases)
