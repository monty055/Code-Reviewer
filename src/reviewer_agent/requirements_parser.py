"""Parses requirement documents (User Story / PRD / BRD) written in Markdown
or plain text into structured :class:`~reviewer_agent.models.Feature`
objects with their acceptance criteria.

The parser is intentionally forgiving: real-world PRDs/BRDs/user-story docs
vary a lot in formatting. It supports:

* ``# Feature`` / ``## Feature`` / ``### Feature`` headings as feature
  boundaries.
* Optional explicit "Acceptance Criteria" (or "Acceptance Criterion",
  "Definition of Done", "AC") sub-sections containing a bullet/numbered
  list.
* Inline criteria IDs such as ``AC-1:``, ``AC1.``, ``1)`` etc. When no ID is
  present, one is generated (``F{n}-AC{m}``).
* Falling back to treating every bullet under a feature as a criterion when
  no explicit acceptance-criteria heading exists.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import AcceptanceCriterion, Feature

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
_AC_HEADING_RE = re.compile(
    r"^(?:#{1,4}\s+)?\**\s*(acceptance criteria|acceptance criterion|"
    r"definition of done|dod|ac)\s*[:\**]*\s*$",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|AC[-\s]?\d+\s*[:.)-])\s*(.*\S)\s*$", re.IGNORECASE)
_AC_ID_PREFIX_RE = re.compile(r"^(AC[-\s]?\d+)\s*[:.)-]\s*(.*)$", re.IGNORECASE)


def parse_requirements_file(path: str) -> list[Feature]:
    """Read a requirements document from *path* and parse it into features."""

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_requirements_text(text, source_name=Path(path).name)


def parse_requirements_text(text: str, source_name: str = "requirements") -> list[Feature]:
    """Parse the raw *text* of a requirements document into a list of
    :class:`Feature` objects, in document order."""

    lines = text.splitlines()
    blocks = _split_into_feature_blocks(lines)

    features: list[Feature] = []
    for idx, (title, body_lines) in enumerate(blocks, start=1):
        feature_id = f"F{idx}"
        description, criteria_lines = _split_description_and_criteria(body_lines)
        criteria = _parse_criteria(criteria_lines, feature_id)
        features.append(
            Feature(
                id=feature_id,
                title=title or f"Untitled Feature {idx}",
                description=description.strip(),
                acceptance_criteria=criteria,
                raw_text="\n".join(body_lines),
            )
        )

    if len(features) > 1:
        # Drop empty "container" headings (e.g. a top-level document title
        # such as "# Product Requirements Document — X") that have neither a
        # description nor acceptance criteria of their own -- these aren't
        # real features, just document/section titles.
        features = [f for f in features if f.acceptance_criteria or f.description.strip()]
        features = _renumber_features(features)

    if not features and text.strip():
        # No headings at all: treat the whole document as a single feature.
        description, criteria_lines = _split_description_and_criteria(lines)
        criteria = _parse_criteria(criteria_lines, "F1")
        features.append(
            Feature(
                id="F1",
                title=source_name,
                description=description.strip(),
                acceptance_criteria=criteria,
                raw_text=text,
            )
        )

    return features


def _renumber_features(features: list[Feature]) -> list[Feature]:
    """Reassign sequential ``F{n}`` ids/criteria ids after features have been
    filtered out, so ids stay contiguous and easy to reference."""

    renumbered: list[Feature] = []
    for idx, feature in enumerate(features, start=1):
        new_id = f"F{idx}"
        new_criteria = []
        for c in feature.acceptance_criteria:
            if c.id.startswith(f"{feature.id}-AC"):
                new_criteria.append(AcceptanceCriterion(id=c.id.replace(feature.id, new_id, 1), text=c.text))
            else:
                new_criteria.append(c)
        renumbered.append(
            Feature(
                id=new_id,
                title=feature.title,
                description=feature.description,
                acceptance_criteria=new_criteria,
                raw_text=feature.raw_text,
            )
        )
    return renumbered


def _split_into_feature_blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split the document into ``(heading_title, body_lines)`` blocks using
    top-level headings as boundaries. If a heading's body is empty and it has
    a deeper sub-heading structure, that's fine -- callers just treat the
    body text as-is."""

    blocks: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_body: list[str] = []
    seen_heading = False

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            heading_text = _strip_heading_markup(m.group(2))
            if heading_text.lower() in {
                "acceptance criteria",
                "acceptance criterion",
                "definition of done",
                "dod",
            }:
                # Not a new feature -- part of the current feature's body.
                current_body.append(line)
                continue
            if seen_heading:
                blocks.append((current_title or "", current_body))
            current_title = heading_text
            current_body = []
            seen_heading = True
        else:
            current_body.append(line)

    if seen_heading:
        blocks.append((current_title or "", current_body))

    return blocks


def _strip_heading_markup(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^(feature|user story|story)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _split_description_and_criteria(body_lines: list[str]) -> tuple[str, list[str]]:
    """Given the body of a feature, separate free-form description text from
    the lines that belong to an explicit acceptance-criteria section."""

    ac_start = None
    for i, line in enumerate(body_lines):
        if _AC_HEADING_RE.match(line.strip()):
            ac_start = i
            break

    if ac_start is None:
        # No explicit AC section: use bullet lines anywhere in the body as
        # the criteria, and non-bullet lines as description.
        description_lines = [l for l in body_lines if not _BULLET_RE.match(l)]
        criteria_lines = [l for l in body_lines if _BULLET_RE.match(l)]
        return "\n".join(description_lines), criteria_lines

    description_lines = body_lines[:ac_start]
    criteria_lines = body_lines[ac_start + 1 :]
    # Stop the AC section at the next heading, if any (already handled by
    # block splitting for top-level headings, but sub-headings might remain).
    stop_at = len(criteria_lines)
    for i, line in enumerate(criteria_lines):
        if _HEADING_RE.match(line) and not _AC_HEADING_RE.match(line.strip()):
            stop_at = i
            break
    return "\n".join(description_lines), criteria_lines[:stop_at]


def _parse_criteria(criteria_lines: list[str], feature_id: str) -> list[AcceptanceCriterion]:
    criteria: list[AcceptanceCriterion] = []
    counter = 0
    for line in criteria_lines:
        m = _BULLET_RE.match(line)
        if not m:
            if line.strip() and criteria:
                # Continuation of the previous bullet (wrapped line).
                prev = criteria[-1]
                criteria[-1] = AcceptanceCriterion(prev.id, f"{prev.text} {line.strip()}")
            continue
        text = m.group(1).strip()
        id_match = _AC_ID_PREFIX_RE.match(text)
        if id_match:
            ac_id, text = id_match.group(1).upper().replace(" ", "-"), id_match.group(2).strip()
        else:
            counter += 1
            ac_id = f"{feature_id}-AC{counter}"
        if text:
            criteria.append(AcceptanceCriterion(id=ac_id, text=text))
    return criteria
