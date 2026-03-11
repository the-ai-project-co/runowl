"""Parse unified diff patches into structured DiffHunk objects."""

import re

from github.models import DiffHunk, FileDiff, PRFile

_HUNK_HEADER_RE = re.compile(
    r"@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@"
)


def parse_patch(file: PRFile) -> FileDiff:
    """Parse a PR file's unified diff patch into structured hunks."""
    hunks: list[DiffHunk] = []

    if file.patch:
        current_hunk: DiffHunk | None = None
        for line in file.patch.splitlines():
            m = _HUNK_HEADER_RE.match(line)
            if m:
                if current_hunk is not None:
                    hunks.append(current_hunk)
                current_hunk = DiffHunk(
                    header=line,
                    old_start=int(m.group("old_start")),
                    old_lines=int(m.group("old_lines") or "1"),
                    new_start=int(m.group("new_start")),
                    new_lines=int(m.group("new_lines") or "1"),
                    lines=[],
                )
            elif current_hunk is not None:
                current_hunk.lines.append(line)
        if current_hunk is not None:
            hunks.append(current_hunk)

    return FileDiff(
        filename=file.filename,
        status=file.status,
        additions=file.additions,
        deletions=file.deletions,
        hunks=hunks,
        previous_filename=file.previous_filename,
    )


def line_range_from_hunk(hunk: DiffHunk) -> tuple[int, int]:
    """Return the (start, end) line range in the new file for a hunk."""
    return hunk.new_start, hunk.new_start + max(hunk.new_lines - 1, 0)
