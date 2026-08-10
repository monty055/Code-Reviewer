from pathlib import Path

from reviewer_agent.code_scanner import scan_source

FIXTURES = Path(__file__).parent / "fixtures"


def test_scans_directory_and_reads_files():
    files = scan_source(str(FIXTURES / "sample_project"))
    assert len(files) == 1
    assert files[0].path == "login.py"
    assert "def login" in files[0].content


def test_scans_single_file():
    files = scan_source(str(FIXTURES / "sample_project" / "login.py"))
    assert len(files) == 1
    assert files[0].path == "login.py"


def test_excludes_dot_dirs_and_unsupported_extensions(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored")
    (tmp_path / "data.bin").write_bytes(b"\x00\x01")
    (tmp_path / "app.py").write_text("print('hi')")

    files = scan_source(str(tmp_path))
    paths = {f.path for f in files}
    assert paths == {"app.py"}
