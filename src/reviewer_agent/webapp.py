"""A small web UI for the Source Code Reviewer Agent.

Run with:

    reviewer-agent serve
    # or
    python -m reviewer_agent.webapp

Then open http://127.0.0.1:5000 in a browser. You can paste/upload a
requirements document, upload a source-code folder or .zip archive (or use
the bundled example), and get an interactive acceptance-criteria coverage
report -- downloadable as Markdown or JSON.
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
from .document_extractors import UnsupportedDocumentError, extract_text
from .llm_client import is_configured
from .report import render_json, render_markdown
from .requirements_parser import parse_requirements_text

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

            use_example_source = request.form.get("use_example_source") == "true"
            if use_example_source:
                source_root = str(EXAMPLES_DIR / "sample_app")
                source_label = "examples/sample_app (bundled example)"
            else:
                tmp_dir = tempfile.mkdtemp(prefix="reviewer-agent-src-")
                source_root, source_label = _materialize_uploaded_source(request, tmp_dir)
                if source_root is None:
                    return jsonify({"error": "No source code was provided (upload a folder or a .zip file)."}), 400

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

    return app


def _load_requirements_text(req) -> str:
    upload = req.files.get("requirements_file")
    if upload and upload.filename:
        return extract_text(upload.filename, upload.read())
    return req.form.get("requirements_text", "")


def _materialize_uploaded_source(req, tmp_dir: str) -> tuple[str | None, str]:
    zip_upload = req.files.get("source_zip")
    if zip_upload and zip_upload.filename:
        data = zip_upload.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            _safe_extract(zf, tmp_dir)
        return tmp_dir, f"{zip_upload.filename} (uploaded archive)"

    folder_files = req.files.getlist("source_files")
    folder_files = [f for f in folder_files if f and f.filename]
    if folder_files:
        for f in folder_files:
            rel_path = _sanitize_relative_path(f.filename)
            if rel_path is None:
                continue
            dest = Path(tmp_dir) / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.save(dest)
        return tmp_dir, "uploaded folder"

    return None, ""


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
