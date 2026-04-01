"""AI evals for the reasoning engine's convergence behavior, tool dispatch, and trace quality."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reasoning.engine import ReasoningEngine
from reasoning.models import (
    ReasoningStep,
    ReasoningTrace,
    StepType,
    RLMResult,
    ConversationMessage,
)
from github.models import PRRef, PRMetadata, FileContent, DirEntry, SearchResult
from sandbox.limits import MAX_ITERATIONS, MAX_LLM_CALLS, ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ref() -> PRRef:
    return PRRef(owner="acme", repo="api", number=42)


def _mock_gh() -> AsyncMock:
    """Build a mock GitHub client with canned tool responses."""
    gh = AsyncMock()
    gh.get_file = AsyncMock(return_value=FileContent(
        path="src/auth.py",
        content="def authenticate():\n    return True\n",
        sha="abc123",
        size=40,
        ref="abc123",
    ))
    gh.list_dir = AsyncMock(return_value=[
        DirEntry(name="auth.py", path="src/auth.py", type="file", size=40, sha="a1"),
        DirEntry(name="db.py", path="src/db.py", type="file", size=120, sha="a2"),
        DirEntry(name="tests", path="src/tests", type="dir"),
    ])
    gh.search_code = AsyncMock(return_value=[
        SearchResult(path="src/auth.py", repository="acme/api", score=0.95),
        SearchResult(path="src/utils.py", repository="acme/api", score=0.80),
    ])
    return gh


def _text_part(text: str) -> MagicMock:
    """Create a mock Gemini Part with text only (no function call)."""
    part = MagicMock()
    part.text = text
    part.function_call = None
    return part


def _tool_part(name: str, args: dict[str, str]) -> MagicMock:
    """Create a mock Gemini Part with a function call."""
    part = MagicMock()
    part.text = None
    fc = MagicMock()
    fc.name = name
    fc.args = args
    part.function_call = fc
    return part


def _gemini_response(parts: list[MagicMock]) -> MagicMock:
    """Build a mock Gemini generate_content response with the given parts."""
    response = MagicMock()
    candidate = MagicMock()
    content = MagicMock()
    content.parts = parts
    candidate.content = content
    response.candidates = [candidate]
    return response


def _empty_response() -> MagicMock:
    """Gemini response with no candidates."""
    response = MagicMock()
    response.candidates = []
    return response


def _build_engine(responses: list[MagicMock]) -> tuple[ReasoningEngine, AsyncMock]:
    """Build a ReasoningEngine with mocked Gemini and GitHub client.

    `responses` is a list of mock Gemini responses returned in order.
    """
    gh = _mock_gh()
    engine = ReasoningEngine(github_client=gh, api_key="fake-key")

    mock_generate = MagicMock(side_effect=responses)
    engine._gemini = MagicMock()
    engine._gemini.models = MagicMock()
    engine._gemini.models.generate_content = mock_generate

    # Disable trace persistence
    engine._save_trace = MagicMock()

    return engine, gh


# ===========================================================================
# 1. Convergence Eval
# ===========================================================================

class TestConvergenceEval:
    """Evaluate that the engine converges in the expected number of iterations."""

    async def test_single_text_response_converges_in_one(self):
        """0 tool calls, just text -> 1 iteration."""
        resp = _gemini_response([_text_part("LGTM, no issues.")])
        engine, _ = _build_engine([resp])
        result = await engine.run("Review this PR", _make_ref(), "abc123")
        assert result.success
        assert result.output == "LGTM, no issues."
        assert result.trace.iterations == 1

    async def test_one_tool_call_then_text(self):
        """1 tool call + 1 text -> converges in 2 iterations."""
        tool_resp = _gemini_response([_tool_part("FETCH_FILE", {"path": "src/auth.py"})])
        text_resp = _gemini_response([_text_part("Found the auth module.")])
        engine, _ = _build_engine([tool_resp, text_resp])
        result = await engine.run("Check auth", _make_ref(), "abc123")
        assert result.success
        assert result.trace.iterations == 2
        assert result.trace.tool_calls == 1
        assert result.trace.llm_calls == 2  # one per iteration

    async def test_three_tool_calls_then_text(self):
        """3 sequential tool calls + 1 text -> 4 iterations."""
        resps = [
            _gemini_response([_tool_part("FETCH_FILE", {"path": "src/auth.py"})]),
            _gemini_response([_tool_part("LIST_DIR", {"path": "src/"})]),
            _gemini_response([_tool_part("SEARCH_CODE", {"query": "authenticate"})]),
            _gemini_response([_text_part("Review complete.")]),
        ]
        engine, _ = _build_engine(resps)
        result = await engine.run("Deep review", _make_ref(), "abc123")
        assert result.success
        assert result.trace.iterations == 4
        assert result.trace.tool_calls == 3

    async def test_tool_results_fed_back_to_model(self):
        """Verify conversation grows with tool results between iterations."""
        tool_resp = _gemini_response([_tool_part("FETCH_FILE", {"path": "src/auth.py"})])
        text_resp = _gemini_response([_text_part("Done.")])
        engine, _ = _build_engine([tool_resp, text_resp])
        result = await engine.run("Q", _make_ref(), "abc123")
        # Conversation: user prompt + model tool call + user tool result + model text
        assert len(result.conversation) == 4
        # The tool result message should contain the file content
        tool_result_msg = result.conversation[2]
        assert tool_result_msg.role == "user"
        assert "FETCH_FILE" in tool_result_msg.content

    async def test_text_only_conversation_is_minimal(self):
        """Pure text response should have exactly 2 conversation messages."""
        resp = _gemini_response([_text_part("All good.")])
        engine, _ = _build_engine([resp])
        result = await engine.run("Review", _make_ref(), "abc123")
        # user prompt + model text
        assert len(result.conversation) == 2


# ===========================================================================
# 2. Trace Quality Eval
# ===========================================================================

class TestTraceQualityEval:
    """Evaluate trace object correctness for various execution paths."""

    async def test_text_only_has_llm_call_and_output_steps(self):
        resp = _gemini_response([_text_part("Looks good.")])
        engine, _ = _build_engine([resp])
        result = await engine.run("Review", _make_ref(), "abc123")
        step_types = [s.type for s in result.trace.steps]
        assert StepType.LLM_CALL in step_types
        assert StepType.OUTPUT in step_types

    async def test_tool_call_step_present(self):
        tool_resp = _gemini_response([_tool_part("FETCH_FILE", {"path": "a.py"})])
        text_resp = _gemini_response([_text_part("Done.")])
        engine, _ = _build_engine([tool_resp, text_resp])
        result = await engine.run("Q", _make_ref(), "abc123")
        step_types = [s.type for s in result.trace.steps]
        assert StepType.TOOL_CALL in step_types

    async def test_llm_calls_count_matches_steps(self):
        tool_resp = _gemini_response([_tool_part("LIST_DIR", {"path": "src/"})]),
        text_resp = _gemini_response([_text_part("Done.")])
        engine, _ = _build_engine([
            _gemini_response([_tool_part("LIST_DIR", {"path": "src/"})]),
            text_resp,
        ])
        result = await engine.run("Q", _make_ref(), "abc123")
        llm_step_count = sum(1 for s in result.trace.steps if s.type == StepType.LLM_CALL)
        assert result.trace.llm_calls == llm_step_count

    async def test_tool_calls_count_matches_steps(self):
        engine, _ = _build_engine([
            _gemini_response([_tool_part("FETCH_FILE", {"path": "a.py"})]),
            _gemini_response([_tool_part("LIST_DIR", {"path": "src/"})]),
            _gemini_response([_text_part("Done.")]),
        ])
        result = await engine.run("Q", _make_ref(), "abc123")
        tool_step_count = sum(1 for s in result.trace.steps if s.type == StepType.TOOL_CALL)
        assert result.trace.tool_calls == tool_step_count

    async def test_reasoning_step_present_each_iteration(self):
        engine, _ = _build_engine([
            _gemini_response([_tool_part("FETCH_FILE", {"path": "a.py"})]),
            _gemini_response([_text_part("Done.")]),
        ])
        result = await engine.run("Q", _make_ref(), "abc123")
        reasoning_steps = [s for s in result.trace.steps if s.type == StepType.REASONING]
        assert len(reasoning_steps) == result.trace.iterations

    async def test_trace_step_metadata_for_tool_call(self):
        engine, _ = _build_engine([
            _gemini_response([_tool_part("FETCH_FILE", {"path": "src/auth.py"})]),
            _gemini_response([_text_part("Done.")]),
        ])
        result = await engine.run("Q", _make_ref(), "abc123")
        tool_steps = [s for s in result.trace.steps if s.type == StepType.TOOL_CALL]
        assert len(tool_steps) == 1
        assert tool_steps[0].metadata.get("tool") == "FETCH_FILE"
        assert tool_steps[0].metadata.get("args") == {"path": "src/auth.py"}


# ===========================================================================
# 3. Tool Dispatch Accuracy Eval
# ===========================================================================

class TestToolDispatchAccuracyEval:
    """Evaluate that Gemini tool calls are dispatched to the correct GitHub client methods."""

    async def test_fetch_file_dispatches_to_get_file(self):
        engine, gh = _build_engine([
            _gemini_response([_tool_part("FETCH_FILE", {"path": "src/auth.py"})]),
            _gemini_response([_text_part("Done.")]),
        ])
        ref = _make_ref()
        await engine.run("Q", ref, "abc123")
        gh.get_file.assert_called_once_with(ref, "src/auth.py", "abc123")

    async def test_list_dir_dispatches_to_list_dir(self):
        engine, gh = _build_engine([
            _gemini_response([_tool_part("LIST_DIR", {"path": "src/"})]),
            _gemini_response([_text_part("Done.")]),
        ])
        ref = _make_ref()
        await engine.run("Q", ref, "abc123")
        gh.list_dir.assert_called_once_with(ref, "src/", "abc123")

    async def test_search_code_dispatches_to_search_code(self):
        engine, gh = _build_engine([
            _gemini_response([_tool_part("SEARCH_CODE", {"query": "def authenticate"})]),
            _gemini_response([_text_part("Done.")]),
        ])
        ref = _make_ref()
        await engine.run("Q", ref, "abc123")
        gh.search_code.assert_called_once_with(ref, "def authenticate")

    async def test_unknown_tool_returns_error_message(self):
        engine, gh = _build_engine([
            _gemini_response([_tool_part("UNKNOWN_TOOL", {"arg": "val"})]),
            _gemini_response([_text_part("Done.")]),
        ])
        result = await engine.run("Q", _make_ref(), "abc123")
        # The tool result fed back should contain "Unknown tool"
        tool_result_msg = result.conversation[2]
        assert "Unknown tool" in tool_result_msg.content


# ===========================================================================
# 4. Conversation History Eval
# ===========================================================================

class TestConversationHistoryEval:
    """Evaluate that prior conversation messages are correctly handled."""

    async def test_prior_conversation_included(self):
        engine, _ = _build_engine([_gemini_response([_text_part("Noted.")])])
        prior = [
            ConversationMessage(role="user", content="What does auth do?"),
            ConversationMessage(role="model", content="It validates tokens."),
        ]
        result = await engine.run("Follow up?", _make_ref(), "abc123", conversation=prior)
        # Prior 2 + new user prompt + model response = 4
        assert len(result.conversation) == 4
        assert result.conversation[0].content == "What does auth do?"
        assert result.conversation[1].content == "It validates tokens."

    async def test_new_messages_appended_after_completion(self):
        engine, _ = _build_engine([_gemini_response([_text_part("Final answer.")])])
        result = await engine.run("Question", _make_ref(), "abc123")
        last = result.conversation[-1]
        assert last.role == "model"
        assert last.content == "Final answer."

    async def test_conversation_grows_across_multi_tool_response(self):
        engine, _ = _build_engine([
            _gemini_response([_tool_part("FETCH_FILE", {"path": "a.py"})]),
            _gemini_response([_tool_part("LIST_DIR", {"path": "src/"})]),
            _gemini_response([_text_part("Complete.")]),
        ])
        result = await engine.run("Deep check", _make_ref(), "abc123")
        # user prompt(1) + tool call model(1) + tool result user(1) +
        # tool call model(1) + tool result user(1) + final model(1) = 6
        assert len(result.conversation) == 6

    async def test_empty_prior_conversation(self):
        engine, _ = _build_engine([_gemini_response([_text_part("OK.")])])
        result = await engine.run("Q", _make_ref(), "abc123", conversation=[])
        assert len(result.conversation) == 2  # user + model

    async def test_none_prior_conversation(self):
        engine, _ = _build_engine([_gemini_response([_text_part("OK.")])])
        result = await engine.run("Q", _make_ref(), "abc123", conversation=None)
        assert len(result.conversation) == 2


# ===========================================================================
# 5. Failure Mode Eval
# ===========================================================================

class TestFailureModeEval:
    """Evaluate graceful handling of errors and edge cases."""

    async def test_gemini_api_exception(self):
        gh = _mock_gh()
        engine = ReasoningEngine(github_client=gh, api_key="fake")
        engine._gemini = MagicMock()
        engine._gemini.models = MagicMock()
        engine._gemini.models.generate_content = MagicMock(
            side_effect=RuntimeError("API quota exceeded")
        )
        engine._save_trace = MagicMock()
        result = await engine.run("Q", _make_ref(), "abc123")
        assert not result.success
        assert result.error is not None
        assert "quota" in result.error.lower() or "API" in result.error

    async def test_empty_response_no_candidates(self):
        engine, _ = _build_engine([_empty_response()])
        result = await engine.run("Q", _make_ref(), "abc123")
        assert not result.success
        assert result.error is not None
        assert "candidates" in result.error.lower() or "No" in result.error

    async def test_tool_execution_error_does_not_crash(self):
        """If a tool raises, the engine should gracefully feed error back."""
        gh = _mock_gh()
        gh.get_file = AsyncMock(side_effect=ConnectionError("GitHub API down"))
        engine = ReasoningEngine(github_client=gh, api_key="fake")
        engine._gemini = MagicMock()
        engine._gemini.models = MagicMock()
        engine._gemini.models.generate_content = MagicMock(side_effect=[
            _gemini_response([_tool_part("FETCH_FILE", {"path": "a.py"})]),
            _gemini_response([_text_part("Handled error.")]),
        ])
        engine._save_trace = MagicMock()
        result = await engine.run("Q", _make_ref(), "abc123")
        assert result.success
        # Tool error should appear in conversation
        tool_result_msg = result.conversation[2]
        assert "Error" in tool_result_msg.content

    async def test_success_false_when_output_empty_and_error(self):
        gh = _mock_gh()
        engine = ReasoningEngine(github_client=gh, api_key="fake")
        engine._gemini = MagicMock()
        engine._gemini.models = MagicMock()
        engine._gemini.models.generate_content = MagicMock(
            side_effect=Exception("total failure")
        )
        engine._save_trace = MagicMock()
        result = await engine.run("Q", _make_ref(), "abc123")
        assert result.success is False
        assert result.output == ""


# ===========================================================================
# 6. Limit Enforcement Eval
# ===========================================================================

class TestLimitEnforcementEval:
    """Evaluate sandbox limits are set to reasonable values."""

    def test_max_iterations_positive(self):
        assert MAX_ITERATIONS > 0

    def test_max_iterations_reasonable(self):
        assert MAX_ITERATIONS < 100

    def test_max_llm_calls_positive(self):
        assert MAX_LLM_CALLS > 0

    def test_max_llm_calls_reasonable(self):
        assert MAX_LLM_CALLS < 100

    def test_allowed_tools_contains_fetch_file(self):
        assert "FETCH_FILE" in ALLOWED_TOOLS

    def test_allowed_tools_contains_list_dir(self):
        assert "LIST_DIR" in ALLOWED_TOOLS

    def test_allowed_tools_contains_search_code(self):
        assert "SEARCH_CODE" in ALLOWED_TOOLS

    def test_allowed_tools_is_superset_of_core_tools(self):
        core = {"FETCH_FILE", "LIST_DIR", "SEARCH_CODE"}
        assert core.issubset(ALLOWED_TOOLS)

    def test_max_llm_calls_lte_max_iterations(self):
        assert MAX_LLM_CALLS <= MAX_ITERATIONS
