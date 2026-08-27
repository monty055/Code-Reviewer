"""Evidence-based comparison of release user stories and development notes.

The analyzer is deliberately extractive and dependency-free.  It never adds
facts that are absent from the two supplied documents.
"""

from __future__ import annotations

import re

from .release_gap_models import (
    ReleaseGapCategory,
    ReleaseGapFinding,
    ReleaseGapReport,
    ReleaseItemStatus,
    ReleaseStory,
    ReleaseValidationStatus,
    StoryInformationItem,
)
from .text_utils import extract_keywords

NOT_FOUND = "Not found in the provided Development Release Notes."

_RELEASE_RE = re.compile(
    r"\brelease\s*:?\s*(?:release\s+)?([A-Za-z0-9][A-Za-z0-9._-]*)",
    re.IGNORECASE,
)
_TICKET_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?([A-Z][A-Z0-9]+-\d+)\b(?:\s*[:\-–—]\s*(.*))?\s*$"
)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s*")
_STORY_ACTION_RE = re.compile(
    r"\bI\s+(?:should(?:\s+be\s+able)?\s+to|want\s+to|need\s+to|can)\s+(.+?)(?:[.!?]|$)",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_NEGATIVE_RE = re.compile(
    r"\b(?:not|no|cannot|can't|unavailable|excluded|out[\s-]+of[\s-]+scope|"
    r"unsupported|disabled|doesn't|does not|won't|will not)\b",
    re.IGNORECASE,
)
_UNCLEAR_RE = re.compile(
    r"^(?:tbd|tba|unknown|unclear|not specified|to be confirmed|to be decided|n/?a)[.!]?$",
    re.IGNORECASE,
)

_MATCH_NOISE = {
    "able",
    "acceptance",
    "available",
    "criteria",
    "delivered",
    "development",
    "functionality",
    "included",
    "release",
    "required",
    "requires",
    "story",
    "support",
    "supported",
}


def _release_values(text: str) -> list[str]:
    values: list[str] = []
    for line in text.splitlines():
        matches = [m for m in _RELEASE_RE.findall(line) if m.lower() not in {"note", "notes"}]
        if matches:
            value = matches[-1].rstrip(".,:;")
            if value.lower() not in {v.lower() for v in values}:
                values.append(value)
    return values


def _release_label(values: list[str]) -> str | None:
    if not values:
        return None
    if len(values) > 1:
        return "Multiple releases: " + ", ".join(f"Release {v}" for v in values)
    return f"Release {values[0]}"


def _is_release_line(line: str) -> bool:
    return bool(_RELEASE_RE.search(line)) and not _TICKET_RE.match(line)


def parse_release_stories(text: str) -> list[ReleaseStory]:
    """Extract ticket-scoped stories without pulling in any other document."""

    lines = text.splitlines()
    blocks: list[tuple[str, str, list[str]]] = []
    ticket: str | None = None
    title = ""
    body: list[str] = []

    for line in lines:
        ticket_match = _TICKET_RE.match(line)
        if ticket_match:
            if ticket is not None:
                blocks.append((ticket, title, body))
            ticket = ticket_match.group(1)
            title = (ticket_match.group(2) or "").strip()
            body = []
        elif ticket is not None:
            body.append(line)

    if ticket is not None:
        blocks.append((ticket, title, body))

    if not blocks:
        blocks = _fallback_story_blocks(lines)

    stories: list[ReleaseStory] = []
    for ticket_id, heading, block_lines in blocks:
        cleaned = [
            _BULLET_PREFIX_RE.sub("", line).strip()
            for line in block_lines
            if line.strip() and not _is_release_line(line)
        ]
        story_text = "\n".join(cleaned).strip()
        if not story_text and heading:
            story_text = heading
        if not story_text:
            continue
        feature = _infer_feature(heading, story_text)
        stories.append(ReleaseStory(ticket=ticket_id, feature=feature, text=story_text))
    return stories


def _fallback_story_blocks(lines: list[str]) -> list[tuple[str, str, list[str]]]:
    blocks: list[tuple[str, str, list[str]]] = []
    title = ""
    body: list[str] = []
    counter = 1
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading and not _is_release_line(line):
            if body:
                blocks.append((f"STORY-{counter:03d}", title, body))
                counter += 1
            title = heading.group(1).strip()
            body = []
        elif not _is_release_line(line):
            body.append(line)
    if body or title:
        blocks.append((f"STORY-{counter:03d}", title, body))
    return blocks


def _infer_feature(heading: str, text: str) -> str:
    if heading:
        return heading.strip()
    match = _STORY_ACTION_RE.search(text)
    if match:
        return match.group(1).strip().rstrip(".")
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Untitled feature")
    return first_line[:100].rstrip(".")


def extract_story_information(story: ReleaseStory) -> list[StoryInformationItem]:
    """Normalize explicit story statements into independently comparable facts."""

    raw_segments = [segment.strip() for segment in _SENTENCE_RE.split(story.text) if segment.strip()]
    items: list[StoryInformationItem] = []
    seen: set[str] = set()

    action_match = _STORY_ACTION_RE.search(story.text)
    if action_match:
        evidence = action_match.group(0).strip()
        _append_item(items, seen, story, "Feature / Functionality", action_match.group(1).strip(), evidence)

    for segment in raw_segments:
        cleaned = _BULLET_PREFIX_RE.sub("", segment).strip()
        if (
            not cleaned
            or re.fullmatch(r"[-=_]+", cleaned)
            or (action_match and _STORY_ACTION_RE.search(cleaned))
        ):
            continue
        info_type, category = _classify_information(cleaned)
        key = _normalise(cleaned)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            StoryInformationItem(
                ticket=story.ticket,
                feature=story.feature,
                information_type=info_type,
                detail=cleaned,
                source_evidence=cleaned,
                category=category,
                unclear=bool(_UNCLEAR_RE.fullmatch(cleaned)),
            )
        )

    if not items:
        _append_item(items, seen, story, "Feature / Functionality", story.feature, story.text)
    return items


def _append_item(
    items: list[StoryInformationItem],
    seen: set[str],
    story: ReleaseStory,
    information_type: str,
    detail: str,
    evidence: str,
) -> None:
    key = _normalise(detail)
    if not key or key in seen:
        return
    seen.add(key)
    _, category = _classify_information(detail)
    items.append(
        StoryInformationItem(
            ticket=story.ticket,
            feature=story.feature,
            information_type=information_type,
            detail=detail,
            source_evidence=evidence,
            category=category,
        )
    )


def _classify_information(text: str) -> tuple[str, ReleaseGapCategory]:
    lowered = text.lower()
    rules = (
        (("out of scope", "excluded", "not included"), "Explicit Exclusion", ReleaseGapCategory.OUT_OF_SCOPE),
        (("credential", "login access", "api key", "token required"), "Required Access / Credentials", ReleaseGapCategory.CREDENTIAL),
        (("third-party", "third party", "external provider", "external integration"), "Third-Party Dependency", ReleaseGapCategory.THIRD_PARTY),
        (("api", "endpoint", "webhook"), "API Dependency", ReleaseGapCategory.API_DEPENDENCY),
        (("ui ", "frontend", "screen", "user interface"), "UI Availability", ReleaseGapCategory.UI_AVAILABILITY),
        (("end-to-end", "end to end", "e2e"), "E2E Validation Limitation", ReleaseGapCategory.E2E_VALIDATION),
        (("config", "environment variable", "feature flag", "setting"), "Configuration", ReleaseGapCategory.CONFIGURATION),
        (("pending", "subject to", "confirmation", "to be confirmed", "r&d", "decision"), "Pending Requirement / Decision", ReleaseGapCategory.PENDING_DECISION),
        (("partially", "partial implementation", "only implemented"), "Partial Implementation", ReleaseGapCategory.PARTIAL_IMPLEMENTATION),
        (("cannot validate", "unable to validate", "not testable", "qa cannot"), "Validation Limitation", ReleaseGapCategory.VALIDATION_LIMITATION),
        (("limitation", "unavailable", "not available", "cannot be completed", "maximum", "minimum", "limit"), "Known Limitation", ReleaseGapCategory.KNOWN_LIMITATION),
        (("depends on", "dependency", "requires backend", "requires frontend", "blocked by"), "Dependency", ReleaseGapCategory.DEPENDENCY),
    )
    for markers, information_type, category in rules:
        if any(marker in lowered for marker in markers):
            return information_type, category
    if re.search(r"\b(?:given|when|then|must|should|shall)\b", lowered):
        return "Acceptance Criterion / Business Rule", ReleaseGapCategory.SCOPE
    return "Feature / Functionality", ReleaseGapCategory.SCOPE


def _note_segments(text: str) -> list[str]:
    segments: list[str] = []
    for raw in _SENTENCE_RE.split(text):
        cleaned = _BULLET_PREFIX_RE.sub("", raw).strip()
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
        if not cleaned or _is_release_line(cleaned):
            continue
        if cleaned.endswith(":") and len(cleaned.split()) <= 5:
            continue
        segments.append(cleaned)
    return segments


def _keywords(text: str) -> set[str]:
    return {_stem(word) for word in extract_keywords(text) if word not in _MATCH_NOISE}


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 3:
            return word[: -len(suffix)]
    return word


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _match_item(item: StoryInformationItem, note_segments: list[str]) -> tuple[ReleaseItemStatus, str]:
    if item.unclear:
        return ReleaseItemStatus.NEEDS_CLARIFICATION, NOT_FOUND

    item_normal = _normalise(item.detail)
    item_keywords = _keywords(item.detail)
    best_segment = ""
    best_score = 0.0
    for segment in note_segments:
        segment_normal = _normalise(segment)
        segment_keywords = _keywords(segment)
        if item_normal and item_normal in segment_normal:
            score = 1.0
        elif item_keywords:
            score = len(item_keywords & segment_keywords) / len(item_keywords)
        else:
            score = 0.0
        if score > best_score:
            best_score = score
            best_segment = segment

    if best_segment and best_score >= 0.5:
        item_negative = bool(_NEGATIVE_RE.search(item.detail))
        note_negative = bool(_NEGATIVE_RE.search(best_segment))
        if item_negative != note_negative:
            return ReleaseItemStatus.CONTRADICTORY, best_segment
    if best_score >= 0.8:
        return ReleaseItemStatus.COVERED, best_segment
    if best_score >= 0.5:
        return ReleaseItemStatus.PARTIALLY_COVERED, best_segment
    return ReleaseItemStatus.MISSING, NOT_FOUND


def _finding_text(
    item: StoryInformationItem, status: ReleaseItemStatus
) -> tuple[str, str]:
    if status is ReleaseItemStatus.COVERED:
        return "No gap identified.", "No action required."
    if status is ReleaseItemStatus.NEEDS_CLARIFICATION:
        return "The User Story evidence is not specific enough for a reliable comparison.", "Clarify the User Story before updating the Development Release Notes."
    if status is ReleaseItemStatus.PARTIALLY_COVERED:
        return "The Development Release Notes mention related scope but omit part of the User Story detail.", f"Document the complete {item.information_type.lower()} from the User Story."
    if status is ReleaseItemStatus.CONTRADICTORY:
        return "The Development Release Notes conflict with the provided User Story evidence.", "Reconcile the conflicting statements and update the Development Release Notes."
    return f"The {item.information_type.lower()} is not documented in the provided Development Release Notes.", f"Add the User Story's {item.information_type.lower()} to the Development Release Notes."


def analyze_release_gap(
    user_stories_text: str,
    development_release_notes_text: str,
    *,
    user_stories_source: str = "User Stories",
    development_release_notes_source: str = "Development Release Notes",
) -> ReleaseGapReport:
    """Validate release scope, then compare only explicit facts from both inputs."""

    story_releases = _release_values(user_stories_text)
    note_releases = _release_values(development_release_notes_text)
    story_label = _release_label(story_releases)
    note_label = _release_label(note_releases)

    validation_error = None
    if len(story_releases) != 1:
        validation_error = "The User Stories input must identify exactly one release."
    elif len(note_releases) != 1:
        validation_error = "The Development Release Notes input must identify exactly one release."
    elif story_releases[0].lower() != note_releases[0].lower():
        validation_error = (
            "Comparison cannot be performed because both inputs do not belong to the same release."
        )

    if validation_error:
        return ReleaseGapReport(
            user_stories_release=story_label,
            development_release_notes_release=note_label,
            validation_status=ReleaseValidationStatus.FAILED,
            validation_message=validation_error,
            user_stories_source=user_stories_source,
            development_release_notes_source=development_release_notes_source,
        )

    stories = parse_release_stories(user_stories_text)
    note_segments = _note_segments(development_release_notes_text)
    findings: list[ReleaseGapFinding] = []
    gap_number = 1
    for story in stories:
        for item in extract_story_information(story):
            status, note_evidence = _match_item(item, note_segments)
            gap, recommendation = _finding_text(item, status)
            gap_id = None
            if status is not ReleaseItemStatus.COVERED:
                gap_id = f"GAP-{gap_number:03d}"
                gap_number += 1
            findings.append(
                ReleaseGapFinding(
                    item=item,
                    status=status,
                    dev_release_note_evidence=note_evidence,
                    gap=gap,
                    recommendation=recommendation,
                    gap_id=gap_id,
                )
            )

    return ReleaseGapReport(
        user_stories_release=story_label,
        development_release_notes_release=note_label,
        validation_status=ReleaseValidationStatus.PASSED,
        validation_message="Both inputs identify the same release.",
        user_stories_source=user_stories_source,
        development_release_notes_source=development_release_notes_source,
        stories=stories,
        findings=findings,
    )
