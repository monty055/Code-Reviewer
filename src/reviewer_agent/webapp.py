"""A small web UI for the Source Code Reviewer Agent.

Run with:

    reviewer-agent serve
    # or
    python -m reviewer_agent.webapp

Then open http://127.0.0.1:5000 in a browser. You can paste/upload a
requirements document, upload one or more source-code folders and/or .zip
archives at once (e.g. a separate `frontend` and `backend` folder, reviewed
together as a single codebase) -- or use the bundled example -- and get an
interactive acceptance-criteria coverage report, downloadable as HTML,
Markdown, or JSON.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from .analyzer import review
from .code_scanner import scan_source
from .document_extractors import UnsupportedDocumentError, extract_text, require_looks_like_text
from .gap_analysis import run_gap_analysis
from .gap_report import render_json as render_gap_json
from .gap_report import render_markdown as render_gap_markdown
from .llm_client import is_configured
from .report import render_html, render_json, render_markdown
from .requirements_parser import parse_requirements_text
from .test_case_export import ExportDependencyError
from .test_case_export import render_csv as render_tc_csv
from .test_case_export import render_docx as render_tc_docx
from .test_case_export import render_json as render_tc_json
from .test_case_export import render_markdown as render_tc_markdown
from .test_case_export import render_pdf as render_tc_pdf
from .test_case_generator import generate_test_case_suite

PACKAGE_DIR = Path(__file__).parent
EXAMPLES_DIR = PACKAGE_DIR.parent.parent / "examples"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(PACKAGE_DIR / "templates"), static_folder=str(PACKAGE_DIR / "static"))
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    @app.get("/")
    def index():
        from flask import render_template

        return render_template("index.html", llm_configured=is_configured())

    @app.get("/api/status")
    def status():
        return jsonify({"llm_configured": is_configured()})

    @app.get("/api/example/requirements")
    def example_requirements():
        path = EXAMPLES_DIR / "PRD_example.md"
        if not path.exists():
            return jsonify({"error": "bundled example not found"}), 404
        return jsonify({"text": path.read_text(encoding="utf-8")})

    @app.post("/api/review")
    def api_review():
        tmp_dir: str | None = None
        try:
            requirements_text = _load_requirements_text(request)
            if not requirements_text or not requirements_text.strip():
                return jsonify({"error": "No requirements document was provided."}), 400
            require_looks_like_text(requirements_text, "the requirements document")

            use_example_source = request.form.get("use_example_source") == "true"
            if use_example_source:
                source_root = str(EXAMPLES_DIR / "sample_app")
                source_label = "examples/sample_app (bundled example)"
            else:
                tmp_dir = tempfile.mkdtemp(prefix="reviewer-agent-src-")
                source_root, source_label = _materialize_uploaded_source(request, tmp_dir)
                if source_root is None:
                    return (
                        jsonify(
                            {
                                "error": "No source code was provided (upload one or more folders and/or .zip files)."
                            }
                        ),
                        400,
                    )

            top_k = _int_form(request, "top_k", default=5, min_v=1, max_v=20)
            min_score = _float_form(request, "min_score", default=0.02, min_v=0.0, max_v=1.0)
            use_llm = request.form.get("use_llm") == "true" and is_configured()

            features = parse_requirements_text(requirements_text, source_name="requirements")
            if not features:
                return jsonify({"error": "Could not parse any features/user stories from the requirements document."}), 400

            files = scan_source(source_root)

            report = review(
                features=features,
                files=files,
                requirements_source="(pasted/uploaded requirements)",
                codebase_source=source_label,
                top_k=top_k,
                min_score=min_score,
                use_llm=use_llm,
            )

            import json as _json

            return jsonify(
                {
                    "report": _json.loads(render_json(report)),
                    "markdown": render_markdown(report),
                    "html": render_html(report),
                    "file_count": len(files),
                    "feature_count": len(features),
                }
            )
        except UnsupportedDocumentError as exc:
            return jsonify({"error": str(exc)}), 400
        except zipfile.BadZipFile:
            return jsonify({"error": "The uploaded .zip file could not be read."}), 400
        except Exception as exc:  # pragma: no cover - defensive catch-all for the UI
            app.logger.exception("Review failed")
            return jsonify({"error": f"Unexpected error: {exc}"}), 500
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @app.post("/api/gap-analysis")
    def api_gap_analysis():
        try:
            features = _parse_uploaded_requirements(request)
        except UnsupportedDocumentError as exc:
            return jsonify({"error": str(exc)}), 400
        except _RequirementsError as exc:
            return jsonify({"error": str(exc)}), 400

        report = run_gap_analysis(features, requirements_source="(pasted/uploaded requirements)")

        import json as _json

        return jsonify(
            {
                "report": _json.loads(render_gap_json(report)),
                "markdown": render_gap_markdown(report),
                "feature_count": len(features),
            }
        )

    @app.post("/api/test-cases")
    def api_test_cases():
        try:
            features = _parse_uploaded_requirements(request)
        except UnsupportedDocumentError as exc:
            return jsonify({"error": str(exc)}), 400
        except _RequirementsError as exc:
            return jsonify({"error": str(exc)}), 400

        gap_report = run_gap_analysis(features, requirements_source="(pasted/uploaded requirements)")
        suite = generate_test_case_suite(gap_report)

        import json as _json

        return jsonify(
            {
                "suite": _json.loads(render_tc_json(suite)),
                "markdown": render_tc_markdown(suite),
                "feature_count": len(features),
            }
        )

    @app.post("/api/export/test-cases")
    def api_export_test_cases():
        export_format = request.form.get("format", "markdown")
        if export_format not in _TC_EXPORTERS:
            return jsonify({"error": f"Unsupported export format: {export_format}"}), 400

        try:
            features = _parse_uploaded_requirements(request)
        except UnsupportedDocumentError as exc:
            return jsonify({"error": str(exc)}), 400
        except _RequirementsError as exc:
            return jsonify({"error": str(exc)}), 400

        gap_report = run_gap_analysis(features, requirements_source="(pasted/uploaded requirements)")
        suite = generate_test_case_suite(gap_report)

        try:
            rendered = _TC_EXPORTERS[export_format](suite)
        except ExportDependencyError as exc:
            return jsonify({"error": str(exc)}), 400

        mimetype, extension, is_binary = _TC_FORMAT_META[export_format]
        payload = rendered if is_binary else rendered.encode("utf-8")
        return send_file(
            io.BytesIO(payload),
            mimetype=mimetype,
            as_attachment=True,
            download_name=f"test-cases.{extension}",
        )

    return app


class _RequirementsError(RuntimeError):
    """Raised when no usable requirements text/features could be parsed
    from the request -- kept internal to this module and translated into a
    400 JSON response by every endpoint that shares this helper."""


def _parse_uploaded_requirements(req):
    """Shared helper for the gap-analysis/test-case endpoints: load the
    requirements text from the request (pasted or uploaded), validate it
    looks like real text, and parse it into :class:`Feature` objects."""

    requirements_text = _load_requirements_text(req)
    if not requirements_text or not requirements_text.strip():
        raise _RequirementsError("No requirements document was provided.")
    require_looks_like_text(requirements_text, "the requirements document")

    features = parse_requirements_text(requirements_text, source_name="requirements")
    if not features:
        raise _RequirementsError("Could not parse any features/user stories from the requirements document.")
    return features


_TC_EXPORTERS = {
    "markdown": render_tc_markdown,
    "json": render_tc_json,
    "csv": render_tc_csv,
    "docx": render_tc_docx,
    "pdf": render_tc_pdf,
}

# (mimetype, file extension, is_binary)
_TC_FORMAT_META = {
    "markdown": ("text/markdown", "md", False),
    "json": ("application/json", "json", False),
    "csv": ("text/csv", "csv", False),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx", True),
    "pdf": ("application/pdf", "pdf", True),
}


def _load_requirements_text(req) -> str:
    upload = req.files.get("requirements_file")
    if upload and upload.filename:
        return extract_text(upload.filename, upload.read())
    return req.form.get("requirements_text", "")


def _materialize_uploaded_source(req, tmp_dir: str) -> tuple[str | None, str]:
    """Combine one or more uploaded folders and/or .zip archives (e.g. a
    separate ``frontend`` folder plus a ``backend.zip``) into a single
    temporary source tree so they can all be reviewed together.

    When more than one source is present, each is placed under its own
    top-level namespace directory (derived from the folder's own top-level
    name, or the zip's filename) so that files with the same relative path
    in different sources (e.g. two ``src/index.js``) don't collide.
    """

    zip_uploads = [f for f in req.files.getlist("source_zip") if f and f.filename]
    folder_files = [f for f in req.files.getlist("source_files") if f and f.filename]

    if not zip_uploads and not folder_files:
        return None, ""

    folder_groups = _group_folder_files_by_top_level_dir(folder_files)
    multiple_sources = (len(zip_uploads) + len(folder_groups)) > 1

    labels: list[str] = []
    used_namespaces: set[str] = set()

    for zip_upload in zip_uploads:
        with zipfile.ZipFile(io.BytesIO(zip_upload.read())) as zf:
            if multiple_sources:
                namespace = _unique_namespace(Path(zip_upload.filename).stem, used_namespaces)
                dest_dir = Path(tmp_dir) / namespace
                dest_dir.mkdir(parents=True, exist_ok=True)
                _safe_extract(zf, str(dest_dir))
            else:
                _safe_extract(zf, tmp_dir)
        labels.append(zip_upload.filename)

    for top_level_name, files in folder_groups.items():
        for f in files:
            rel_path = _sanitize_relative_path(f.filename)
            if rel_path is None:
                continue
            dest = Path(tmp_dir) / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.save(dest)
        labels.append(top_level_name or "uploaded folder")

    label_suffix = "s" if len(labels) > 1 else ""
    source_label = f"uploaded source{label_suffix}: {', '.join(labels)}"
    return tmp_dir, source_label


def _group_folder_files_by_top_level_dir(folder_files: list) -> dict[str, list]:
    """Group uploaded folder files by their top-level directory name (the
    root of each ``webkitRelativePath``), so multiple separately-selected
    folders (e.g. ``frontend`` and ``backend``) are tracked distinctly for
    labeling purposes even though they land in the same temp directory."""

    groups: dict[str, list] = {}
    for f in folder_files:
        rel_path = _sanitize_relative_path(f.filename)
        top_level = rel_path.split("/", 1)[0] if rel_path else "uploaded folder"
        groups.setdefault(top_level, []).append(f)
    return groups


def _unique_namespace(stem: str, used: set[str]) -> str:
    base = _sanitize_relative_path(stem) or "archive"
    base = base.replace("/", "-")
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _sanitize_relative_path(raw_path: str) -> str | None:
    """Prevent path traversal from untrusted upload filenames."""

    normalized = raw_path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    return "/".join(parts)


def _safe_extract(zf: zipfile.ZipFile, dest_dir: str) -> None:
    dest_root = Path(dest_dir).resolve()
    for member in zf.infolist():
        rel_path = _sanitize_relative_path(member.filename)
        if rel_path is None:
            continue
        target = (dest_root / rel_path).resolve()
        if dest_root not in target.parents and target != dest_root:
            continue
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def _int_form(req, key: str, default: int, min_v: int, max_v: int) -> int:
    try:
        value = int(req.form.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(min_v, min(max_v, value))


def _float_form(req, key: str, default: float, min_v: float, max_v: float) -> float:
    try:
        value = float(req.form.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(min_v, min(max_v, value))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Source Code Reviewer Agent web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
