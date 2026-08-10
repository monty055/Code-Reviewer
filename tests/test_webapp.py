import io
import zipfile
from pathlib import Path

import pytest

flask = pytest.importorskip("flask")

from reviewer_agent.webapp import create_app

REQUIREMENTS_TEXT = """## Login

As a user, I want to log in so that I can access my account.

### Acceptance Criteria

- AC-1: Reject invalid passwords.
- AC-2: Issue a token on success.
"""


@pytest.fixture()
def client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_index_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Source Code Reviewer Agent" in resp.data


def test_status_endpoint(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert "llm_configured" in resp.get_json()


def test_example_requirements_endpoint(client):
    resp = client.get("/api/example/requirements")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "User Authentication" in data["text"]


def test_review_requires_requirements(client):
    resp = client.post("/api/review", data={"use_example_source": "true"})
    assert resp.status_code == 400
    assert "requirements" in resp.get_json()["error"].lower()


def test_review_requires_source(client):
    resp = client.post("/api/review", data={"requirements_text": REQUIREMENTS_TEXT})
    assert resp.status_code == 400
    assert "source" in resp.get_json()["error"].lower()


def test_review_rejects_binary_requirements_upload(client):
    fake_zip_bytes = b"PK\x03\x04" + bytes(range(256)) * 4
    data = {
        "requirements_file": (io.BytesIO(fake_zip_bytes), "export.mdux"),
        "use_example_source": "true",
    }
    resp = client.post("/api/review", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "doesn't look like" in resp.get_json()["error"]


def test_review_with_example_source(client):
    resp = client.post(
        "/api/review",
        data={"requirements_text": REQUIREMENTS_TEXT, "use_example_source": "true"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["feature_count"] == 1
    assert data["report"]["features"][0]["title"] == "Login"
    assert "# Source Code Review Report" in data["markdown"]


def test_review_with_uploaded_folder_files(client):
    data = {
        "requirements_text": REQUIREMENTS_TEXT,
        "source_files": [
            (io.BytesIO(b"def login(password):\n    reject_invalid(password)\n"), "login.py"),
        ],
    }
    resp = client.post("/api/review", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["file_count"] == 1


def test_review_with_uploaded_zip(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("app/login.py", "def login(password):\n    reject_invalid(password)\n")
    buf.seek(0)

    data = {
        "requirements_text": REQUIREMENTS_TEXT,
        "source_zip": (buf, "src.zip"),
    }
    resp = client.post("/api/review", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["file_count"] == 1
    assert body["report"]["features"][0]["matched_files"] == ["app/login.py"]


def test_zip_path_traversal_is_sanitized(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.py", "print('evil')\n")
        zf.writestr("login.py", "def login(password):\n    reject_invalid(password)\n")
    buf.seek(0)

    data = {
        "requirements_text": REQUIREMENTS_TEXT,
        "source_zip": (buf, "src.zip"),
    }
    resp = client.post("/api/review", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    # The traversal entry should have been sanitized into the temp dir, not escaped it.
    assert body["file_count"] == 2
