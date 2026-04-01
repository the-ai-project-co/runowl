"""Integration tests for the Recursive Reasoning Engine (Gemini mocked)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from github.models import DirEntry, FileContent, PRRef, SearchResult
from reasoning.engine import ReasoningEngine
from reasoning.models import ConversationMessage, ReasoningStep, StepType

PR_REF = PRRef(owner="acme", repo="widget", number=5)


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
        steps: list[ReasoningStep] = []
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
