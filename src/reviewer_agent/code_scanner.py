"""Scans a source-code directory (or a single file) and loads its contents
for comparison against requirements."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from .models import CodeFile

DEFAULT_INCLUDE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rb", ".php",
    ".c", ".h", ".cpp", ".cc", ".hpp", ".cs", ".swift", ".m", ".scala",
    ".rs", ".sql", ".html", ".css", ".scss", ".vue", ".sh", ".yml", ".yaml",
    ".json", ".md",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".mypy_cache", ".pytest_cache", "target", "vendor", ".idea", ".vscode",
    "coverage", ".tox", "egg-info",
}

MAX_FILE_BYTES = 500_000


def scan_source(
    root: str,
    include_extensions: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[CodeFile]:
    """Recursively collect source files under *root*.

    If *root* points to a single file, a single-element list is returned.
    """

    include_extensions = include_extensions or DEFAULT_INCLUDE_EXTENSIONS
    exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS
    exclude_globs = exclude_globs or []

    root_path = Path(root)
    if root_path.is_file():
        return [_read_file(root_path, root_path.parent)]

    files: list[CodeFile] = []
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        if any(part in exclude_dirs for part in path.parts):
            continue
        rel = path.relative_to(root_path).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in exclude_globs):
            continue
        if path.suffix.lower() not in include_extensions:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(_read_file(path, root_path))
    return files


def _read_file(path: Path, root_path: Path) -> CodeFile:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = ""
    try:
        rel = path.relative_to(root_path).as_posix()
    except ValueError:
        rel = path.as_posix()
    return CodeFile(path=rel, content=content)
