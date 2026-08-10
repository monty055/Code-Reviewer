"""Matches requirement features to the source files most likely to
implement them, using lightweight keyword overlap scoring."""

from __future__ import annotations

from dataclasses import dataclass

from .models import CodeFile, Feature
from .text_utils import extract_keywords, tokenize


@dataclass
class FileMatch:
    file: CodeFile
    score: float


def match_feature_to_files(
    feature: Feature,
    files: list[CodeFile],
    top_k: int = 5,
    min_score: float = 0.02,
) -> list[FileMatch]:
    """Rank *files* by relevance to *feature* and return the top matches.

    The score combines:
      * keyword overlap between the feature text and file content
      * a bonus for filename tokens matching feature keywords (file/module
        names are a strong signal of "this implements that feature").
    """

    feature_keywords = feature.keywords()
    if not feature_keywords:
        return []

    scored: list[FileMatch] = []
    for f in files:
        file_keywords = f.keywords()
        overlap = len(feature_keywords & file_keywords)
        if overlap == 0:
            continue
        content_score = overlap / max(len(feature_keywords), 1)

        filename_tokens = set(tokenize(f.path))
        filename_overlap = len(feature_keywords & filename_tokens)
        filename_score = filename_overlap / max(len(feature_keywords), 1)

        score = content_score + 0.75 * filename_score
        if score >= min_score:
            scored.append(FileMatch(file=f, score=score))

    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:top_k]


def rank_all_features(
    features: list[Feature],
    files: list[CodeFile],
    top_k: int = 5,
    min_score: float = 0.02,
) -> dict[str, list[FileMatch]]:
    """Convenience helper: match every feature against the file set."""

    return {
        feature.id: match_feature_to_files(feature, files, top_k=top_k, min_score=min_score)
        for feature in features
    }


def unmatched_files(
    files: list[CodeFile], matches_by_feature: dict[str, list[FileMatch]]
) -> list[str]:
    """Return the paths of files that were not matched to any feature."""

    matched_paths: set[str] = set()
    for matches in matches_by_feature.values():
        matched_paths.update(m.file.path for m in matches)
    return sorted(f.path for f in files if f.path not in matched_paths)
