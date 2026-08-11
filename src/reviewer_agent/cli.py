"""Command-line entry point for the Source Code Reviewer Agent.

Example:
    python -m reviewer_agent.cli review \\
        --requirements examples/PRD_example.md \\
        --source examples/sample_app \\
        --output report.md

    python -m reviewer_agent.cli gap-analysis \\
        --requirements examples/PRD_example.md \\
        --output gap-report.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyzer import review
from .code_scanner import scan_source
from .document_extractors import UnsupportedDocumentError
from .gap_analysis import run_gap_analysis
from .gap_report import render_json as render_gap_json
from .gap_report import render_markdown as render_gap_markdown
from .llm_client import is_configured
from .report import render_html, render_json, render_markdown
from .requirements_parser import parse_requirements_file
from .test_case_export import ExportDependencyError
from .test_case_export import render_csv as render_tc_csv
from .test_case_export import render_docx as render_tc_docx
from .test_case_export import render_json as render_tc_json
from .test_case_export import render_markdown as render_tc_markdown
from .test_case_export import render_pdf as render_tc_pdf
from .test_case_generator import generate_test_case_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reviewer_agent",
        description="Review source code against a requirements document (User Story / PRD / BRD).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    review_parser = sub.add_parser("review", help="Run a full review and generate a report.")
    review_parser.add_argument(
        "--requirements", "-r", required=True, help="Path to the requirements document (Markdown/text)."
    )
    review_parser.add_argument(
        "--source", "-s", required=True, help="Path to the source code directory (or a single file)."
    )
    review_parser.add_argument(
        "--output", "-o", default=None, help="Path to write the report to. Defaults to stdout."
    )
    review_parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json", "html"],
        default="markdown",
        help="Output format. 'html' produces a standalone Requirement Compliance Index (RCI) "
        "report in plain English, viewable directly in a browser.",
    )
    review_parser.add_argument(
        "--top-k", type=int, default=5, help="Max number of source files matched per feature (default: 5)."
    )
    review_parser.add_argument(
        "--min-score", type=float, default=0.02, help="Minimum keyword-overlap score for a file match (default: 0.02)."
    )
    review_parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use an LLM (requires OPENAI_API_KEY) for higher-quality criterion analysis; "
        "falls back to heuristics if unavailable.",
    )
    review_parser.add_argument(
        "--fail-below",
        type=float,
        default=None,
        help="Exit with a non-zero status if overall coverage is below this fraction (e.g. 0.8).",
    )

    gap_parser = sub.add_parser(
        "gap-analysis",
        help="Analyze a requirements document for user-story gaps, design gaps, and the "
        "mandatory information needed to generate test cases with test data.",
    )
    gap_parser.add_argument(
        "--requirements", "-r", required=True, help="Path to the requirements document (Markdown/text)."
    )
    gap_parser.add_argument(
        "--output", "-o", default=None, help="Path to write the report to. Defaults to stdout."
    )
    gap_parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    gap_parser.add_argument(
        "--fail-below",
        type=float,
        default=None,
        help="Exit with a non-zero status if the overall test-data readiness score is below "
        "this fraction (e.g. 0.8) -- useful in CI to gate on requirements quality.",
    )

    tc_parser = sub.add_parser(
        "generate-test-cases",
        help="Generate draft test cases (with test data) from a requirements document's gap analysis.",
    )
    tc_parser.add_argument(
        "--requirements", "-r", required=True, help="Path to the requirements document (Markdown/text)."
    )
    tc_parser.add_argument(
        "--output", "-o", default=None, help="Path to write the report to. Defaults to stdout (not valid for docx/pdf)."
    )
    tc_parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json", "csv", "docx", "pdf"],
        default="markdown",
        help="Output format (default: markdown). 'docx' requires the 'docs' extra, 'pdf' requires the 'export' extra.",
    )

    serve_parser = sub.add_parser("serve", help="Launch the web UI for interactive code reviews.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1).")
    serve_parser.add_argument("--port", type=int, default=5000, help="Port to bind (default: 5000).")
    serve_parser.add_argument("--debug", action="store_true", help="Run Flask in debug/reload mode.")

    return parser


def run_serve(args: argparse.Namespace) -> int:
    try:
        from .webapp import create_app
    except ImportError:
        print(
            "error: the web UI requires Flask. Install it with: pip install -e \".[web]\"",
            file=sys.stderr,
        )
        return 2

    app = create_app()
    print(f"Serving Source Code Reviewer UI on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def run_review(args: argparse.Namespace) -> int:
    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"error: requirements file not found: {req_path}", file=sys.stderr)
        return 2

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"error: source path not found: {src_path}", file=sys.stderr)
        return 2

    try:
        features = parse_requirements_file(str(req_path))
    except UnsupportedDocumentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not features:
        print("error: no features/user-stories could be parsed from the requirements document", file=sys.stderr)
        return 2

    files = scan_source(str(src_path))
    if not files:
        print("warning: no source files were found to review", file=sys.stderr)

    if args.use_llm and not is_configured():
        print(
            "warning: --use-llm was set but no API key is configured "
            "(set OPENAI_API_KEY); falling back to heuristic analysis.",
            file=sys.stderr,
        )

    report = review(
        features=features,
        files=files,
        requirements_source=str(req_path),
        codebase_source=str(src_path),
        top_k=args.top_k,
        min_score=args.min_score,
        use_llm=args.use_llm,
    )

    if args.format == "json":
        rendered = render_json(report)
    elif args.format == "html":
        rendered = render_html(report)
    else:
        rendered = render_markdown(report)

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(rendered)

    if args.fail_below is not None and report.overall_coverage < args.fail_below:
        print(
            f"error: overall coverage {report.overall_coverage:.0%} is below threshold "
            f"{args.fail_below:.0%}",
            file=sys.stderr,
        )
        return 1

    return 0


def run_gap_analysis_command(args: argparse.Namespace) -> int:
    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"error: requirements file not found: {req_path}", file=sys.stderr)
        return 2

    try:
        features = parse_requirements_file(str(req_path))
    except UnsupportedDocumentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not features:
        print("error: no features/user-stories could be parsed from the requirements document", file=sys.stderr)
        return 2

    report = run_gap_analysis(features, requirements_source=str(req_path))

    rendered = render_gap_json(report) if args.format == "json" else render_gap_markdown(report)

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(rendered)

    if args.fail_below is not None and report.overall_readiness_score < args.fail_below:
        print(
            f"error: overall test-data readiness {report.overall_readiness_score:.0%} is below "
            f"threshold {args.fail_below:.0%}",
            file=sys.stderr,
        )
        return 1

    return 0


_TC_BINARY_FORMATS = {"docx", "pdf"}
_TC_RENDERERS = {
    "markdown": render_tc_markdown,
    "json": render_tc_json,
    "csv": render_tc_csv,
    "docx": render_tc_docx,
    "pdf": render_tc_pdf,
}


def run_generate_test_cases(args: argparse.Namespace) -> int:
    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"error: requirements file not found: {req_path}", file=sys.stderr)
        return 2

    try:
        features = parse_requirements_file(str(req_path))
    except UnsupportedDocumentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not features:
        print("error: no features/user-stories could be parsed from the requirements document", file=sys.stderr)
        return 2

    if args.format in _TC_BINARY_FORMATS and not args.output:
        print(f"error: --output is required when --format is '{args.format}'", file=sys.stderr)
        return 2

    gap_report = run_gap_analysis(features, requirements_source=str(req_path))
    suite = generate_test_case_suite(gap_report)

    try:
        rendered = _TC_RENDERERS[args.format](suite)
    except ExportDependencyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        mode = "wb" if args.format in _TC_BINARY_FORMATS else "w"
        if mode == "wb":
            Path(args.output).write_bytes(rendered)
        else:
            Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"Test cases written to {args.output}")
    else:
        print(rendered)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "review":
        return run_review(args)
    if args.command == "gap-analysis":
        return run_gap_analysis_command(args)
    if args.command == "generate-test-cases":
        return run_generate_test_cases(args)
    if args.command == "serve":
        return run_serve(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
