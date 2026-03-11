"""Tests for GitHub URL parser and path sanitizer."""

import pytest

from github.parser import parse_pr_url, sanitize_path


class TestParsePrUrl:
    def test_valid_url(self) -> None:
        ref = parse_pr_url("https://github.com/owner/repo/pull/42")
        assert ref.owner == "owner"
        assert ref.repo == "repo"
        assert ref.number == 42

    def test_url_with_trailing_path(self) -> None:
        ref = parse_pr_url("https://github.com/owner/repo/pull/42/files")
        assert ref.number == 42

    def test_url_with_fragment(self) -> None:
        ref = parse_pr_url("https://github.com/owner/repo/pull/42#issuecomment-123")
        assert ref.number == 42

    def test_url_with_whitespace(self) -> None:
        ref = parse_pr_url("  https://github.com/owner/repo/pull/10  ")
        assert ref.number == 10

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid GitHub PR URL"):
            parse_pr_url("https://github.com/owner/repo/issues/42")

    def test_non_github_url_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_pr_url("https://gitlab.com/owner/repo/merge_requests/1")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_pr_url("")

    def test_hyphenated_owner_repo(self) -> None:
        ref = parse_pr_url("https://github.com/my-org/my-repo/pull/99")
        assert ref.owner == "my-org"
        assert ref.repo == "my-repo"


class TestSanitizePath:
    def test_normal_path(self) -> None:
        assert sanitize_path("src/main.py") == "src/main.py"

    def test_leading_slash_stripped(self) -> None:
        assert sanitize_path("/src/main.py") == "src/main.py"

    def test_traversal_raises(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            sanitize_path("../../etc/passwd")

    def test_traversal_in_middle_raises(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            sanitize_path("src/../etc/passwd")

    def test_unsafe_chars_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsafe characters"):
            sanitize_path("src/main.py;rm -rf /")

    def test_nested_path(self) -> None:
        assert sanitize_path("a/b/c/d.py") == "a/b/c/d.py"
