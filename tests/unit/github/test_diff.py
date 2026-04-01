"""Tests for diff patch parser."""

from github.diff import line_range_from_hunk, parse_patch
from github.models import PRFile


def _make_file(patch: str | None = None) -> PRFile:
    return PRFile(
        filename="src/foo.py",
        status="modified",
        additions=3,
        deletions=1,
        changes=4,
        patch=patch,
    )


class TestParsePatch:
    def test_no_patch_returns_empty_hunks(self) -> None:
        diff = parse_patch(_make_file(patch=None))
        assert diff.hunks == []

    def test_single_hunk_parsed(self) -> None:
        patch = "@@ -1,4 +1,6 @@\n context\n-removed\n+added\n+extra\n context"
        diff = parse_patch(_make_file(patch=patch))
        assert len(diff.hunks) == 1
        hunk = diff.hunks[0]
        assert hunk.old_start == 1
        assert hunk.old_lines == 4
        assert hunk.new_start == 1
        assert hunk.new_lines == 6

    def test_hunk_lines_captured(self) -> None:
        patch = "@@ -1,2 +1,3 @@\n context\n-old\n+new\n+extra"
        diff = parse_patch(_make_file(patch=patch))
        assert " context" in diff.hunks[0].lines
        assert "-old" in diff.hunks[0].lines
        assert "+new" in diff.hunks[0].lines

    def test_multiple_hunks(self) -> None:
        patch = "@@ -1,2 +1,2 @@\n-a\n+b\n" "@@ -10,2 +10,2 @@\n-c\n+d\n"
        diff = parse_patch(_make_file(patch=patch))
        assert len(diff.hunks) == 2
        assert diff.hunks[1].old_start == 10

    def test_filename_and_status_preserved(self) -> None:
        diff = parse_patch(_make_file(patch="@@ -1 +1 @@\n+line"))
        assert diff.filename == "src/foo.py"
        assert diff.status == "modified"

    def test_previous_filename_propagated(self) -> None:
        f = PRFile(
            filename="new.py",
            status="renamed",
            additions=0,
            deletions=0,
            changes=0,
            previous_filename="old.py",
        )
        diff = parse_patch(f)
        assert diff.previous_filename == "old.py"


class TestLineRange:
    def test_single_line_hunk(self) -> None:
        from github.models import DiffHunk

        hunk = DiffHunk(
            header="@@ -1 +1 @@",
            old_start=1,
            old_lines=1,
            new_start=5,
            new_lines=1,
            lines=[],
        )
        start, end = line_range_from_hunk(hunk)
        assert start == 5
        assert end == 5

    def test_multi_line_hunk(self) -> None:
        from github.models import DiffHunk

        hunk = DiffHunk(
            header="@@ -1,5 +1,8 @@",
            old_start=1,
            old_lines=5,
            new_start=10,
            new_lines=8,
            lines=[],
        )
        start, end = line_range_from_hunk(hunk)
        assert start == 10
        assert end == 17
