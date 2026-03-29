"""Unit tests for app.utils.file_utils."""

import os

import pytest

from app.utils.file_utils import (
    get_file_type,
    sanitize_filename,
    ensure_unique_path,
    list_folders,
)


# ---------------------------------------------------------------------------
# get_file_type
# ---------------------------------------------------------------------------

class TestGetFileType:

    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("report.pdf", "pdf"),
            ("photo.png", "image"),
            ("photo.jpg", "image"),
            ("photo.jpeg", "image"),
            ("scan.tiff", "image"),
            ("scan.tif", "image"),
            ("icon.bmp", "image"),
            ("anim.gif", "image"),
            ("pic.webp", "image"),
            ("doc.docx", "docx"),
            ("sheet.xlsx", "xlsx"),
            ("notes.txt", "text"),
            ("readme.md", "text"),
            ("data.csv", "text"),
            ("letter.rtf", "text"),
            ("archive.zip", "unknown"),
            ("noext", "unknown"),
        ],
    )
    def test_file_types(self, filename, expected):
        assert get_file_type(filename) == expected

    def test_case_insensitive(self):
        assert get_file_type("REPORT.PDF") == "pdf"
        assert get_file_type("Photo.JPG") == "image"


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:

    def test_removes_special_characters(self):
        result = sanitize_filename('my<file>:name"/\\|?*here')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_collapses_multiple_underscores(self):
        result = sanitize_filename("a:::b")
        assert "__" not in result  # no double underscores

    def test_strips_leading_trailing(self):
        result = sanitize_filename("...name...")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_empty_string_returns_unnamed(self):
        assert sanitize_filename("") == "unnamed"

    def test_only_special_chars_returns_unnamed(self):
        assert sanitize_filename(':<>"/\\|?*') == "unnamed"

    def test_normal_name_unchanged(self):
        assert sanitize_filename("my_report_2024") == "my_report_2024"


# ---------------------------------------------------------------------------
# ensure_unique_path
# ---------------------------------------------------------------------------

class TestEnsureUniquePath:

    def test_no_conflict(self, tmp_path):
        path = str(tmp_path / "newfile.txt")
        assert ensure_unique_path(path) == path

    def test_with_existing_file(self, tmp_path):
        original = tmp_path / "file.txt"
        original.write_text("exists")
        result = ensure_unique_path(str(original))
        assert result != str(original)
        assert "file_1.txt" in result

    def test_with_multiple_conflicts(self, tmp_path):
        base = tmp_path / "file.txt"
        base.write_text("v0")
        (tmp_path / "file_1.txt").write_text("v1")
        (tmp_path / "file_2.txt").write_text("v2")
        result = ensure_unique_path(str(base))
        assert "file_3.txt" in result


# ---------------------------------------------------------------------------
# list_folders
# ---------------------------------------------------------------------------

class TestListFolders:

    def test_returns_only_directories(self, tmp_path):
        (tmp_path / "dir_a").mkdir()
        (tmp_path / "dir_b").mkdir()
        (tmp_path / "file.txt").write_text("hello")
        result = list_folders(str(tmp_path))
        assert "dir_a" in result
        assert "dir_b" in result
        assert "file.txt" not in result

    def test_ignores_dot_directories(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        result = list_folders(str(tmp_path))
        assert ".hidden" not in result
        assert "visible" in result

    def test_sorted_output(self, tmp_path):
        for name in ["zebra", "alpha", "middle"]:
            (tmp_path / name).mkdir()
        result = list_folders(str(tmp_path))
        assert result == sorted(result)

    def test_nonexistent_dir(self, tmp_path):
        result = list_folders(str(tmp_path / "does_not_exist"))
        assert result == []
