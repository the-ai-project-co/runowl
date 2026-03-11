"""Citation extraction and validation against visible diff hunks."""

from __future__ import annotations

import re

from github.diff import line_range_from_hunk
from github.models import FileDiff
from review.models import Citation

# Matches patterns like:
#   src/auth.py lines 10-20
#   src/auth.py line 10
#   src/auth.py:10-20
#   src/auth.py:10
_CITATION_RE = re.compile(
    r"(?P<file>[\w/\-_.]+\.\w+)"
    r"(?:\s+lines?\s+(?P<start1>\d+)(?:[–\-](?P<end1>\d+))?"
    r"|\:(?P<start2>\d+)(?:-(?P<end2>\d+))?)"
)


def extract_citations(text: str) -> list[Citation]:
    """Extract all citation references from a block of agent output text."""
    citations = []
    for m in _CITATION_RE.finditer(text):
        file = m.group("file")
        start = int(m.group("start1") or m.group("start2") or 0)
        end_raw = m.group("end1") or m.group("end2")
        end = int(end_raw) if end_raw else start
        if start > 0:
            citations.append(Citation(file=file, line_start=start, line_end=end))
    return citations


def constrain_to_diff(citation: Citation, diffs: list[FileDiff]) -> Citation | None:
    """Return the citation if it falls within a visible diff hunk, else None.

    This ensures the review agent only cites lines that actually appear
    in the PR diff, not arbitrary lines from the file.
    """
    for diff in diffs:
        if diff.filename != citation.file:
            continue
        for hunk in diff.hunks:
            hunk_start, hunk_end = line_range_from_hunk(hunk)
            # Accept if citation overlaps the hunk range
            if citation.line_start <= hunk_end and citation.line_end >= hunk_start:
                return citation
    return None


def validate_citations(citations: list[Citation], diffs: list[FileDiff]) -> list[Citation]:
    """Filter citations to only those visible in the diff hunks."""
    valid = []
    for c in citations:
        constrained = constrain_to_diff(c, diffs)
        if constrained:
            valid.append(constrained)
    return valid
