"""Small text-processing helpers used by the matcher and heuristic analyzer.

Kept dependency-free (no NLP libraries) so the tool works offline out of the
box; an optional LLM backend (see ``llm_client.py``) can be plugged in for
higher-quality matching/analysis when an API key is available.
"""

from __future__ import annotations

import re

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "to",
    "of", "in", "on", "at", "by", "with", "as", "is", "are", "was", "were",
    "be", "been", "being", "this", "that", "these", "those", "it", "its",
    "so", "so that", "i", "we", "user", "users", "should", "must", "can",
    "will", "shall", "would", "could", "when", "where", "which", "who",
    "whom", "into", "from", "up", "down", "out", "about", "than", "also",
    "not", "no", "do", "does", "did", "has", "have", "had", "system",
    "story", "feature", "requirement", "requirements", "given", "and",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]{1,}")


def tokenize(text: str) -> list[str]:
    """Split *text* into lowercase word tokens, also splitting camelCase and
    snake_case identifiers so that code and prose keywords line up."""

    tokens: list[str] = []
    for raw in _WORD_RE.findall(text):
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw).replace("_", " ").split()
        tokens.extend(p.lower() for p in parts if p)
    return tokens


def extract_keywords(text: str, min_len: int = 3) -> set[str]:
    """Return the set of meaningful keywords in *text* (stopwords removed)."""

    return {
        t
        for t in tokenize(text)
        if len(t) >= min_len and t not in _STOPWORDS
    }


def keyword_overlap_score(a: set[str], b: set[str]) -> float:
    """Jaccard-style overlap score biased towards coverage of *a* by *b*.

    Returns a value in ``[0, 1]`` representing how much of the "requirement"
    keyword set ``a`` is covered by the "code" keyword set ``b``.
    """

    if not a:
        return 0.0
    return len(a & b) / len(a)


def find_matching_lines(text: str, keywords: set[str], max_lines: int = 5) -> list[tuple[int, str]]:
    """Return up to *max_lines* (1-indexed line number, line text) pairs from
    *text* whose tokens intersect *keywords*."""

    matches: list[tuple[int, str]] = []
    if not keywords:
        return matches
    for idx, line in enumerate(text.splitlines(), start=1):
        line_tokens = set(tokenize(line))
        if line_tokens & keywords:
            matches.append((idx, line.strip()))
            if len(matches) >= max_lines:
                break
    return matches
