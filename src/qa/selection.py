"""Code selection helpers — extract content from diffs by selection mode."""

from __future__ import annotations

from github.models import FileDiff
from qa.models import CodeSelection, SelectionMode


def select_line(diffs: list[FileDiff], file: str, line: int) -> CodeSelection | None:
    """Select a single line from a file's diff."""
    for diff in diffs:
        if diff.filename != file:
            continue
        for hunk in diff.hunks:
            if hunk.new_start <= line <= hunk.new_start + hunk.new_lines:
                offset = line - hunk.new_start
                lines = hunk.lines
                content = lines[offset] if offset < len(lines) else ""
                return CodeSelection(
                    mode=SelectionMode.LINE,
                    file=file,
                    content=content,
                    line_start=line,
                    line_end=line,
                )
    return None


def select_range(diffs: list[FileDiff], file: str, start: int, end: int) -> CodeSelection | None:
    """Select a line range from a file's diff."""
    for diff in diffs:
        if diff.filename != file:
            continue
        collected: list[str] = []
        for hunk in diff.hunks:
            hunk_start = hunk.new_start
            hunk_end = hunk.new_start + hunk.new_lines - 1
            if hunk_start > end or hunk_end < start:
                continue
            current_line = hunk_start
            for raw_line in hunk.lines:
                if start <= current_line <= end:
                    collected.append(raw_line)
                if not raw_line.startswith("-"):
                    current_line += 1
        if collected:
            return CodeSelection(
                mode=SelectionMode.RANGE,
                file=file,
                content="\n".join(collected),
                line_start=start,
                line_end=end,
            )
    return None


def select_hunk(diffs: list[FileDiff], file: str, hunk_index: int = 0) -> CodeSelection | None:
    """Select a full diff hunk by index."""
    for diff in diffs:
        if diff.filename != file:
            continue
        if hunk_index >= len(diff.hunks):
            return None
        hunk = diff.hunks[hunk_index]
        return CodeSelection(
            mode=SelectionMode.HUNK,
            file=file,
            content="\n".join(hunk.lines),
            line_start=hunk.new_start,
            line_end=hunk.new_start + hunk.new_lines - 1,
            hunk_header=hunk.header,
        )
    return None


def select_file(diffs: list[FileDiff], file: str) -> CodeSelection | None:
    """Select all hunks from a single file."""
    for diff in diffs:
        if diff.filename != file:
            continue
        all_lines: list[str] = []
        for hunk in diff.hunks:
            all_lines.append(hunk.header)
            all_lines.extend(hunk.lines)
        return CodeSelection(
            mode=SelectionMode.FILE,
            file=file,
            content="\n".join(all_lines),
        )
    return None


def select_changeset(diffs: list[FileDiff]) -> CodeSelection:
    """Select the entire changeset (all files)."""
    lines: list[str] = []
    for diff in diffs:
        lines.append(f"### {diff.filename} [{diff.status}]")
        for hunk in diff.hunks:
            lines.append(hunk.header)
            lines.extend(hunk.lines)
    return CodeSelection(
        mode=SelectionMode.CHANGESET,
        file="(all files)",
        content="\n".join(lines),
    )


def format_selection_context(selection: CodeSelection | None) -> str:
    """Format a code selection for injection into the Q&A prompt."""
    if not selection:
        return "(no code selected)"
    return f"**Selected:** {selection.describe()}\n" f"```\n{selection.content[:3000]}\n```"
