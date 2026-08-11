"""Analyzes parsed requirements (:class:`~reviewer_agent.models.Feature`
objects) to produce a **Gap Analysis** covering three angles:

1. **User story gaps** -- missing role/goal/benefit, missing or vague
   acceptance criteria, missing negative/error-handling scenarios.
2. **Design gaps** -- non-functional requirement categories (security,
   performance, validation, error handling, UI/UX, integration,
   reliability) that aren't mentioned anywhere for a feature/document.
3. **Test data requirements** -- for every acceptance criterion, the data
   fields it implies plus a checklist of the mandatory information
   (example values, formats, boundaries, valid/invalid cases) still needed
   before test cases with concrete test data can be generated from it.

This is a heuristic, offline, dependency-free first pass -- like the rest of
this tool, it's meant to focus a human reviewer's attention, not replace
one. See the README for how it fits into a broader gap-analysis workflow.
"""

from __future__ import annotations

import re

from .gap_models import (
    FeatureGapAnalysis,
    GapAnalysisReport,
    GapCategory,
    GapFinding,
    GapSeverity,
    TestDataRequirement,
)
from .models import AcceptanceCriterion, Feature
from .text_utils import tokenize

# --------------------------------------------------------------------------
# User story gap detection
# --------------------------------------------------------------------------

_STORY_ROLE_RE = re.compile(r"\bas an?\b", re.IGNORECASE)
_STORY_GOAL_RE = re.compile(r"\bi want\b|\bi need\b|\bi'd like\b", re.IGNORECASE)
_STORY_BENEFIT_RE = re.compile(r"\bso that\b|\bin order to\b|\bso i can\b", re.IGNORECASE)

_VAGUE_TERMS = {
    "tbd", "tba", "etc", "etc.", "somehow", "properly", "appropriately",
    "appropriate", "reasonable", "reasonably", "user-friendly", "friendly",
    "fast", "quickly", "easy", "easily", "good", "nice", "better", "efficient",
    "efficiently", "robust", "seamless", "seamlessly", "intuitive", "flexible",
    "and so on", "as needed", "if necessary", "if applicable",
}
_NEGATIVE_TERMS = {
    "error", "errors", "invalid", "fail", "fails", "failure", "reject",
    "rejects", "rejected", "cannot", "must not", "not allowed", "unauthorized",
    "denied", "deny", "exceeds", "exceed", "duplicate", "missing", "empty",
}
_BOUNDARY_TERMS = {
    "minimum", "maximum", "min", "max", "limit", "limits", "boundary",
    "at least", "at most", "no more than", "no less than", "between",
    "greater than", "less than", "exceed",
}


def _short_words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def analyze_user_story_gaps(feature: Feature) -> list[GapFinding]:
    findings: list[GapFinding] = []
    story_text = f"{feature.title} {feature.description}"

    has_role = bool(_STORY_ROLE_RE.search(story_text))
    has_goal = bool(_STORY_GOAL_RE.search(story_text))
    has_benefit = bool(_STORY_BENEFIT_RE.search(story_text))
    missing_parts = [
        name
        for present, name in (
            (has_role, "role ('As a ...')"),
            (has_goal, "goal ('I want ...')"),
            (has_benefit, "benefit/rationale ('so that ...')"),
        )
        if not present
    ]
    if missing_parts:
        findings.append(
            GapFinding(
                category=GapCategory.USER_STORY,
                severity=GapSeverity.MEDIUM if len(missing_parts) < 3 else GapSeverity.HIGH,
                description=(
                    f"'{feature.title}' does not follow the standard user-story format -- "
                    f"missing: {', '.join(missing_parts)}."
                ),
                recommendation=(
                    "Rewrite as 'As a <role>, I want <goal> so that <benefit>' so the "
                    "actor, capability, and business value are unambiguous."
                ),
            )
        )

    if not feature.acceptance_criteria:
        findings.append(
            GapFinding(
                category=GapCategory.USER_STORY,
                severity=GapSeverity.HIGH,
                description=f"'{feature.title}' has no acceptance criteria defined.",
                recommendation=(
                    "Add explicit, testable acceptance criteria (Given/When/Then or a "
                    "bullet list) -- without them this story cannot be reliably "
                    "implemented, reviewed, or turned into test cases."
                ),
            )
        )
        return findings

    for criterion in feature.acceptance_criteria:
        words = _short_words(criterion.text)
        if len(words) < 4:
            findings.append(
                GapFinding(
                    category=GapCategory.USER_STORY,
                    severity=GapSeverity.MEDIUM,
                    description=f"{criterion.id} ('{criterion.text}') is too short/terse to be testable.",
                    recommendation="Expand this criterion to state the trigger, expected behavior, and outcome explicitly.",
                    criterion_id=criterion.id,
                )
            )
        vague_hits = {w for w in words if w in _VAGUE_TERMS} | {
            term for term in _VAGUE_TERMS if " " in term and term in criterion.text.lower()
        }
        if vague_hits:
            findings.append(
                GapFinding(
                    category=GapCategory.USER_STORY,
                    severity=GapSeverity.MEDIUM,
                    description=(
                        f"{criterion.id} ('{criterion.text}') uses vague/subjective language "
                        f"({', '.join(sorted(vague_hits))}) that can't be objectively verified."
                    ),
                    recommendation="Replace subjective terms with a measurable condition (e.g. a specific value, threshold, format, or time limit).",
                    criterion_id=criterion.id,
                )
            )

    all_criteria_text = " ".join(c.text.lower() for c in feature.acceptance_criteria)
    if not any(term in all_criteria_text for term in _NEGATIVE_TERMS):
        findings.append(
            GapFinding(
                category=GapCategory.USER_STORY,
                severity=GapSeverity.HIGH,
                description=(
                    f"'{feature.title}' only describes happy-path behavior -- no acceptance "
                    "criteria cover invalid input, errors, or rejected/denied cases."
                ),
                recommendation="Add acceptance criteria for error handling and negative scenarios (invalid input, unauthorized access, failures, duplicates, etc.).",
            )
        )

    return findings


# --------------------------------------------------------------------------
# Design gap detection (non-functional requirement coverage)
# --------------------------------------------------------------------------

_DESIGN_CATEGORIES: dict[str, set[str]] = {
    "Security & Access Control": {
        "security", "auth", "authentication", "authorization", "encrypt",
        "encrypted", "encryption", "permission", "permissions", "role",
        "roles", "access control", "token", "pii", "sensitive", "compliance",
        "gdpr", "audit",
    },
    "Performance & Scalability": {
        "performance", "latency", "response time", "throughput", "load",
        "concurrent", "concurrency", "scalab", "scale", "capacity", "sla",
    },
    "Data Validation & Formats": {
        "validate", "validation", "format", "constraint", "required field",
        "unique", "length", "range", "pattern", "schema", "mandatory field",
    },
    "Error Handling & Recovery": {
        "error", "exception", "retry", "fallback", "timeout", "rollback",
        "recover", "recovery", "graceful",
    },
    "UI/UX & Accessibility": {
        "ui", "ux", "accessibility", "responsive", "layout", "screen",
        "usability", "wcag", "contrast",
    },
    "Integration & Interfaces": {
        "api", "integration", "third-party", "webhook", "endpoint",
        "interface", "external system", "sync",
    },
    "Reliability & Availability": {
        "availability", "uptime", "backup", "disaster recovery", "failover",
        "redundan", "reliability",
    },
}


def _mentions_category(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def analyze_design_gaps(feature: Feature) -> list[GapFinding]:
    text = " ".join(
        [feature.title, feature.description] + [c.text for c in feature.acceptance_criteria]
    )
    findings: list[GapFinding] = []
    for category, keywords in _DESIGN_CATEGORIES.items():
        if not _mentions_category(text, keywords):
            findings.append(
                GapFinding(
                    category=GapCategory.DESIGN,
                    severity=GapSeverity.LOW,
                    description=f"'{feature.title}' has no {category.lower()} requirements specified.",
                    recommendation=f"Confirm whether {category.lower()} requirements apply to this feature; if so, document them explicitly.",
                )
            )
    return findings


def analyze_document_level_design_gaps(features: list[Feature]) -> list[GapFinding]:
    """Cross-cutting design gaps evaluated across the *whole* document,
    since non-functional requirements are often intended to apply globally
    rather than being repeated per feature."""

    combined = " ".join(
        " ".join([f.title, f.description] + [c.text for c in f.acceptance_criteria])
        for f in features
    )
    findings: list[GapFinding] = []
    for category, keywords in _DESIGN_CATEGORIES.items():
        if not _mentions_category(combined, keywords):
            findings.append(
                GapFinding(
                    category=GapCategory.DESIGN,
                    severity=GapSeverity.MEDIUM,
                    description=f"No feature in the document mentions {category.lower()} at all.",
                    recommendation=f"Add a section (or per-feature notes) covering {category.lower()} requirements/NFRs, or explicitly state they are out of scope.",
                )
            )
    return findings


# --------------------------------------------------------------------------
# Test data requirements extraction
# --------------------------------------------------------------------------

_QUOTED_RE = re.compile(r"[\"“]([^\"”]{1,60})[\"”]|'([^']{1,60})'")
_FIELD_HINT_WORDS = {
    "email", "password", "username", "name", "title", "date", "time",
    "amount", "price", "quantity", "status", "id", "identifier", "phone",
    "address", "token", "url", "code", "description", "category", "type",
    "role", "currency", "percentage", "duration", "timestamp", "file",
    "size", "format", "field",
}
_EXAMPLE_MARKERS_RE = re.compile(r"\b(e\.g\.|for example|such as|like)\b", re.IGNORECASE)
_FORMAT_MARKERS_RE = re.compile(
    r"\b(format|yyyy|mm/dd|iso ?8601|regex|pattern|[a-z]+@[a-z]+)\b", re.IGNORECASE
)
_NUMBER_RE = re.compile(r"\d")
_VALID_TERMS = {"valid", "success", "successful", "correct", "accepted"}
_INVALID_TERMS = {"invalid", "incorrect", "reject", "rejected", "fail", "error", "denied"}


def extract_data_fields(text: str) -> list[str]:
    """Best-effort extraction of the data fields/entities implied by a piece
    of criterion text (quoted literals plus known field-name keywords)."""

    fields: set[str] = set()
    for m in _QUOTED_RE.finditer(text):
        value = (m.group(1) or m.group(2) or "").strip()
        if value:
            fields.add(f'"{value}"')

    tokens = tokenize(text)
    for token in tokens:
        if token in _FIELD_HINT_WORDS:
            fields.add(token)

    return sorted(fields)


def _missing_test_data_info(criterion: AcceptanceCriterion) -> list[str]:
    text = criterion.text
    lowered = text.lower()
    missing: list[str] = []

    has_example = bool(_EXAMPLE_MARKERS_RE.search(text)) or bool(_QUOTED_RE.search(text))
    has_number = bool(_NUMBER_RE.search(text))
    if not has_example and not has_number:
        missing.append("No concrete example value is given (e.g. a sample input/output).")

    mentions_size_or_time = any(
        term in lowered for term in ("length", "size", "amount", "date", "time", "age", "quantity", "limit")
    )
    has_boundary = any(term in lowered for term in _BOUNDARY_TERMS) or has_number
    if mentions_size_or_time and not has_boundary:
        missing.append("Boundary values (minimum/maximum/valid range) are not specified.")

    mentions_format_prone_field = any(
        term in lowered for term in ("date", "email", "phone", "id", "code", "currency", "url")
    )
    if mentions_format_prone_field and not _FORMAT_MARKERS_RE.search(text):
        missing.append("Expected data format/pattern is not specified.")

    has_valid = any(term in lowered for term in _VALID_TERMS)
    has_invalid = any(term in lowered for term in _INVALID_TERMS)
    if has_valid and not has_invalid:
        missing.append("Only the valid/success case is described; the corresponding invalid/failure test data is not specified.")
    elif has_invalid and not has_valid:
        missing.append("Only the invalid/failure case is described; the corresponding valid/success test data is not specified.")

    return missing


def analyze_test_data_requirements(feature: Feature) -> list[TestDataRequirement]:
    requirements: list[TestDataRequirement] = []
    for criterion in feature.acceptance_criteria:
        requirements.append(
            TestDataRequirement(
                criterion_id=criterion.id,
                criterion_text=criterion.text,
                data_fields=extract_data_fields(criterion.text),
                missing_info=_missing_test_data_info(criterion),
            )
        )
    return requirements


# --------------------------------------------------------------------------
# Top-level entry point
# --------------------------------------------------------------------------


def analyze_feature(feature: Feature) -> FeatureGapAnalysis:
    return FeatureGapAnalysis(
        feature=feature,
        user_story_gaps=analyze_user_story_gaps(feature),
        design_gaps=analyze_design_gaps(feature),
        test_data_requirements=analyze_test_data_requirements(feature),
    )


def run_gap_analysis(features: list[Feature], requirements_source: str) -> GapAnalysisReport:
    """Run the full gap analysis pipeline over every parsed feature/user
    story, returning a complete :class:`GapAnalysisReport`."""

    feature_analyses = [analyze_feature(f) for f in features]
    return GapAnalysisReport(
        requirements_source=requirements_source,
        feature_analyses=feature_analyses,
        document_level_design_gaps=analyze_document_level_design_gaps(features),
    )
