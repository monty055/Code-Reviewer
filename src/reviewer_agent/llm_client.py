"""Optional LLM backend used to improve criterion-level analysis quality.

The reviewer agent works fully offline using heuristic keyword matching
(see ``analyzer.py``). If an OpenAI-compatible API key is available, this
module can be used to ask a language model to judge each acceptance
criterion against the matched source code with higher precision.

This module has no hard dependency on the ``openai`` package: it is
imported lazily so the rest of the tool works without it installed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

SYSTEM_PROMPT = """You are a meticulous senior software engineer performing a \
source-code review against a product requirements document. For every \
acceptance criterion you are given, decide whether the provided source code \
satisfies it. Respond ONLY with strict JSON, matching this schema:

{
  "results": [
    {
      "criterion_id": "<id>",
      "status": "Met" | "Partially Met" | "Not Met" | "Needs Manual Review",
      "confidence": <float 0-1>,
      "rationale": "<one or two sentence justification>",
      "evidence_lines": [<line numbers relevant to your rationale, if any>]
    }
  ]
}

Be conservative: if the code does not clearly address a criterion, mark it \
"Not Met" or "Needs Manual Review" rather than guessing "Met".
"""


@dataclass
class LLMCriterionVerdict:
    criterion_id: str
    status: str
    confidence: float
    rationale: str
    evidence_lines: list[int]


class LLMUnavailableError(RuntimeError):
    """Raised when no usable LLM backend/credentials are configured."""


def is_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("REVIEWER_LLM_API_KEY"))


def evaluate_criteria_with_llm(
    feature_title: str,
    feature_description: str,
    criteria: list[tuple[str, str]],
    file_path: str,
    file_content: str,
    model: str | None = None,
) -> list[LLMCriterionVerdict]:
    """Ask the configured LLM to evaluate *criteria* (list of (id, text))
    against *file_content*. Raises :class:`LLMUnavailableError` if no
    backend is configured or the call fails."""

    if not is_configured():
        raise LLMUnavailableError("No LLM API key configured (set OPENAI_API_KEY).")

    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise LLMUnavailableError("The 'openai' package is not installed.") from exc

    numbered_content = "\n".join(
        f"{i + 1}: {line}" for i, line in enumerate(file_content.splitlines())
    )
    criteria_block = "\n".join(f"- [{cid}] {text}" for cid, text in criteria)

    user_prompt = f"""Feature: {feature_title}
Description: {feature_description}

Acceptance criteria to evaluate:
{criteria_block}

Source file: {file_path}
```
{numbered_content}
```
"""

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("REVIEWER_LLM_API_KEY"))
    model_name = model or os.environ.get("REVIEWER_LLM_MODEL", "gpt-4o-mini")

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
    except Exception as exc:  # pragma: no cover - network/SDK errors
        raise LLMUnavailableError(f"LLM call failed: {exc}") from exc

    verdicts = []
    for item in data.get("results", []):
        verdicts.append(
            LLMCriterionVerdict(
                criterion_id=str(item.get("criterion_id", "")),
                status=str(item.get("status", "Needs Manual Review")),
                confidence=float(item.get("confidence", 0.5)),
                rationale=str(item.get("rationale", "")),
                evidence_lines=[int(n) for n in item.get("evidence_lines", []) if str(n).isdigit()],
            )
        )
    return verdicts
