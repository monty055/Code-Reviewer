from reviewer_agent.release_gap_analyzer import (
    NOT_FOUND,
    analyze_release_gap,
    extract_story_information,
    parse_release_stories,
)
from reviewer_agent.release_gap_models import (
    ReleaseGapCategory,
    ReleaseItemStatus,
    ReleaseValidationStatus,
)


USER_STORIES = """Release: Release 24

JIRA-101
As a user, I should be able to upload an image.

Supported formats and maximum file size are subject to R&D confirmation.

---

JIRA-102
As an affiliate, I should be able to generate an affiliate link.

---

JIRA-103
As a user, I should complete event registration and payment.
"""

RELEASE_NOTES = """Release 24

Included:
- Image upload functionality
- Affiliate functionality
- Event registration

Known Limitations:
- None specified
"""


def test_release_mismatch_stops_comparison():
    report = analyze_release_gap(USER_STORIES, RELEASE_NOTES.replace("Release 24", "Release 23"))

    assert report.validation_status is ReleaseValidationStatus.FAILED
    assert not report.comparison_completed
    assert report.findings == []
    assert report.user_stories_release == "Release 24"
    assert report.development_release_notes_release == "Release 23"


def test_missing_or_ambiguous_release_stops_comparison():
    report = analyze_release_gap("JIRA-1\nAs a user, I can log in.", RELEASE_NOTES)

    assert report.validation_status is ReleaseValidationStatus.FAILED
    assert "exactly one release" in report.validation_message


def test_parser_keeps_ticket_scope_and_extracts_only_explicit_facts():
    stories = parse_release_stories(USER_STORIES)

    assert [story.ticket for story in stories] == ["JIRA-101", "JIRA-102", "JIRA-103"]
    first_items = extract_story_information(stories[0])
    assert len(first_items) == 2
    assert first_items[0].detail == "upload an image"
    assert first_items[1].source_evidence == (
        "Supported formats and maximum file size are subject to R&D confirmation."
    )
    assert first_items[1].category is ReleaseGapCategory.PENDING_DECISION


def test_example_analysis_is_evidence_based():
    report = analyze_release_gap(USER_STORIES, RELEASE_NOTES)

    assert report.validation_status is ReleaseValidationStatus.PASSED
    assert len(report.stories) == 3

    image_feature = next(
        finding
        for finding in report.findings
        if finding.item.ticket == "JIRA-101"
        and finding.item.information_type == "Feature / Functionality"
    )
    assert image_feature.status is ReleaseItemStatus.COVERED
    assert image_feature.dev_release_note_evidence == "Image upload functionality"

    pending_decision = next(
        finding
        for finding in report.findings
        if finding.item.category is ReleaseGapCategory.PENDING_DECISION
    )
    assert pending_decision.status is ReleaseItemStatus.MISSING
    assert pending_decision.dev_release_note_evidence == NOT_FOUND
    assert pending_decision.gap_id == "GAP-001"

    affiliate = next(
        finding for finding in report.findings if finding.item.ticket == "JIRA-102"
    )
    assert affiliate.status is ReleaseItemStatus.PARTIALLY_COVERED
    assert affiliate.dev_release_note_evidence == "Affiliate functionality"

    event_payment = next(
        finding for finding in report.findings if finding.item.ticket == "JIRA-103"
    )
    assert event_payment.item.detail == "complete event registration and payment"
    assert event_payment.status is ReleaseItemStatus.PARTIALLY_COVERED

    # The source says nothing about an API-only affiliate flow, so the agent
    # must not invent that finding from the proposed example output.
    assert not any(
        finding.item.category is ReleaseGapCategory.API_DEPENDENCY
        for finding in report.findings
    )


def test_related_but_incomplete_note_is_partially_covered():
    stories = """Release 7
JIRA-7
As a user, I should complete event registration and payment.
"""
    notes = """Release 7
Included:
- Event registration
"""

    report = analyze_release_gap(stories, notes)

    assert report.findings[0].status is ReleaseItemStatus.PARTIALLY_COVERED
    assert report.findings[0].dev_release_note_evidence == "Event registration"


def test_explicit_conflict_is_contradictory():
    stories = """Release 8
JIRA-8
As a user, I should be able to upload images.
"""
    notes = """Release 8
- Image upload is not included.
"""

    report = analyze_release_gap(stories, notes)

    assert report.findings[0].status is ReleaseItemStatus.CONTRADICTORY


def test_standalone_tbd_is_needs_clarification():
    stories = """Release 9
JIRA-9
TBD
"""
    notes = """Release 9
Known Limitations:
- None specified
"""

    report = analyze_release_gap(stories, notes)

    assert report.findings[0].status is ReleaseItemStatus.NEEDS_CLARIFICATION
