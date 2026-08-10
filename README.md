# Code-Reviewer — Source Code Reviewer Agent

A source-code reviewer agent that compares a codebase against a requirements
document (User Story / PRD / BRD) and produces a **detailed report** listing,
for every feature, each of its acceptance criteria and whether the source
code satisfies it — with supporting evidence (matched files and line
numbers).

## Why

Manually cross-checking "did we actually build what the PRD asked for?" is
slow and error-prone. This tool automates the first pass: it parses your
requirements doc into features + acceptance criteria, finds the source files
most likely to implement each feature, and scores each criterion as:

| Status | Meaning |
|---|---|
| ✅ Met | Strong evidence the criterion is implemented |
| 🟡 Partially Met | Some evidence found, but not conclusive |
| ❌ Not Met | No evidence found in the matched source files |
| ❓ Needs Manual Review | No relevant source files were found at all |

The output is meant to be a **starting point for a human reviewer**, not a
final verdict — see [Limitations](#limitations) below.

## How it works

1. **Parse requirements** (`requirements_parser.py`) — reads a Markdown/text
   PRD, BRD, or user-story document and extracts a list of `Feature`s, each
   with a title, description, and a list of `AcceptanceCriterion`s. Supports
   explicit `### Acceptance Criteria` sections, `AC-1:`-style IDs, or plain
   bullet lists.
2. **Scan source code** (`code_scanner.py`) — recursively walks the source
   directory, skipping `.git`, `node_modules`, build artifacts, etc.
3. **Match features to files** (`matcher.py`) — scores every file against
   every feature using keyword overlap (identifiers, comments, filenames vs.
   feature/criteria text), returning the top-`k` candidate files per
   feature.
4. **Evaluate each acceptance criterion** (`analyzer.py`) — for every
   criterion, checks how well its keywords are covered by the matched files
   and assigns a status with a rationale and line-level evidence. Optionally
   delegates this step to an LLM (`--use-llm`, requires `OPENAI_API_KEY`) for
   higher-quality, context-aware judgements; automatically falls back to the
   heuristic if the LLM is unavailable.
5. **Render the report** (`report.py`) — Markdown (default, human-friendly)
   or JSON (machine-readable, e.g. for CI gating).

## Installation

```bash
pip install -e .
# Optional: enable LLM-assisted analysis
pip install -e ".[llm]"
# Optional: run the test suite
pip install -e ".[dev]"
```

Requires Python 3.10+. The core tool has **zero required third-party
dependencies**.

## Usage

```bash
python -m reviewer_agent.cli review \
    --requirements path/to/PRD.md \
    --source path/to/your/codebase \
    --output report.md
```

Or, after installing, use the console script:

```bash
reviewer-agent review -r path/to/PRD.md -s path/to/your/codebase -o report.md
```

### Options

| Flag | Description |
|---|---|
| `--requirements`, `-r` | Path to the requirements document (Markdown/text). |
| `--source`, `-s` | Path to the source code directory (or a single file). |
| `--output`, `-o` | Path to write the report to. Defaults to stdout. |
| `--format`, `-f` | `markdown` (default) or `json`. |
| `--top-k` | Max number of source files matched per feature (default: 5). |
| `--min-score` | Minimum keyword-overlap score required for a file match (default: 0.02). |
| `--use-llm` | Use an LLM (requires `OPENAI_API_KEY`) for higher-quality criterion analysis. Falls back to heuristics automatically if unavailable. |
| `--fail-below` | Exit non-zero if overall coverage is below this fraction (e.g. `0.8`) — useful in CI. |

### Try it on the bundled example

```bash
python -m reviewer_agent.cli review \
    --requirements examples/PRD_example.md \
    --source examples/sample_app
```

`examples/PRD_example.md` describes a small Task Tracker API (auth, task
creation, task completion, email notifications); `examples/sample_app/`
implements everything except the email notifications feature, so the demo
report shows a realistic mix of ✅/🟡/❌ results.

### Enabling LLM-assisted analysis

```bash
export OPENAI_API_KEY=sk-...
python -m reviewer_agent.cli review -r PRD.md -s ./src --use-llm
```

Set `REVIEWER_LLM_MODEL` to override the default model (`gpt-4o-mini`).

## Requirements document format

The parser is intentionally forgiving. A typical feature looks like:

```markdown
## Task Creation

As a logged-in user, I want to create a new task with a title and optional
due date so that I can track my work.

### Acceptance Criteria

- AC-1: A task cannot be created without a title.
- AC-2: A newly created task defaults to status "pending".
```

Headings (`#`, `##`, or `###`) delimit features/user-stories. Explicit
`Acceptance Criteria` / `Definition of Done` sub-sections are recognized; if
none is present, every bullet under the feature is treated as a criterion.

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

## Limitations

This tool uses lightweight, explainable heuristics (or an optional LLM) to
approximate whether code satisfies a requirement — it does **not** execute
the code or run your test suite. Treat every result, especially 🟡 and ❓, as
a prompt for human review rather than a certified pass/fail. It works best
as a fast first pass over large PRDs/codebases to focus reviewer attention
where it's most needed.
