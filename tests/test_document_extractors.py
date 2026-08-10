import io

import pytest

from reviewer_agent.document_extractors import UnsupportedDocumentError, extract_text


def test_plain_markdown_passes_through():
    text = "## Feature\n\n- AC-1: Do the thing.\n"
    assert extract_text("prd.md", text.encode("utf-8")) == text


def test_txt_extension_passes_through():
    text = "As a user I want X so that Y.\n"
    assert extract_text("notes.txt", text.encode("utf-8")) == text


def test_binary_zip_like_upload_raises_clear_error():
    # A .docx/.pptx/.xlsx file (or a raw zip) is itself a ZIP archive whose
    # bytes are not valid text -- decoding it naively produces garbage.
    fake_zip_bytes = b"PK\x03\x04" + bytes(range(256)) * 4
    with pytest.raises(UnsupportedDocumentError):
        extract_text("export.confluence", fake_zip_bytes)


def test_docx_extraction_preserves_headings_and_bullets():
    docx = pytest.importorskip("docx")
    buf = io.BytesIO()
    document = docx.Document()
    document.add_heading("User Login", level=1)
    document.add_paragraph("As a user, I want to log in so that I can access my account.")
    document.add_heading("Acceptance Criteria", level=2)
    document.add_paragraph("Reject invalid passwords.", style="List Bullet")
    document.add_paragraph("Issue a token on success.", style="List Bullet")
    document.save(buf)
    buf.seek(0)

    text = extract_text("prd.docx", buf.getvalue())

    assert "# User Login" in text
    assert "## Acceptance Criteria" in text
    assert "Reject invalid passwords." in text
    assert "Issue a token on success." in text


def test_docx_without_dependency_raises_helpful_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "docx":
            raise ImportError("no docx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(UnsupportedDocumentError, match="python-docx"):
        extract_text("prd.docx", b"irrelevant")


def test_pdf_without_dependency_raises_helpful_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("no pypdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(UnsupportedDocumentError, match="pypdf"):
        extract_text("prd.pdf", b"irrelevant")
