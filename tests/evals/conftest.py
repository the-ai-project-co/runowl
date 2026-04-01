"""Shared fixtures and scoring helpers for AI evaluation tests."""

import pytest
from dataclasses import dataclass, field
from github.models import DiffHunk, FileDiff, PRFile, PRMetadata, PRRef


@dataclass
class EvalScore:
    """Accumulates correct/total counts for precision/recall reporting."""
    name: str
    correct: int = 0
    total: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        tp = self.correct
        fp = self.false_positives
        return tp / (tp + fp) if (tp + fp) else 1.0

    @property
    def recall(self) -> float:
        tp = self.correct
        fn = self.false_negatives
        return tp / (tp + fn) if (tp + fn) else 1.0

    def record(self, expected: bool, actual: bool) -> None:
        self.total += 1
        if expected == actual:
            self.correct += 1
        if actual and not expected:
            self.false_positives += 1
        if not actual and expected:
            self.false_negatives += 1


def make_diff(filename: str, added_lines: list[str], start: int = 1, status: str = "added") -> FileDiff:
    """Build a FileDiff with added lines for testing."""
    raw = [f"+{line}" for line in added_lines]
    hunk = DiffHunk(
        header=f"@@ -0,0 +{start},{len(added_lines)} @@",
        old_start=0,
        old_lines=0,
        new_start=start,
        new_lines=len(added_lines),
        lines=raw,
    )
    return FileDiff(
        filename=filename,
        status=status,
        additions=len(added_lines),
        deletions=0,
        hunks=[hunk],
    )


def make_multi_hunk_diff(
    filename: str,
    hunks: list[tuple[int, list[str]]],
    status: str = "modified",
) -> FileDiff:
    """Build a FileDiff with multiple hunks. Each tuple is (start_line, lines)."""
    diff_hunks = []
    total_add = 0
    for start, lines in hunks:
        raw = [f"+{line}" for line in lines]
        diff_hunks.append(DiffHunk(
            header=f"@@ -0,0 +{start},{len(lines)} @@",
            old_start=0,
            old_lines=0,
            new_start=start,
            new_lines=len(lines),
            lines=raw,
        ))
        total_add += len(lines)
    return FileDiff(
        filename=filename,
        status=status,
        additions=total_add,
        deletions=0,
        hunks=diff_hunks,
    )


def make_pr_metadata(**kwargs) -> PRMetadata:
    """Build PRMetadata with sensible defaults."""
    defaults = dict(
        number=1,
        title="Test PR",
        body="Test body",
        author="testuser",
        base_branch="main",
        head_branch="feature/test",
        head_sha="abc123",
        base_sha="def456",
        state="open",
        commits=[],
        files=[],
        additions=10,
        deletions=5,
        changed_files=1,
    )
    defaults.update(kwargs)
    return PRMetadata(**defaults)


PR_REF = PRRef(owner="test", repo="repo", number=1)
