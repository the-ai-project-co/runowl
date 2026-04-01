"""Unit tests for reasoning context builders and trace models."""

from github.models import PRMetadata
from reasoning.context import build_diff_context, build_pr_summary
from reasoning.models import ReasoningStep, ReasoningTrace, StepType
from reasoning.prompts import CONTEXT_WINDOW_DIFF_LIMIT


def _make_metadata(**kwargs) -> PRMetadata:
    defaults = dict(
        number=5,
        title="Add login endpoint",
        body="Adds /login route",
        author="alice",
        base_branch="main",
        head_branch="feat/login",
        head_sha="abc123",
        base_sha="def456",
        state="open",
        commits=[],
        files=[],
        additions=30,
        deletions=5,
        changed_files=2,
    )
    defaults.update(kwargs)
    return PRMetadata(**defaults)


# ── Context builder tests ──────────────────────────────────────────────────────


class TestBuildPrSummary:
    def test_contains_title(self) -> None:
        meta = _make_metadata()
        summary = build_pr_summary(meta)
        assert "Add login endpoint" in summary

    def test_contains_author(self) -> None:
        meta = _make_metadata()
        assert "alice" in build_pr_summary(meta)

    def test_contains_branch_info(self) -> None:
        meta = _make_metadata()
        summary = build_pr_summary(meta)
        assert "feat/login" in summary
        assert "main" in summary

    def test_no_body_shows_none(self) -> None:
        meta = _make_metadata(body=None)
        assert "(none)" in build_pr_summary(meta)


class TestBuildDiffContext:
    def _make_diff(self, filename: str = "src/a.py", status: str = "modified"):
        from github.models import DiffHunk, FileDiff

        return FileDiff(
            filename=filename,
            status=status,
            additions=2,
            deletions=1,
            hunks=[
                DiffHunk(
                    header="@@ -1,3 +1,4 @@",
                    old_start=1,
                    old_lines=3,
                    new_start=1,
                    new_lines=4,
                    lines=[" ctx", "-old", "+new"],
                )
            ],
        )

    def test_filename_in_output(self) -> None:
        diff = self._make_diff()
        out = build_diff_context(_make_metadata(), [diff])
        assert "src/a.py" in out

    def test_hunk_header_in_output(self) -> None:
        diff = self._make_diff()
        out = build_diff_context(_make_metadata(), [diff])
        assert "@@ -1,3 +1,4 @@" in out

    def test_removed_file_no_patch(self) -> None:
        from github.models import FileDiff

        diff = FileDiff(filename="old.py", status="removed", additions=0, deletions=10, hunks=[])
        out = build_diff_context(_make_metadata(), [diff])
        assert "deleted" in out

    def test_overflow_files_noted(self) -> None:
        diffs = [self._make_diff(f"src/f{i}.py") for i in range(CONTEXT_WINDOW_DIFF_LIMIT + 3)]
        out = build_diff_context(_make_metadata(), diffs)
        assert "additional files" in out
        assert "FETCH_FILE" in out

    def test_within_limit_no_overflow_message(self) -> None:
        diffs = [self._make_diff(f"src/f{i}.py") for i in range(5)]
        out = build_diff_context(_make_metadata(), diffs)
        assert "additional files" not in out


# ── ReasoningTrace tests ───────────────────────────────────────────────────────


class TestReasoningTrace:
    def test_llm_call_increments_counter(self) -> None:
        trace = ReasoningTrace()
        trace.add_step(ReasoningStep(type=StepType.LLM_CALL, content="x", iteration=0))
        assert trace.llm_calls == 1

    def test_tool_call_increments_counter(self) -> None:
        trace = ReasoningTrace()
        trace.add_step(ReasoningStep(type=StepType.TOOL_CALL, content="y", iteration=0))
        assert trace.tool_calls == 1

    def test_reasoning_step_does_not_increment_llm(self) -> None:
        trace = ReasoningTrace()
        trace.add_step(ReasoningStep(type=StepType.REASONING, content="z", iteration=0))
        assert trace.llm_calls == 0
        assert trace.tool_calls == 0
