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
# Optional: run the web UI
pip install -e ".[web]"
# Optional: read .docx/.pdf requirements docs, and export test cases to .docx
pip install -e ".[docs]"
# Optional: export generated test cases to PDF
pip install -e ".[export]"
# Optional: run the test suite
pip install -e ".[dev]"
```

Requires Python 3.10+. The core CLI tool has **zero required third-party
dependencies**; the web UI requires Flask (`pip install -e ".[web]"`).

## Web UI

For an interactive experience, launch the bundled web app:

```bash
pip install -e ".[web]"
reviewer-agent serve
# then open http://127.0.0.1:5000
```

From the UI you can:

- Paste your requirements document or upload a `.md`/`.txt` file (or click
  **Load example PRD** to try the bundled sample).
- Add one or more source-code folders and/or `.zip` archives at once (e.g. a
  separate **frontend** and **backend** folder, added side by side) &mdash;
  they're all combined into a single codebase for the review &mdash; or
  check **Use bundled example app** to try it instantly.
- Tune matching options (max files per feature, min match score, optional
  LLM-assisted analysis if `OPENAI_API_KEY` is configured on the server).
- Click **Run Review** to get an interactive report: an overall coverage
  ring, expandable per-feature cards with a criteria table (status,
  confidence, rationale, evidence), and a list of source files not linked to
  any feature.
- Click **View RCI Report (HTML)** to open a standalone, plain-English
  "Requirement Compliance Index" report in a new tab (see below), or
  download the report as HTML, Markdown, or JSON.

Use `--host`/`--port`/`--debug` to customize the server, e.g.
`reviewer-agent serve --host 0.0.0.0 --port 8080`.

## CLI Usage

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
| `--format`, `-f` | `markdown` (default), `json`, or `html` (a standalone "Requirement Compliance Index" report, see below). |
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

## The Requirement Compliance Index (RCI) HTML report

Alongside Markdown and JSON, the tool can produce a standalone, self-contained
**HTML "Requirement Compliance Index" (RCI) report** written in plain,
human-readable English -- suitable for opening directly in a browser,
printing, or sharing with non-technical stakeholders (PMs, QA, auditors).

```bash
python -m reviewer_agent.cli review -r PRD.md -s ./src -o rci-report.html --format html
```

or, in the web UI, click **View RCI Report (HTML)** / **Download HTML**
after running a review.

It includes:

- An overall **RCI score** (the percentage of acceptance criteria that are
  Met or Partially Met) with a plain-English explanation of what that means.
- A "What This Report Means" section spelling out the status legend.
- A feature-by-feature summary table with progress bars and jump links.
- Per-feature sections with a narrative paragraph (e.g. *"3 of 4 acceptance
  criteria are fully met, 1 is partially met... for an overall compliance of
  75%."*), the matched source files, and a detailed table per acceptance
  criterion (status, confidence, plain-English explanation, and evidence).
- A list of source files that weren't linked to any feature.

The HTML has no external dependencies (CSS is inlined), so the file can be
emailed, committed, or opened offline as-is.

## Supported requirements file formats

Uploaded/loaded requirements files can be:

- **Plain text / Markdown** (`.md`, `.txt`) — read natively, no extra dependencies.
- **`.docx`** — heading styles are converted to Markdown `#`/`##`/`###`, and table rows are converted to bullet lines. Requires `pip install -e ".[docs]"`.
- **`.pdf`** — text is extracted page by page. Requires `pip install -e ".[docs]"`. Scanned/image-only PDFs aren't supported (no OCR).

If you upload a file that isn't plain text/Markdown and doesn't match a supported format above (e.g. a raw Confluence/Word export saved with a non-`.docx` extension), you'll get a clear error asking you to paste the text directly or save/export it as `.md`/`.txt`/`.docx`/`.pdf` instead of silently getting a garbled/binary result.

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

## Gap Analysis + Test-Data Readiness workflow

Besides comparing requirements against code, this repo also includes a
**Gap Analysis** agent that works purely on the requirements document
itself — no source code needed. Use it to drive a workflow like:

> Requirements docs → user-story gap analysis → design gaps → gap analysis
> report → mandatory information needed to generate test cases with test
> data.

Run it with:

```bash
python -m reviewer_agent.cli gap-analysis \
    --requirements path/to/PRD.md \
    --output gap-report.md
```

or, after installing: `reviewer-agent gap-analysis -r PRD.md -o gap-report.md`.

For every feature/user story parsed from the document (see
[Requirements document format](#requirements-document-format)), it reports:

1. **User story gaps** — missing role/goal/benefit (`As a ... I want ... so
   that ...`), missing or too-terse acceptance criteria, vague/subjective
   language (e.g. "fast", "user-friendly", "TBD") that can't be objectively
   verified, and stories that only describe the happy path with no
   negative/error-handling criteria.
2. **Design gaps** — non-functional requirement categories (security &
   access control, performance & scalability, data validation & formats,
   error handling & recovery, UI/UX & accessibility, integration &
   interfaces, reliability & availability) that aren't mentioned for a
   feature, plus a **document-level** rollup of categories missing across
   the *entire* document (since NFRs are often meant to apply globally).
3. **Mandatory information for test-case generation** — for every
   acceptance criterion, the data fields/entities it implies (quoted
   literals plus known field-name keywords like `email`, `date`, `status`,
   `id`, ...) and a checklist of what's still missing before a QA engineer
   (or an LLM) could reliably turn it into test cases with concrete test
   data: example values, boundary/min-max values, expected formats, and
   whether both the valid *and* invalid cases are covered.

### Options

| Flag | Description |
|---|---|
| `--requirements`, `-r` | Path to the requirements document (Markdown/text/`.docx`/`.pdf`). |
| `--output`, `-o` | Path to write the report to. Defaults to stdout. |
| `--format`, `-f` | `markdown` (default) or `json` (machine-readable, e.g. to feed into a downstream test-case-generation agent/LLM). |
| `--fail-below` | Exit non-zero if the overall test-data readiness score is below this fraction (e.g. `0.8`) — useful in CI to gate on requirements quality before test cases are written. |

### Try it on the bundled example

```bash
python -m reviewer_agent.cli gap-analysis --requirements examples/PRD_example.md
```

### Generating draft test cases (with test data)

Once you've reviewed the gap analysis, generate draft test cases -- one (or
more, for missing valid/invalid/boundary counterparts) per acceptance
criterion, each with concrete test data where enough information is
available, or a clearly flagged "needs clarification" stub with the exact
open question otherwise:

```bash
python -m reviewer_agent.cli generate-test-cases \
    --requirements examples/PRD_example.md \
    --output test-cases.md
```

`--format` supports `markdown` (default), `json`, `csv`, `docx` (requires
the `docs` extra), and `pdf` (requires the `export` extra) — `--output` is
required for the binary `docx`/`pdf` formats. Each generated test case
includes preconditions, numbered steps, a test-data table, the expected
result, a type (`Positive` / `Negative` / `Boundary`), a priority, and,
when applicable, the specific open questions blocking automation.

### Web UI: upload any doc, analyze gaps, export test cases

The web UI (`reviewer-agent serve`, see [Web UI](#web-ui) above) has a
dedicated **"Gap Analysis & Test Cases"** tab alongside the code-review
tab. From there you can:

- **Upload** a requirements document in any supported format (`.docx`,
  `.pdf`, `.md`, `.txt`) or paste it directly — no source code required.
- Click **Run Gap Analysis** to see, per feature: user-story gaps, design
  gaps, and a per-criterion breakdown of the data fields and mandatory
  missing information needed for test-case generation (with a
  document-level rollup of NFR categories missing entirely). Download the
  gap report as Markdown or JSON.
- Click **Generate Test Cases** to see the drafted test cases (with test
  data, type, priority, and readiness status) in a table, then **export
  them as Markdown, JSON, CSV, Word (.docx), or PDF** with one click.

### Suggested end-to-end flow

1. Drop your PRD/BRD/user-story doc in as-is (`.md`, `.txt`, `.docx`, or
   `.pdf`) — no reformatting needed, the parser (`requirements_parser.py`)
   is forgiving about structure. Use the CLI or the web UI's "Gap Analysis
   & Test Cases" tab.
2. Run gap analysis and share the report with the requirements author/BA to
   close the high-severity gaps (missing acceptance criteria, happy-path-only
   stories, undocumented NFR categories).
3. Once gaps are closed, generate test cases and export them to whichever
   format your QA process needs (CSV for a test-management tool import,
   `.docx`/PDF for a shareable document, JSON for a downstream automation
   pipeline). Criteria still missing mandatory info produce clearly flagged
   stub test cases instead of guessed test data, so nothing masquerades as
   ready when it isn't.
4. Optionally also run `review --source ./src` once the code exists, to
   check the acceptance criteria are actually implemented (see
   [CLI Usage](#cli-usage) above).

## Release Notes Gap Analyzer

The `release-gap-analysis` workflow compares two—and only two—documents:
User Stories for one release and the Development Release Notes for that same
release. It validates both release identifiers before comparison and stops
without findings when they do not match.

```bash
reviewer-agent release-gap-analysis \
    --user-stories examples/release_24_user_stories.md \
    --release-notes examples/release_24_development_notes.md \
    --output release-gap-report.md
```

Use `--format json` for machine-readable output. The report classifies each
explicit User Story fact as Covered, Partially Covered, Missing,
Contradictory, or Needs Clarification and quotes evidence from both inputs.
Missing note evidence is always reported as “Not found in the provided
Development Release Notes.” It does not infer undocumented dependencies,
limitations, functionality, or root causes.

The web UI includes a **Release Notes Gap Analyzer** tab with separate paste
and upload inputs for both documents, release-scope validation, an
evidence-backed findings table, and Markdown/JSON downloads.

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
