"""Core data structures shared across the reviewer agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CriterionStatus(str, Enum):
    """Result of comparing one acceptance criterion against the codebase."""

    MET = "Met"
    PARTIALLY_MET = "Partially Met"
    NOT_MET = "Not Met"
    NEEDS_REVIEW = "Needs Manual Review"

    @property
    def emoji(self) -> str:
        return {
            CriterionStatus.MET: "✅",
            CriterionStatus.PARTIALLY_MET: "🟡",
            CriterionStatus.NOT_MET: "❌",
            CriterionStatus.NEEDS_REVIEW: "❓",
        }[self]


@dataclass
class AcceptanceCriterion:
    """A single, testable acceptance criterion belonging to a feature."""

    id: str
    text: str


@dataclass
class Feature:
    """A feature/user story extracted from the requirements document."""

    id: str
    title: str
    description: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = field(default_factory=list)
    raw_text: str = ""

    def keywords(self) -> set[str]:
        from .text_utils import extract_keywords

        text = " ".join(
            [self.title, self.description] + [ac.text for ac in self.acceptance_criteria]
        )
        return extract_keywords(text)


@dataclass
class CodeFile:
    """A single source file discovered while scanning the codebase."""

    path: str
    content: str

    @property
    def lines(self) -> list[str]:
        return self.content.splitlines()

    def keywords(self) -> set[str]:
        from .text_utils import extract_keywords

        return extract_keywords(self.content)


@dataclass
class Evidence:
    """A pointer to a specific location in the codebase supporting a verdict."""

    file: str
    line_number: int
    snippet: str


@dataclass
class CriterionResult:
    """The outcome of evaluating one acceptance criterion."""

    criterion: AcceptanceCriterion
    status: CriterionStatus
    confidence: float
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class FeatureReport:
    """Aggregated results for a single feature."""

    feature: Feature
    matched_files: list[str]
    criterion_results: list[CriterionResult]

    @property
    def coverage(self) -> float:
        if not self.criterion_results:
            return 0.0
        met = sum(
            1
            for r in self.criterion_results
            if r.status in (CriterionStatus.MET, CriterionStatus.PARTIALLY_MET)
        )
        return met / len(self.criterion_results)


@dataclass
class ReviewReport:
    """The full review output covering every feature in the requirements doc."""

    requirements_source: str
    codebase_source: str
    feature_reports: list[FeatureReport]
    unmatched_files: list[str] = field(default_factory=list)

    @property
    def overall_coverage(self) -> float:
        if not self.feature_reports:
            return 0.0
        return sum(f.coverage for f in self.feature_reports) / len(self.feature_reports)
