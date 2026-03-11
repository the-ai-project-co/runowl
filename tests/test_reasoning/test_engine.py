"""Tests for the Recursive Reasoning Engine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from github.models import DirEntry, FileContent, PRMetadata, PRRef, SearchResult
from reasoning.context import build_diff_context, build_pr_summary
from reasoning.engine import ReasoningEngine
from reasoning.models import ConversationMessage, ReasoningStep, ReasoningTrace, StepType
from reasoning.prompts import CONTEXT_WINDOW_DIFF_LIMIT

PR_REF = PRRef(owner="acme", repo="widget", number=5)


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


# ── ReasoningEngine tests (Gemini mocked) ─────────────────────────────────────


def _mock_text_response(text: str) -> MagicMock:
    """Build a mock Gemini response that returns plain text (no tool calls)."""
    part = MagicMock()
    part.text = text
    part.function_call = None

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _mock_tool_then_text(tool_name: str, tool_args: dict, final_text: str):
    """Build two mock responses: first a tool call, then a text response."""
    # First response — tool call
    fc = MagicMock()
    fc.name = tool_name
    fc.args = tool_args

    tool_part = MagicMock()
    tool_part.function_call = fc
    tool_part.text = None

    tool_content = MagicMock()
    tool_content.parts = [tool_part]

    tool_candidate = MagicMock()
    tool_candidate.content = tool_content

    tool_response = MagicMock()
    tool_response.candidates = [tool_candidate]

    # Second response — text
    text_response = _mock_text_response(final_text)
    return [tool_response, text_response]


@pytest.fixture
def mock_gh() -> MagicMock:
    gh = MagicMock()
    gh.get_file = AsyncMock(
        return_value=FileContent(
            path="src/a.py", content="print('hi')", sha="aaa", size=11, ref="abc"
        )
    )
    gh.list_dir = AsyncMock(return_value=[DirEntry(name="a.py", path="src/a.py", type="file")])
    gh.search_code = AsyncMock(
        return_value=[SearchResult(path="src/a.py", repository="acme/widget", score=0.9)]
    )
    return gh


class TestReasoningEngine:
    async def test_returns_text_output(self, mock_gh: MagicMock) -> None:
        engine = ReasoningEngine(github_client=mock_gh, api_key="test")
        with patch.object(
            engine._gemini.models,
            "generate_content",
            return_value=_mock_text_response("Review complete."),
        ):
            result = await engine.run("Review this PR", PR_REF, "abc123")
        assert result.success
        assert "Review complete." in result.output

    async def test_tool_call_then_text(self, mock_gh: MagicMock) -> None:
        engine = ReasoningEngine(github_client=mock_gh, api_key="test")
        responses = _mock_tool_then_text("FETCH_FILE", {"path": "src/a.py"}, "Found issues.")
        with patch.object(engine._gemini.models, "generate_content", side_effect=responses):
            result = await engine.run("Review this PR", PR_REF, "abc123")
        assert result.success
        assert "Found issues." in result.output
        assert result.trace.tool_calls == 1

    async def test_step_callback_called(self, mock_gh: MagicMock) -> None:
        steps = []
        engine = ReasoningEngine(
            github_client=mock_gh,
            api_key="test",
            step_callback=lambda s: steps.append(s),
        )
        with patch.object(
            engine._gemini.models, "generate_content", return_value=_mock_text_response("Done.")
        ):
            await engine.run("Review this PR", PR_REF, "abc123")
        assert any(s.type == StepType.OUTPUT for s in steps)

    async def test_gemini_error_returns_failure(self, mock_gh: MagicMock) -> None:
        engine = ReasoningEngine(github_client=mock_gh, api_key="test")
        with patch.object(
            engine._gemini.models, "generate_content", side_effect=Exception("API down")
        ):
            result = await engine.run("Review", PR_REF, "abc123")
        assert not result.success
        assert result.error is not None

    async def test_conversation_history_appended(self, mock_gh: MagicMock) -> None:
        engine = ReasoningEngine(github_client=mock_gh, api_key="test")
        prior = [ConversationMessage(role="user", content="earlier question")]
        with patch.object(
            engine._gemini.models, "generate_content", return_value=_mock_text_response("Answer.")
        ):
            result = await engine.run("Follow-up", PR_REF, "abc123", conversation=prior)
        # Prior message + new question + model answer = 3
        assert len(result.conversation) == 3

    async def test_trace_saved_to_disk(self, mock_gh: MagicMock, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        engine = ReasoningEngine(github_client=mock_gh, api_key="test")
        with patch.object(
            engine._gemini.models, "generate_content", return_value=_mock_text_response("Done.")
        ):
            await engine.run("Review", PR_REF, "abc123")
        trace_file = tmp_path / ".runowl" / "traces" / "acme__widget__pr5.json"
        assert trace_file.exists()
