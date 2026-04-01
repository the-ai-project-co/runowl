"""End-to-end tests for the interactive Q&A pipeline.

Tests the full flow: ask question -> fetch PR metadata -> build context ->
call reasoning -> extract citations -> return answer -> store in session.

All external dependencies (GitHub, ReasoningEngine) are mocked at the
top level — internal wiring is exercised for real.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from github.models import DiffHunk, PRCommit, PRFile, PRMetadata, PRRef
from qa.engine import QAEngine
from qa.models import CodeSelection, QAMessage, QASession, SelectionMode
from reasoning.models import (
    ConversationMessage,
    ReasoningStep,
    ReasoningTrace,
    RLMResult,
    StepType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pr_ref(owner: str = "acme", repo: str = "widgets", number: int = 99) -> PRRef:
    return PRRef(owner=owner, repo=repo, number=number)


def _make_pr_metadata(
    *,
    number: int = 99,
    files: list[PRFile] | None = None,
) -> PRMetadata:
    default_files = [
        PRFile(
            filename="src/auth.py",
            status="modified",
            additions=10,
            deletions=2,
            changes=12,
            patch=(
                "@@ -10,7 +10,9 @@ def login(user):\n"
                "     token = generate_token(user)\n"
                "+    audit_log(user, 'login')\n"
                "     return token\n"
            ),
        ),
        PRFile(
            filename="src/utils.py",
            status="added",
            additions=25,
            deletions=0,
            changes=25,
            patch="@@ -0,0 +1,25 @@\n+def helper():\n+    pass\n",
        ),
    ]
    return PRMetadata(
        number=number,
        title="Add audit logging",
        body="Adds audit log calls on login.",
        author="dev",
        base_branch="main",
        head_branch="feat/audit",
        head_sha="abc123",
        base_sha="000000",
        state="open",
        commits=[PRCommit(sha="abc123", message="add audit", author="dev")],
        files=files if files is not None else default_files,
        additions=35,
        deletions=2,
        changed_files=2,
    )


def _make_rlm_result(output: str) -> RLMResult:
    """Build an RLMResult with a simple trace."""
    trace = ReasoningTrace()
    trace.add_step(ReasoningStep(type=StepType.LLM_CALL, content="thinking", iteration=0))
    trace.add_step(ReasoningStep(type=StepType.OUTPUT, content=output, iteration=1))
    return RLMResult(
        output=output,
        trace=trace,
        conversation=[ConversationMessage(role="model", content=output)],
        success=True,
    )


def _build_engine(
    reasoning_output: str = "The login function now writes an audit log. See src/auth.py:11.",
) -> tuple[QAEngine, AsyncMock, AsyncMock]:
    """Create a QAEngine with mocked GitHub client and ReasoningEngine."""
    mock_gh = AsyncMock()
    mock_gh.get_pr_metadata = AsyncMock(return_value=_make_pr_metadata())
    mock_gh.close = AsyncMock()

    mock_reasoning = AsyncMock()
    mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result(reasoning_output))

    engine = QAEngine(github_client=mock_gh, reasoning_engine=mock_reasoning)
    return engine, mock_gh, mock_reasoning


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSingleQuestionAnswer:
    """Single question -> answer with citations extracted."""

    async def test_single_question_returns_answer_with_citations(self) -> None:
        engine, mock_gh, mock_reasoning = _build_engine(
            reasoning_output="The function writes an audit log entry at src/auth.py:11."
        )
        ref = _make_pr_ref()

        msg = await engine.ask(ref, "What does the login change do?")

        assert isinstance(msg, QAMessage)
        assert msg.role == "assistant"
        assert msg.question == "What does the login change do?"
        assert "audit log" in msg.answer
        # Citation should be extracted from the answer text
        assert len(msg.citations) >= 1
        assert any("src/auth.py" in c for c in msg.citations)

    async def test_answer_stored_in_session(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()

        await engine.ask(ref, "Explain this PR")

        session = engine.get_session(ref)
        assert len(session.messages) == 1
        assert session.messages[0].question == "Explain this PR"

    async def test_github_metadata_fetched_once(self) -> None:
        engine, mock_gh, _ = _build_engine()
        ref = _make_pr_ref()

        await engine.ask(ref, "Q1")
        await engine.ask(ref, "Q2")

        # PR metadata should be cached after first call
        assert mock_gh.get_pr_metadata.call_count == 1


class TestMultiTurnConversation:
    """Multi-turn conversation (3+ turns) maintaining context."""

    async def test_three_turn_conversation_maintains_history(self) -> None:
        engine, _, mock_reasoning = _build_engine()
        ref = _make_pr_ref()

        answers = [
            "The PR adds audit logging to the login flow.",
            "The audit_log function is called after token generation in src/auth.py:11.",
            "No, there are no security concerns with this approach.",
        ]
        for i, answer_text in enumerate(answers):
            mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result(answer_text))
            msg = await engine.ask(ref, f"Question {i + 1}")
            assert msg.answer == answer_text

        session = engine.get_session(ref)
        assert len(session.messages) == 3
        assert session.messages[0].question == "Question 1"
        assert session.messages[1].question == "Question 2"
        assert session.messages[2].question == "Question 3"

    async def test_conversation_history_passed_to_reasoning(self) -> None:
        engine, _, mock_reasoning = _build_engine()
        ref = _make_pr_ref()

        # First question
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("Answer 1"))
        await engine.ask(ref, "First question")

        # Second question — reasoning engine should receive conversation history
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("Answer 2"))
        await engine.ask(ref, "Follow-up question")

        call_kwargs = mock_reasoning.ask.call_args
        conversation_arg = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        assert conversation_arg is not None
        assert len(conversation_arg) >= 2  # at least one user + model pair
        assert conversation_arg[0].role == "user"
        assert conversation_arg[0].content == "First question"

    async def test_history_text_property(self) -> None:
        engine, _, mock_reasoning = _build_engine()
        ref = _make_pr_ref()

        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("A1"))
        await engine.ask(ref, "Q1")
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("A2"))
        await engine.ask(ref, "Q2")

        session = engine.get_session(ref)
        text = session.history_text
        assert "Q: Q1" in text
        assert "A: A1" in text
        assert "Q: Q2" in text
        assert "A: A2" in text


class TestSessionReset:
    """Session reset clears history."""

    async def test_reset_clears_messages(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()

        await engine.ask(ref, "Q1")
        session = engine.get_session(ref)
        assert len(session.messages) == 1

        engine.reset_session(ref)
        assert len(session.messages) == 0

    async def test_reset_allows_new_conversation(self) -> None:
        engine, _, mock_reasoning = _build_engine()
        ref = _make_pr_ref()

        await engine.ask(ref, "Old question")
        engine.reset_session(ref)

        # After reset, reasoning should receive empty conversation
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("Fresh answer"))
        await engine.ask(ref, "New question")

        call_kwargs = mock_reasoning.ask.call_args
        conversation_arg = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        # Conversation should be empty because history was reset
        assert conversation_arg == []


class TestCodeSelection:
    """Code selection (RANGE mode) passed to reasoning engine."""

    async def test_range_selection_forwarded_to_reasoning(self) -> None:
        engine, _, mock_reasoning = _build_engine()
        ref = _make_pr_ref()

        selection = CodeSelection(
            mode=SelectionMode.RANGE,
            file="src/auth.py",
            content="+    audit_log(user, 'login')",
            line_start=11,
            line_end=11,
        )

        await engine.ask(ref, "What does this line do?", selection=selection)

        call_kwargs = mock_reasoning.ask.call_args
        selected_code_arg = call_kwargs.kwargs.get("selected_code") or call_kwargs[1].get("selected_code")
        # The formatted selection context should contain file info and content
        assert "src/auth.py" in selected_code_arg
        assert "audit_log" in selected_code_arg

    async def test_selection_stored_in_message(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()

        selection = CodeSelection(
            mode=SelectionMode.RANGE,
            file="src/auth.py",
            content="+    audit_log(user, 'login')",
            line_start=11,
            line_end=13,
        )

        msg = await engine.ask(ref, "Explain this", selection=selection)

        assert msg.selection is not None
        assert msg.selection.mode == SelectionMode.RANGE
        assert msg.selection.file == "src/auth.py"
        assert msg.selection.line_start == 11
        assert msg.selection.line_end == 13

    async def test_no_selection_sends_placeholder(self) -> None:
        engine, _, mock_reasoning = _build_engine()
        ref = _make_pr_ref()

        await engine.ask(ref, "General question")

        call_kwargs = mock_reasoning.ask.call_args
        selected_code_arg = call_kwargs.kwargs.get("selected_code") or call_kwargs[1].get("selected_code")
        assert "no code selected" in selected_code_arg.lower()

    def test_code_selection_describe_range(self) -> None:
        sel = CodeSelection(
            mode=SelectionMode.RANGE,
            file="src/auth.py",
            content="...",
            line_start=10,
            line_end=20,
        )
        assert sel.describe() == "src/auth.py:10-20"

    def test_code_selection_describe_line(self) -> None:
        sel = CodeSelection(
            mode=SelectionMode.LINE,
            file="src/auth.py",
            content="...",
            line_start=42,
        )
        assert sel.describe() == "src/auth.py:42"


class TestQACommands:
    """All QA commands: quit->SESSION_END, help->commands list, reset->clears,
    history->shows history, files->shows files, unknown->None."""

    def test_quit_returns_session_end(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        assert engine.handle_command(ref, "quit") == "SESSION_END"

    def test_exit_returns_session_end(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        assert engine.handle_command(ref, "exit") == "SESSION_END"

    def test_q_returns_session_end(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        assert engine.handle_command(ref, "q") == "SESSION_END"

    def test_help_returns_commands_list(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        result = engine.handle_command(ref, "help")
        assert result is not None
        assert "quit" in result
        assert "reset" in result
        assert "history" in result
        assert "files" in result

    def test_reset_clears_and_returns_message(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        session = engine.get_session(ref)
        session.add(QAMessage(role="assistant", question="Q", answer="A"))
        assert len(session.messages) == 1

        result = engine.handle_command(ref, "reset")
        assert result is not None
        assert "cleared" in result.lower()
        assert len(session.messages) == 0

    async def test_history_shows_previous_qa(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()

        await engine.ask(ref, "What is this?")

        result = engine.handle_command(ref, "history")
        assert result is not None
        assert "What is this?" in result

    def test_history_empty(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        result = engine.handle_command(ref, "history")
        assert result is not None
        assert "no conversation" in result.lower()

    async def test_files_shows_changed_files(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()

        # Need to load diffs first by asking a question
        await engine.ask(ref, "Anything")

        result = engine.handle_command(ref, "files")
        assert result is not None
        assert "src/auth.py" in result

    def test_files_before_load(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        result = engine.handle_command(ref, "files")
        assert result is not None
        assert "not yet loaded" in result.lower()

    def test_unknown_command_returns_none(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        assert engine.handle_command(ref, "foobar") is None

    def test_unknown_command_regular_text_returns_none(self) -> None:
        engine, _, _ = _build_engine()
        ref = _make_pr_ref()
        assert engine.handle_command(ref, "What does this code do?") is None


class TestSessionIsolation:
    """Session isolation between different PRs."""

    async def test_different_prs_have_separate_sessions(self) -> None:
        engine, mock_gh, mock_reasoning = _build_engine()
        ref_a = _make_pr_ref(owner="acme", repo="widgets", number=1)
        ref_b = _make_pr_ref(owner="acme", repo="widgets", number=2)

        # Ensure both PRs can load metadata
        mock_gh.get_pr_metadata = AsyncMock(return_value=_make_pr_metadata(number=1))
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("Answer for PR1"))
        await engine.ask(ref_a, "Q for PR1")

        mock_gh.get_pr_metadata = AsyncMock(return_value=_make_pr_metadata(number=2))
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("Answer for PR2"))
        await engine.ask(ref_b, "Q for PR2")

        session_a = engine.get_session(ref_a)
        session_b = engine.get_session(ref_b)

        assert len(session_a.messages) == 1
        assert len(session_b.messages) == 1
        assert session_a.messages[0].question == "Q for PR1"
        assert session_b.messages[0].question == "Q for PR2"

    async def test_resetting_one_session_does_not_affect_other(self) -> None:
        engine, mock_gh, mock_reasoning = _build_engine()
        ref_a = _make_pr_ref(number=10)
        ref_b = _make_pr_ref(number=20)

        mock_gh.get_pr_metadata = AsyncMock(return_value=_make_pr_metadata())
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("A"))

        await engine.ask(ref_a, "Qa")
        await engine.ask(ref_b, "Qb")

        engine.reset_session(ref_a)

        assert len(engine.get_session(ref_a).messages) == 0
        assert len(engine.get_session(ref_b).messages) == 1

    async def test_different_repos_are_isolated(self) -> None:
        engine, mock_gh, mock_reasoning = _build_engine()
        ref_x = _make_pr_ref(owner="org1", repo="repoA", number=5)
        ref_y = _make_pr_ref(owner="org2", repo="repoB", number=5)

        mock_gh.get_pr_metadata = AsyncMock(return_value=_make_pr_metadata())
        mock_reasoning.ask = AsyncMock(return_value=_make_rlm_result("Answer"))

        await engine.ask(ref_x, "Qx")
        await engine.ask(ref_y, "Qy")

        session_x = engine.get_session(ref_x)
        session_y = engine.get_session(ref_y)
        assert session_x is not session_y
        assert session_x.pr_ref_str != session_y.pr_ref_str


class TestCitationExtraction:
    """Citation extraction from answers containing file references."""

    async def test_single_file_line_citation(self) -> None:
        engine, _, _ = _build_engine(
            reasoning_output="The issue is at src/auth.py:11 where the audit call is made."
        )
        ref = _make_pr_ref()
        msg = await engine.ask(ref, "Where is the issue?")
        assert any("src/auth.py:11" in c for c in msg.citations)

    async def test_file_range_citation(self) -> None:
        engine, _, _ = _build_engine(
            reasoning_output="See the changes in src/auth.py lines 10-20 for the new logic."
        )
        ref = _make_pr_ref()
        msg = await engine.ask(ref, "Where are the changes?")
        assert any("src/auth.py" in c for c in msg.citations)

    async def test_multiple_citations(self) -> None:
        engine, _, _ = _build_engine(
            reasoning_output=(
                "The change spans src/auth.py:11 and src/utils.py:5. "
                "Both files are affected."
            )
        )
        ref = _make_pr_ref()
        msg = await engine.ask(ref, "What files changed?")
        assert len(msg.citations) >= 2
        files_cited = " ".join(msg.citations)
        assert "src/auth.py" in files_cited
        assert "src/utils.py" in files_cited

    async def test_no_citations_when_none_in_answer(self) -> None:
        engine, _, _ = _build_engine(
            reasoning_output="This PR improves code quality overall."
        )
        ref = _make_pr_ref()
        msg = await engine.ask(ref, "What does it do?")
        assert msg.citations == []

    async def test_citations_persisted_in_session(self) -> None:
        engine, _, _ = _build_engine(
            reasoning_output="Fixed in src/auth.py:15 and src/auth.py:20."
        )
        ref = _make_pr_ref()
        await engine.ask(ref, "Where is the fix?")

        session = engine.get_session(ref)
        assert len(session.messages) == 1
        assert len(session.messages[0].citations) >= 1

    async def test_colon_notation_citation(self) -> None:
        engine, _, _ = _build_engine(
            reasoning_output="Check src/utils.py:3-10 for the helper implementation."
        )
        ref = _make_pr_ref()
        msg = await engine.ask(ref, "Where is the helper?")
        assert any("src/utils.py" in c for c in msg.citations)


class TestQASessionModel:
    """Direct tests on the QASession dataclass."""

    def test_add_and_last_n(self) -> None:
        session = QASession(pr_ref_str="owner/repo#1")
        for i in range(5):
            session.add(
                QAMessage(role="assistant", question=f"Q{i}", answer=f"A{i}")
            )
        assert len(session.messages) == 5
        last_two = session.last_n(2)
        assert len(last_two) == 2
        assert last_two[0].question == "Q3"
        assert last_two[1].question == "Q4"

    def test_reset_clears_all(self) -> None:
        session = QASession(pr_ref_str="owner/repo#1")
        session.add(QAMessage(role="assistant", question="Q", answer="A"))
        session.reset()
        assert session.messages == []

    def test_last_n_more_than_available(self) -> None:
        session = QASession(pr_ref_str="owner/repo#1")
        session.add(QAMessage(role="assistant", question="Q1", answer="A1"))
        result = session.last_n(10)
        assert len(result) == 1

    def test_history_text_formatting(self) -> None:
        session = QASession(pr_ref_str="owner/repo#1")
        session.add(QAMessage(role="assistant", question="What?", answer="This."))
        session.add(QAMessage(role="assistant", question="Why?", answer="Because."))
        text = session.history_text
        assert "Q: What?" in text
        assert "A: This." in text
        assert "Q: Why?" in text
        assert "A: Because." in text
