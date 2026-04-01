"""Tests for code selection helpers."""

from github.models import DiffHunk, FileDiff
from qa.models import SelectionMode
from qa.selection import (
    format_selection_context,
    select_changeset,
    select_file,
    select_hunk,
    select_line,
    select_range,
)


def _make_diff(
    filename: str = "src/auth.py",
    hunk_start: int = 10,
    lines: list[str] | None = None,
) -> FileDiff:
    hunk_lines = lines or [" ctx", "-old_line", "+new_line", " end"]
    hunk = DiffHunk(
        header=f"@@ -{hunk_start},4 +{hunk_start},4 @@",
        old_start=hunk_start,
        old_lines=4,
        new_start=hunk_start,
        new_lines=4,
        lines=hunk_lines,
    )
    return FileDiff(
        filename=filename,
        status="modified",
        additions=1,
        deletions=1,
        hunks=[hunk],
    )


class TestSelectLine:
    def test_returns_selection_for_valid_line(self) -> None:
        diff = _make_diff(hunk_start=10)
        result = select_line([diff], "src/auth.py", 10)
        assert result is not None
        assert result.mode == SelectionMode.LINE
        assert result.line_start == 10

    def test_returns_none_for_wrong_file(self) -> None:
        diff = _make_diff()
        assert select_line([diff], "src/other.py", 10) is None

    def test_returns_none_for_line_outside_hunk(self) -> None:
        diff = _make_diff(hunk_start=10)
        assert select_line([diff], "src/auth.py", 100) is None

    def test_content_extracted(self) -> None:
        diff = _make_diff(hunk_start=5, lines=["+first", "+second", "+third"])
        result = select_line([diff], "src/auth.py", 5)
        assert result is not None
        assert result.content == "+first"


class TestSelectRange:
    def test_returns_selection_for_valid_range(self) -> None:
        diff = _make_diff(hunk_start=10)
        result = select_range([diff], "src/auth.py", 10, 12)
        assert result is not None
        assert result.mode == SelectionMode.RANGE
        assert result.line_start == 10
        assert result.line_end == 12

    def test_returns_none_for_wrong_file(self) -> None:
        diff = _make_diff()
        assert select_range([diff], "src/other.py", 10, 12) is None

    def test_returns_none_when_no_overlap(self) -> None:
        diff = _make_diff(hunk_start=10)
        assert select_range([diff], "src/auth.py", 50, 60) is None

    def test_content_contains_lines_in_range(self) -> None:
        diff = _make_diff(hunk_start=1, lines=["+a", "+b", "+c"])
        result = select_range([diff], "src/auth.py", 1, 2)
        assert result is not None
        assert "+a" in result.content


class TestSelectHunk:
    def test_returns_first_hunk(self) -> None:
        diff = _make_diff()
        result = select_hunk([diff], "src/auth.py", 0)
        assert result is not None
        assert result.mode == SelectionMode.HUNK
        assert result.hunk_header is not None

    def test_returns_none_for_out_of_bounds_index(self) -> None:
        diff = _make_diff()
        assert select_hunk([diff], "src/auth.py", 5) is None

    def test_returns_none_for_wrong_file(self) -> None:
        diff = _make_diff()
        assert select_hunk([diff], "src/other.py", 0) is None

    def test_hunk_content_contains_lines(self) -> None:
        diff = _make_diff(lines=["+added_line", "-removed_line"])
        result = select_hunk([diff], "src/auth.py", 0)
        assert result is not None
        assert "+added_line" in result.content


class TestSelectFile:
    def test_returns_file_selection(self) -> None:
        diff = _make_diff()
        result = select_file([diff], "src/auth.py")
        assert result is not None
        assert result.mode == SelectionMode.FILE
        assert result.file == "src/auth.py"

    def test_returns_none_for_missing_file(self) -> None:
        diff = _make_diff()
        assert select_file([diff], "src/missing.py") is None

    def test_content_includes_hunk_header(self) -> None:
        diff = _make_diff(hunk_start=10)
        result = select_file([diff], "src/auth.py")
        assert result is not None
        assert "@@ " in result.content


class TestSelectChangeset:
    def test_includes_all_files(self) -> None:
        diffs = [_make_diff("src/a.py"), _make_diff("src/b.py")]
        result = select_changeset(diffs)
        assert result.mode == SelectionMode.CHANGESET
        assert "src/a.py" in result.content
        assert "src/b.py" in result.content

    def test_empty_diffs(self) -> None:
        result = select_changeset([])
        assert result.content == ""


class TestFormatSelectionContext:
    def test_none_selection(self) -> None:
        out = format_selection_context(None)
        assert "no code selected" in out

    def test_formats_file_selection(self) -> None:
        diff = _make_diff()
        sel = select_file([diff], "src/auth.py")
        out = format_selection_context(sel)
        assert "src/auth.py" in out
        assert "```" in out

    def test_content_truncated_at_3000(self) -> None:
        long_content = "x" * 5000
        from qa.models import CodeSelection

        sel = CodeSelection(mode=SelectionMode.FILE, file="f.py", content=long_content)
        out = format_selection_context(sel)
        assert len(out) < 4000
