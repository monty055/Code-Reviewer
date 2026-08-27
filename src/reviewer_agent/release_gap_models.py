"""Data structures for comparing release-scoped user stories with release notes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReleaseValidationStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class ReleaseItemStatus(str, Enum):
    COVERED = "Covered"
    PARTIALLY_COVERED = "Partially Covered"
    MISSING = "Missing"
    CONTRADICTORY = "Contradictory"
    NEEDS_CLARIFICATION = "Needs Clarification"


class ReleaseGapCategory(str, Enum):
    SCOPE = "Scope Gap"
    OUT_OF_SCOPE = "Out-of-Scope Gap"
    DEPENDENCY = "Dependency Gap"
    THIRD_PARTY = "Third-Party Gap"
    API_DEPENDENCY = "API Dependency Gap"
    UI_AVAILABILITY = "UI Availability Gap"
    E2E_VALIDATION = "E2E Validation Gap"
    CREDENTIAL = "Credential Gap"
    CONFIGURATION = "Configuration Gap"
    KNOWN_LIMITATION = "Known Limitation Gap"
    PENDING_DECISION = "Pending Decision Gap"
    PARTIAL_IMPLEMENTATION = "Partial Implementation Gap"
    VALIDATION_LIMITATION = "Validation Limitation Gap"


@dataclass(frozen=True)
class ReleaseStory:
    ticket: str
    feature: str
    text: str


@dataclass(frozen=True)
class StoryInformationItem:
    ticket: str
    feature: str
    information_type: str
    detail: str
    source_evidence: str
    category: ReleaseGapCategory
    unclear: bool = False


@dataclass(frozen=True)
class ReleaseGapFinding:
    item: StoryInformationItem
    status: ReleaseItemStatus
    dev_release_note_evidence: str
    gap: str
    recommendation: str
    gap_id: str | None = None


@dataclass
class ReleaseGapReport:
    user_stories_release: str | None
    development_release_notes_release: str | None
    validation_status: ReleaseValidationStatus
    validation_message: str
    user_stories_source: str
    development_release_notes_source: str
    stories: list[ReleaseStory] = field(default_factory=list)
    findings: list[ReleaseGapFinding] = field(default_factory=list)

    @property
    def comparison_completed(self) -> bool:
        return self.validation_status is ReleaseValidationStatus.PASSED

    @property
    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in ReleaseItemStatus}
        for finding in self.findings:
            counts[finding.status.value] += 1
        return counts
