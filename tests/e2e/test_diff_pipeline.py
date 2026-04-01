"""E2E tests for the diff parsing + citation extraction + validation pipeline.

Covers the full flow: raw unified-diff patch string -> parse_patch -> FileDiff
with DiffHunks -> extract_citations from review text -> validate_citations
against parsed hunks.  Also covers PR URL parsing and path sanitization.
"""

import pytest

from github.diff import line_range_from_hunk, parse_patch
from github.models import DiffHunk, FileDiff, PRFile
from github.parser import parse_pr_url, sanitize_path
from review.citations import extract_citations, validate_citations


# ---------------------------------------------------------------------------
# Helpers — realistic patch content
# ---------------------------------------------------------------------------

MULTI_HUNK_PATCH = """\
@@ -1,7 +1,8 @@
 import os
 import sys
+import logging

 def main():
-    print("hello")
+    logging.info("hello")
     return 0
@@ -20,6 +21,10 @@
 def helper():
     pass

+def new_function():
+    \"\"\"Added in this PR.\"\"\"
+    return 42
+
 class Config:
     pass"""

RENAME_PATCH = """\
@@ -1,4 +1,4 @@
-# Old header
+# New header

 def greet():
     pass"""

SINGLE_LINE_PATCH = """\
@@ -5 +5 @@
-    old_value = 1
+    new_value = 2"""


# ---------------------------------------------------------------------------
# 1. Parse realistic multi-hunk patch
# ---------------------------------------------------------------------------


class TestParseMultiHunkPatch:
    def test_extracts_all_hunks(self):
        pr_file = PRFile(
            filename="src/main.py",
            status="modified",
            additions=5,
            deletions=1,
            changes=6,
            patch=MULTI_HUNK_PATCH,
        )
        diff = parse_patch(pr_file)

        assert diff.filename == "src/main.py"
        assert diff.status == "modified"
        assert diff.additions == 5
        assert diff.deletions == 1
        assert len(diff.hunks) == 2

    def test_first_hunk_line_numbers(self):
        pr_file = PRFile(
            filename="src/main.py",
            status="modified",
            additions=5,
            deletions=1,
            changes=6,
            patch=MULTI_HUNK_PATCH,
        )
        diff = parse_patch(pr_file)
        h1 = diff.hunks[0]

        assert h1.old_start == 1
        assert h1.old_lines == 7
        assert h1.new_start == 1
        assert h1.new_lines == 8

    def test_second_hunk_line_numbers(self):
        pr_file = PRFile(
            filename="src/main.py",
            status="modified",
            additions=5,
            deletions=1,
            changes=6,
            patch=MULTI_HUNK_PATCH,
        )
        diff = parse_patch(pr_file)
        h2 = diff.hunks[1]

        assert h2.old_start == 20
        assert h2.old_lines == 6
        assert h2.new_start == 21
        assert h2.new_lines == 10

    def test_hunk_lines_contain_additions_and_deletions(self):
        pr_file = PRFile(
            filename="src/main.py",
            status="modified",
            additions=5,
            deletions=1,
            changes=6,
            patch=MULTI_HUNK_PATCH,
        )
        diff = parse_patch(pr_file)
        h1_lines = diff.hunks[0].lines

        additions = [l for l in h1_lines if l.startswith("+")]
        deletions = [l for l in h1_lines if l.startswith("-")]
        context = [l for l in h1_lines if l.startswith(" ")]

        assert len(additions) >= 2  # +import logging, +logging.info(...)
        assert len(deletions) >= 1  # -print("hello")
        assert len(context) >= 1  # context lines with space prefix

    def test_previous_filename_is_none(self):
        pr_file = PRFile(
            filename="src/main.py",
            status="modified",
            additions=5,
            deletions=1,
            changes=6,
            patch=MULTI_HUNK_PATCH,
        )
        diff = parse_patch(pr_file)
        assert diff.previous_filename is None


# ---------------------------------------------------------------------------
# 2. Parse patch with renamed file
# ---------------------------------------------------------------------------


class TestParseRenamedFile:
    def test_rename_preserves_previous_filename(self):
        pr_file = PRFile(
            filename="src/greeting.py",
            status="renamed",
            additions=1,
            deletions=1,
            changes=2,
            patch=RENAME_PATCH,
            previous_filename="src/old_greeting.py",
        )
        diff = parse_patch(pr_file)

        assert diff.filename == "src/greeting.py"
        assert diff.previous_filename == "src/old_greeting.py"
        assert diff.status == "renamed"
        assert len(diff.hunks) == 1

    def test_rename_hunk_has_correct_content(self):
        pr_file = PRFile(
            filename="src/greeting.py",
            status="renamed",
            additions=1,
            deletions=1,
            changes=2,
            patch=RENAME_PATCH,
            previous_filename="src/old_greeting.py",
        )
        diff = parse_patch(pr_file)
        h = diff.hunks[0]

        assert h.old_start == 1
        assert h.new_start == 1
        assert any("-# Old header" in l for l in h.lines)
        assert any("+# New header" in l for l in h.lines)


# ---------------------------------------------------------------------------
# 3. Parse empty / None patch
# ---------------------------------------------------------------------------


class TestParseEmptyPatch:
    def test_none_patch_gives_empty_hunks(self):
        pr_file = PRFile(
            filename="deleted.py",
            status="removed",
            additions=0,
            deletions=100,
            changes=100,
            patch=None,
        )
        diff = parse_patch(pr_file)

        assert diff.filename == "deleted.py"
        assert diff.hunks == []

    def test_empty_string_patch_gives_empty_hunks(self):
        pr_file = PRFile(
            filename="empty.py",
            status="modified",
            additions=0,
            deletions=0,
            changes=0,
            patch="",
        )
        diff = parse_patch(pr_file)
        assert diff.hunks == []


# ---------------------------------------------------------------------------
# 4. Line range calculation from hunks
# ---------------------------------------------------------------------------


class TestLineRangeFromHunk:
    def test_multi_line_hunk(self):
        hunk = DiffHunk(
            header="@@ -1,7 +1,8 @@",
            old_start=1,
            old_lines=7,
            new_start=1,
            new_lines=8,
            lines=[],
        )
        start, end = line_range_from_hunk(hunk)
        assert start == 1
        assert end == 8

    def test_single_line_hunk(self):
        hunk = DiffHunk(
            header="@@ -5 +5 @@",
            old_start=5,
            old_lines=1,
            new_start=5,
            new_lines=1,
            lines=[],
        )
        start, end = line_range_from_hunk(hunk)
        assert start == 5
        assert end == 5

    def test_large_hunk(self):
        hunk = DiffHunk(
            header="@@ -100,50 +110,60 @@",
            old_start=100,
            old_lines=50,
            new_start=110,
            new_lines=60,
            lines=[],
        )
        start, end = line_range_from_hunk(hunk)
        assert start == 110
        assert end == 169  # 110 + 60 - 1

    def test_zero_new_lines_hunk(self):
        """A hunk that removes lines entirely (0 new lines)."""
        hunk = DiffHunk(
            header="@@ -10,5 +10,0 @@",
            old_start=10,
            old_lines=5,
            new_start=10,
            new_lines=0,
            lines=[],
        )
        start, end = line_range_from_hunk(hunk)
        assert start == 10
        assert end == 10  # max(0-1, 0) = 0; 10 + 0 = 10


# ---------------------------------------------------------------------------
# 5. Extract citations from text with multiple formats
# ---------------------------------------------------------------------------


class TestExtractCitations:
    def test_lines_range_format(self):
        text = "The bug is in src/auth.py lines 10-20 where the token check is wrong."
        citations = extract_citations(text)

        assert len(citations) == 1
        assert citations[0].file == "src/auth.py"
        assert citations[0].line_start == 10
        assert citations[0].line_end == 20

    def test_colon_range_format(self):
        text = "See src/auth.py:42-55 for the broken validation logic."
        citations = extract_citations(text)

        assert len(citations) == 1
        assert citations[0].file == "src/auth.py"
        assert citations[0].line_start == 42
        assert citations[0].line_end == 55

    def test_single_line_format(self):
        text = "There is a null dereference at src/main.py line 7."
        citations = extract_citations(text)

        assert len(citations) == 1
        assert citations[0].file == "src/main.py"
        assert citations[0].line_start == 7
        assert citations[0].line_end == 7

    def test_multiple_citations_in_text(self):
        text = (
            "Found issues in src/auth.py lines 10-20 and src/auth.py:42-55. "
            "Also check src/main.py line 7 for a related problem."
        )
        citations = extract_citations(text)

        assert len(citations) == 3
        files = {c.file for c in citations}
        assert files == {"src/auth.py", "src/main.py"}

    def test_no_citations_in_plain_text(self):
        text = "Everything looks good, no issues found."
        citations = extract_citations(text)
        assert citations == []

    def test_colon_single_line(self):
        text = "Bug at utils/helper.py:99"
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0].line_start == 99
        assert citations[0].line_end == 99


# ---------------------------------------------------------------------------
# 6. Validate citations against parsed diff hunks
# ---------------------------------------------------------------------------


class TestValidateCitations:
    @pytest.fixture()
    def sample_diffs(self) -> list[FileDiff]:
        """Build a realistic FileDiff list from the multi-hunk patch."""
        pr_file = PRFile(
            filename="src/main.py",
            status="modified",
            additions=5,
            deletions=1,
            changes=6,
            patch=MULTI_HUNK_PATCH,
        )
        return [parse_patch(pr_file)]

    def test_citation_inside_hunk_passes(self, sample_diffs):
        # Hunk 1 new range: 1-8, Hunk 2 new range: 21-30
        from review.models import Citation

        citations = [Citation(file="src/main.py", line_start=3, line_end=5)]
        valid = validate_citations(citations, sample_diffs)
        assert len(valid) == 1

    def test_citation_outside_all_hunks_fails(self, sample_diffs):
        from review.models import Citation

        # Lines 12-15 fall between hunk 1 (1-8) and hunk 2 (21-30)
        citations = [Citation(file="src/main.py", line_start=12, line_end=15)]
        valid = validate_citations(citations, sample_diffs)
        assert len(valid) == 0

    def test_citation_for_wrong_file_fails(self, sample_diffs):
        from review.models import Citation

        citations = [Citation(file="src/other.py", line_start=1, line_end=5)]
        valid = validate_citations(citations, sample_diffs)
        assert len(valid) == 0

    def test_citation_overlapping_hunk_edge_passes(self, sample_diffs):
        from review.models import Citation

        # Citation spans into hunk 2 (starts at 21)
        citations = [Citation(file="src/main.py", line_start=19, line_end=22)]
        valid = validate_citations(citations, sample_diffs)
        assert len(valid) == 1

    def test_mixed_valid_and_invalid(self, sample_diffs):
        from review.models import Citation

        citations = [
            Citation(file="src/main.py", line_start=1, line_end=3),   # valid (hunk 1)
            Citation(file="src/main.py", line_start=12, line_end=15), # invalid (gap)
            Citation(file="src/main.py", line_start=25, line_end=28), # valid (hunk 2)
        ]
        valid = validate_citations(citations, sample_diffs)
        assert len(valid) == 2


# ---------------------------------------------------------------------------
# 7. Full pipeline: raw patch -> parse -> extract citations -> validate
# ---------------------------------------------------------------------------


class TestFullDiffCitationPipeline:
    def test_end_to_end_pipeline(self):
        pr_file = PRFile(
            filename="src/auth.py",
            status="modified",
            additions=4,
            deletions=2,
            changes=6,
            patch=(
                "@@ -10,7 +10,9 @@\n"
                " def validate_token(token):\n"
                "-    if token is None:\n"
                "-        return False\n"
                "+    if not token:\n"
                "+        raise ValueError('Token required')\n"
                "+    if len(token) < 32:\n"
                "+        raise ValueError('Token too short')\n"
                "     return True\n"
                "     \n"
            ),
        )

        # Step 1: parse diff
        diff = parse_patch(pr_file)
        assert diff.filename == "src/auth.py"
        assert len(diff.hunks) == 1

        hunk = diff.hunks[0]
        assert hunk.new_start == 10
        assert hunk.new_lines == 9

        # Step 2: extract citations from a review finding
        review_text = (
            "P1 bug: The validation in src/auth.py lines 11-14 raises ValueError "
            "but the caller in src/main.py:42-45 does not handle it."
        )
        citations = extract_citations(review_text)
        assert len(citations) == 2

        # Step 3: validate citations against diff
        valid = validate_citations(citations, [diff])
        # src/auth.py 11-14 is inside hunk (10-18), src/main.py is not in diff
        assert len(valid) == 1
        assert valid[0].file == "src/auth.py"

    def test_pipeline_with_multiple_files(self):
        """Parse two files, extract citations referencing both, validate."""
        file_a = PRFile(
            filename="src/db.py",
            status="modified",
            additions=3,
            deletions=1,
            changes=4,
            patch=(
                "@@ -50,4 +50,6 @@\n"
                " def connect():\n"
                "-    return None\n"
                "+    pool = create_pool()\n"
                "+    pool.initialize()\n"
                "+    return pool\n"
            ),
        )
        file_b = PRFile(
            filename="src/cache.py",
            status="added",
            additions=10,
            deletions=0,
            changes=10,
            patch=(
                "@@ -0,0 +1,10 @@\n"
                "+import redis\n"
                "+\n"
                "+class Cache:\n"
                "+    def __init__(self):\n"
                "+        self.client = redis.Redis()\n"
                "+\n"
                "+    def get(self, key):\n"
                "+        return self.client.get(key)\n"
                "+\n"
                "+    def set(self, key, value):\n"
            ),
        )

        diffs = [parse_patch(file_a), parse_patch(file_b)]

        review_text = (
            "src/db.py lines 51-53 creates pool without error handling. "
            "src/cache.py:3-5 should accept host parameter. "
            "src/unrelated.py lines 1-10 is not in this PR."
        )
        citations = extract_citations(review_text)
        assert len(citations) == 3

        valid = validate_citations(citations, diffs)
        assert len(valid) == 2
        valid_files = {c.file for c in valid}
        assert valid_files == {"src/db.py", "src/cache.py"}


# ---------------------------------------------------------------------------
# 8. PR URL parsing
# ---------------------------------------------------------------------------


class TestParsePRUrl:
    def test_basic_url(self):
        ref = parse_pr_url("https://github.com/octocat/hello-world/pull/42")
        assert ref.owner == "octocat"
        assert ref.repo == "hello-world"
        assert ref.number == 42

    def test_url_with_files_path(self):
        ref = parse_pr_url("https://github.com/org/repo/pull/123/files")
        assert ref.owner == "org"
        assert ref.repo == "repo"
        assert ref.number == 123

    def test_url_with_fragment(self):
        ref = parse_pr_url(
            "https://github.com/owner/repo/pull/999#issuecomment-123456"
        )
        assert ref.owner == "owner"
        assert ref.repo == "repo"
        assert ref.number == 999

    def test_url_with_trailing_whitespace(self):
        ref = parse_pr_url("  https://github.com/a/b/pull/1  ")
        assert ref.owner == "a"
        assert ref.repo == "b"
        assert ref.number == 1

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub PR URL"):
            parse_pr_url("https://example.com/not-a-pr")

    def test_non_github_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub PR URL"):
            parse_pr_url("https://gitlab.com/owner/repo/merge_requests/5")

    def test_issue_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub PR URL"):
            parse_pr_url("https://github.com/owner/repo/issues/10")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_pr_url("")

    def test_http_url(self):
        ref = parse_pr_url("http://github.com/owner/repo/pull/7")
        assert ref.number == 7


# ---------------------------------------------------------------------------
# 9. Path sanitization
# ---------------------------------------------------------------------------


class TestSanitizePath:
    def test_normal_path(self):
        assert sanitize_path("src/main.py") == "src/main.py"

    def test_strips_leading_slash(self):
        assert sanitize_path("/src/main.py") == "src/main.py"

    def test_strips_whitespace(self):
        assert sanitize_path("  src/main.py  ") == "src/main.py"

    def test_traversal_attack_raises(self):
        with pytest.raises(ValueError, match="Path traversal"):
            sanitize_path("../../etc/passwd")

    def test_mid_path_traversal_raises(self):
        with pytest.raises(ValueError, match="Path traversal"):
            sanitize_path("src/../../etc/passwd")

    def test_unsafe_characters_raises(self):
        with pytest.raises(ValueError, match="Unsafe characters"):
            sanitize_path("src/main;rm -rf /.py")

    def test_shell_injection_raises(self):
        with pytest.raises(ValueError, match="Unsafe characters"):
            sanitize_path("src/$(whoami).py")

    def test_backtick_injection_raises(self):
        with pytest.raises(ValueError, match="Unsafe characters"):
            sanitize_path("src/`id`.py")

    def test_dashes_and_underscores_allowed(self):
        assert sanitize_path("src/my-module/some_file.py") == "src/my-module/some_file.py"

    def test_deeply_nested_path(self):
        result = sanitize_path("a/b/c/d/e/f/g.txt")
        assert result == "a/b/c/d/e/f/g.txt"
