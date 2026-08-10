"""Evaluates each acceptance criterion of a feature against its matched
source files, producing a :class:`~reviewer_agent.models.CriterionResult`
per criterion.

Two evaluation strategies are supported:

* **Heuristic** (default, offline): keyword-overlap scoring between the
  criterion text and the matched file's content/comments/identifiers.
* **LLM-assisted** (opt-in, requires ``OPENAI_API_KEY``): delegates the
  judgement to a language model for higher-quality, context-aware verdicts.
  Falls back to the heuristic strategy automatically if the LLM call fails.
"""

from __future__ import annotations

from .llm_client import LLMUnavailableError, evaluate_criteria_with_llm, is_configured
from .matcher import FileMatch, match_feature_to_files
from .models import (
    AcceptanceCriterion,
    CodeFile,
    CriterionResult,
    CriterionStatus,
    Evidence,
    Feature,
    FeatureReport,
    ReviewReport,
)
from .text_utils import extract_keywords, find_matching_lines, keyword_overlap_score

# Coverage thresholds for the heuristic strategy.
MET_THRESHOLD = 0.6
PARTIAL_THRESHOLD = 0.3


def evaluate_criterion_heuristic(
    criterion: AcceptanceCriterion, matched_files: list[CodeFile]
) -> CriterionResult:
    criterion_keywords = extract_keywords(criterion.text)

    best_score = 0.0
    best_file: CodeFile | None = None
    for f in matched_files:
        score = keyword_overlap_score(criterion_keywords, f.keywords())
        if score > best_score:
            best_score = score
            best_file = f

    if not matched_files or not criterion_keywords:
        return CriterionResult(
            criterion=criterion,
            status=CriterionStatus.NEEDS_REVIEW,
            confidence=0.0,
            rationale="No relevant source files were found for this feature; manual review needed.",
        )

    evidence: list[Evidence] = []
    if best_file is not None:
        for line_no, snippet in find_matching_lines(best_file.content, criterion_keywords):
            evidence.append(Evidence(file=best_file.path, line_number=line_no, snippet=snippet))

    if best_score >= MET_THRESHOLD:
        status = CriterionStatus.MET
        rationale = (
            f"Strong keyword overlap ({best_score:.0%}) between the criterion and "
            f"'{best_file.path}' suggests this is implemented."
        )
    elif best_score >= PARTIAL_THRESHOLD:
        status = CriterionStatus.PARTIALLY_MET
        rationale = (
            f"Some related terms ({best_score:.0%} overlap) were found in "
            f"'{best_file.path}', but full coverage could not be confirmed automatically."
        )
    else:
        status = CriterionStatus.NOT_MET
        rationale = (
            "No strong evidence of this criterion was found in the matched source files "
            f"(best overlap {best_score:.0%})."
        )

    return CriterionResult(
        criterion=criterion,
        status=status,
        confidence=round(best_score, 2),
        rationale=rationale,
        evidence=evidence,
    )


def evaluate_feature(
    feature: Feature,
    files: list[CodeFile],
    top_k: int = 5,
    min_score: float = 0.02,
    use_llm: bool = False,
) -> FeatureReport:
    matches: list[FileMatch] = match_feature_to_files(feature, files, top_k=top_k, min_score=min_score)
    matched_files = [m.file for m in matches]

    results: list[CriterionResult] = []
    if not feature.acceptance_criteria:
        return FeatureReport(feature=feature, matched_files=[f.path for f in matched_files], criterion_results=[])

    if use_llm and is_configured() and matched_files:
        results = _evaluate_with_llm_fallback(feature, matched_files)
    else:
        for criterion in feature.acceptance_criteria:
            results.append(evaluate_criterion_heuristic(criterion, matched_files))

    return FeatureReport(
        feature=feature,
        matched_files=[f.path for f in matched_files],
        criterion_results=results,
    )


def _evaluate_with_llm_fallback(feature: Feature, matched_files: list[CodeFile]) -> list[CriterionResult]:
    primary_file = matched_files[0]
    criteria_pairs = [(c.id, c.text) for c in feature.acceptance_criteria]
    try:
        verdicts = evaluate_criteria_with_llm(
            feature_title=feature.title,
            feature_description=feature.description,
            criteria=criteria_pairs,
            file_path=primary_file.path,
            file_content=primary_file.content,
        )
        verdicts_by_id = {v.criterion_id: v for v in verdicts}
    except LLMUnavailableError:
        return [evaluate_criterion_heuristic(c, matched_files) for c in feature.acceptance_criteria]

    results: list[CriterionResult] = []
    for criterion in feature.acceptance_criteria:
        verdict = verdicts_by_id.get(criterion.id)
        if verdict is None:
            results.append(evaluate_criterion_heuristic(criterion, matched_files))
            continue
        try:
            status = CriterionStatus(verdict.status)
        except ValueError:
            status = CriterionStatus.NEEDS_REVIEW
        lines = primary_file.lines
        evidence = [
            Evidence(
                file=primary_file.path,
                line_number=ln,
                snippet=lines[ln - 1].strip() if 0 < ln <= len(lines) else "",
            )
            for ln in verdict.evidence_lines
        ]
        results.append(
            CriterionResult(
                criterion=criterion,
                status=status,
                confidence=verdict.confidence,
                rationale=verdict.rationale,
                evidence=evidence,
            )
        )
    return results


def review(
    features: list[Feature],
    files: list[CodeFile],
    requirements_source: str,
    codebase_source: str,
    top_k: int = 5,
    min_score: float = 0.02,
    use_llm: bool = False,
) -> ReviewReport:
    """Run the full review: match every feature to files and evaluate every
    acceptance criterion, returning a complete :class:`ReviewReport`."""

    from .matcher import rank_all_features, unmatched_files

    matches_by_feature = rank_all_features(features, files, top_k=top_k, min_score=min_score)
    feature_reports = [
        evaluate_feature(feature, files, top_k=top_k, min_score=min_score, use_llm=use_llm)
        for feature in features
    ]
    return ReviewReport(
        requirements_source=requirements_source,
        codebase_source=codebase_source,
        feature_reports=feature_reports,
        unmatched_files=unmatched_files(files, matches_by_feature),
    )
