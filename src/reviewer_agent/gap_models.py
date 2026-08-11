"""Data structures for the requirements Gap Analysis + Test Data workflow.

These are intentionally separate from :mod:`reviewer_agent.models` (which
covers the source-code *review* workflow): gap analysis only looks at the
requirements document itself -- no source code is involved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import Feature


class GapSeverity(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @property
    def emoji(self) -> str:
        return {GapSeverity.HIGH: "🔴", GapSeverity.MEDIUM: "🟠", GapSeverity.LOW: "🟡"}[self]


class GapCategory(str, Enum):
    USER_STORY = "User Story Gap"
    DESIGN = "Design Gap"
    TEST_DATA = "Test Data Gap"


@dataclass
class GapFinding:
    """A single identified gap in the requirements document."""

    category: GapCategory
    severity: GapSeverity
    description: str
    recommendation: str
    criterion_id: str | None = None


@dataclass
class TestDataRequirement:
    """The mandatory information needed to generate test cases (with test
    data) for one acceptance criterion."""

    criterion_id: str
    criterion_text: str
    data_fields: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)

    @property
    def is_ready_for_test_case_generation(self) -> bool:
        return not self.missing_info


@dataclass
class FeatureGapAnalysis:
    """Gap analysis results for a single feature/user story."""

    feature: Feature
    user_story_gaps: list[GapFinding] = field(default_factory=list)
    design_gaps: list[GapFinding] = field(default_factory=list)
    test_data_requirements: list[TestDataRequirement] = field(default_factory=list)

    @property
    def all_gaps(self) -> list[GapFinding]:
        return self.user_story_gaps + self.design_gaps

    @property
    def readiness_score(self) -> float:
        """Fraction of acceptance criteria that already have enough
        information (data fields + concrete values/formats/boundaries) to
        generate test cases with test data, without further clarification."""

        if not self.test_data_requirements:
            return 0.0
        ready = sum(1 for t in self.test_data_requirements if t.is_ready_for_test_case_generation)
        return ready / len(self.test_data_requirements)


@dataclass
class GapAnalysisReport:
    """The full gap analysis output covering every feature in the
    requirements document."""

    requirements_source: str
    feature_analyses: list[FeatureGapAnalysis] = field(default_factory=list)
    document_level_design_gaps: list[GapFinding] = field(default_factory=list)

    @property
    def total_gap_count(self) -> int:
        return len(self.document_level_design_gaps) + sum(
            len(fa.all_gaps) for fa in self.feature_analyses
        )

    @property
    def overall_readiness_score(self) -> float:
        scores = [fa.readiness_score for fa in self.feature_analyses if fa.test_data_requirements]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
