"""AI evals for Q&A engine answer quality, context management, and code selection."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from qa.engine import QAEngine, QA_COMMANDS
from qa.models import QASession, QAMessage, CodeSelection, SelectionMode
from qa.selection import (
    format_selection_context,
    select_line,
    select_range,
    select_hunk,
    select_file,
    select_changeset,
)
from review.citations import extract_citations
from github.models import PRRef, PRMetadata, PRFile, DiffHunk, FileDiff
from reasoning.models import RLMResult, ReasoningTrace, ConversationMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ref(owner: str = "acme", repo: str = "api", number: int = 42) -> PRRef:
    return PRRef(owner=owner, repo=repo, number=number)


def _make_metadata(
    number: int = 42,
    title: str = "Add auth",
    body: str | None = "Implements JWT auth",
    n_files: int = 1,
) -> PRMetadata:
    files = [
        PRFile(
            filename=f"src/file_{i}.py",
            status="modified",
            additions=10,
            deletions=2,
            changes=12,
            patch="@@ -1,3 +1,5 @@\n line1\n+line2\n+line3\n line4\n line5",
        )
        for i in range(n_files)
    ]
    return PRMetadata(
        number=number,
        title=title,
        body=body,
        author="dev",
        base_branch="main",
        head_branch="feat/auth",
        head_sha="abc123",
        base_sha="def456",
        state="open",
        commits=[],
        files=files,
        additions=10 * n_files,
        deletions=2 * n_files,
        changed_files=n_files,
    )


def _make_rlm_result(output: str, success: bool = True) -> RLMResult:
    return RLMResult(
        output=output,
        trace=ReasoningTrace(),
        conversation=[],
        success=success,
    )


def _build_engine(rlm_output: str = "Looks good.") -> tuple[QAEngine, AsyncMock, AsyncMock]:
    """Build a QAEngine with mocked GitHub client and reasoning engine."""
    gh = AsyncMock()
    gh.get_pr_metadata = AsyncMock(return_value=_make_metadata())

    reasoning = AsyncMock()
    reasoning.ask = AsyncMock(return_value=_make_rlm_result(rlm_output))

    engine = QAEngine(github_client=gh, reasoning_engine=reasoning)
    return engine, gh, reasoning


def _make_file_diff(
    filename: str = "src/auth.py",
    status: str = "modified",
    hunks: list[DiffHunk] | None = None,
) -> FileDiff:
    if hunks is None:
        hunks = [
            DiffHunk(
                header="@@ -10,5 +10,7 @@ def authenticate():",
                old_start=10,
                old_lines=5,
                new_start=10,
                new_lines=7,
                lines=[
                    " def authenticate():",
                    "+    token = get_token()",
                    "+    if not token:",
                    "+        raise AuthError()",
                    "     return True",
                    " ",
                    " def logout():",
                ],
            )
        ]
    return FileDiff(
        filename=filename,
        status=status,
        additions=3,
        deletions=0,
        hunks=hunks,
    )


# ===========================================================================
# 1. Answer Relevance Eval
# ===========================================================================

class TestAnswerRelevanceEval:
    """Evaluate that the Q&A engine stores answers, questions, and citations correctly."""

    async def test_answer_stored_in_message(self):
        engine, _, reasoning = _build_engine("The function validates JWT tokens.")
        msg = await engine.ask(_make_ref(), "What does authenticate do?")
        assert msg.answer == "The function validates JWT tokens."

    async def test_question_stored_in_message(self):
        engine, _, _ = _build_engine("Answer here.")
        msg = await engine.ask(_make_ref(), "How does login work?")
        assert msg.question == "How does login work?"

    async def test_citations_extracted_from_answer_with_file_ref(self):
        answer = "The issue is in src/auth.py lines 10-15 where the token is checked."
        engine, _, _ = _build_engine(answer)
        msg = await engine.ask(_make_ref(), "Where is the bug?")
        assert len(msg.citations) >= 1
        assert any("src/auth.py" in c for c in msg.citations)

    async def test_citations_extracted_colon_format(self):
        answer = "See src/utils.py:42 for the helper function."
        engine, _, _ = _build_engine(answer)
        msg = await engine.ask(_make_ref(), "Where is the helper?")
        assert len(msg.citations) >= 1
        assert any("src/utils.py" in c for c in msg.citations)

    async def test_no_citations_when_answer_has_no_file_refs(self):
        engine, _, _ = _build_engine("Everything looks fine, no issues found.")
        msg = await engine.ask(_make_ref(), "Any problems?")
        assert msg.citations == []

    async def test_selection_context_forwarded_to_engine(self):
        engine, _, reasoning = _build_engine("Noted.")
        selection = CodeSelection(
            mode=SelectionMode.LINE,
            file="src/auth.py",
            content="token = get_token()",
            line_start=11,
            line_end=11,
        )
        await engine.ask(_make_ref(), "What is this?", selection=selection)
        call_kwargs = reasoning.ask.call_args
        assert "token" in call_kwargs.kwargs.get("selected_code", "") or \
               "token" in call_kwargs[1].get("selected_code", "")

    async def test_none_selection_yields_no_code_selected(self):
        engine, _, reasoning = _build_engine("Noted.")
        await engine.ask(_make_ref(), "General question", selection=None)
        call_kwargs = reasoning.ask.call_args
        selected = call_kwargs.kwargs.get("selected_code", "") or call_kwargs[1].get("selected_code", "")
        assert "(no code selected)" in selected

    async def test_empty_answer_fallback(self):
        engine, _, reasoning = _build_engine("")
        reasoning.ask = AsyncMock(return_value=RLMResult(
            output="", trace=ReasoningTrace(), conversation=[], success=True
        ))
        msg = await engine.ask(_make_ref(), "Question?")
        assert msg.answer == "(no answer returned)"

    async def test_message_role_is_assistant(self):
        engine, _, _ = _build_engine("response text")
        msg = await engine.ask(_make_ref(), "Question")
        assert msg.role == "assistant"

    async def test_multiple_citations_in_answer(self):
        answer = (
            "Found issues in src/auth.py lines 10-15 and also in "
            "src/db.py:20-30 where connections leak."
        )
        engine, _, _ = _build_engine(answer)
        msg = await engine.ask(_make_ref(), "List all issues")
        assert len(msg.citations) >= 2


# ===========================================================================
# 2. Context Management Eval
# ===========================================================================

class TestContextManagementEval:
    """Evaluate multi-turn conversation context passing to the reasoning engine."""

    async def test_first_question_no_history(self):
        engine, _, reasoning = _build_engine("Answer 1")
        await engine.ask(_make_ref(), "Q1")
        call_kwargs = reasoning.ask.call_args
        conversation = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        assert conversation == []

    async def test_second_question_one_exchange_in_history(self):
        engine, _, reasoning = _build_engine("Answer")
        ref = _make_ref()
        await engine.ask(ref, "Q1")
        await engine.ask(ref, "Q2")
        call_kwargs = reasoning.ask.call_args  # last call
        conversation = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        # 1 exchange = 2 messages (user + model)
        assert len(conversation) == 2

    async def test_third_question_two_exchanges_in_history(self):
        engine, _, reasoning = _build_engine("Answer")
        ref = _make_ref()
        await engine.ask(ref, "Q1")
        await engine.ask(ref, "Q2")
        await engine.ask(ref, "Q3")
        call_kwargs = reasoning.ask.call_args
        conversation = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        # 2 exchanges = 4 messages
        assert len(conversation) == 4

    async def test_window_limit_after_many_turns(self):
        engine, _, reasoning = _build_engine("Answer")
        ref = _make_ref()
        # Ask 8 questions to exceed the last_n(6) window
        for i in range(8):
            await engine.ask(ref, f"Q{i}")
        call_kwargs = reasoning.ask.call_args
        conversation = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        # last_n(6) => 6 exchanges => 12 messages
        assert len(conversation) == 12

    async def test_reset_clears_history(self):
        engine, _, reasoning = _build_engine("Answer")
        ref = _make_ref()
        await engine.ask(ref, "Q1")
        await engine.ask(ref, "Q2")
        engine.reset_session(ref)
        await engine.ask(ref, "Q3 after reset")
        call_kwargs = reasoning.ask.call_args
        conversation = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        assert conversation == []

    async def test_history_text_contains_all_pairs(self):
        engine, _, _ = _build_engine("Some answer")
        ref = _make_ref()
        await engine.ask(ref, "First question")
        await engine.ask(ref, "Second question")
        session = engine.get_session(ref)
        text = session.history_text
        assert "First question" in text
        assert "Second question" in text
        assert "Some answer" in text

    async def test_conversation_messages_have_correct_roles(self):
        engine, _, reasoning = _build_engine("Reply")
        ref = _make_ref()
        await engine.ask(ref, "Q1")
        await engine.ask(ref, "Q2")
        call_kwargs = reasoning.ask.call_args
        conversation = call_kwargs.kwargs.get("conversation") or call_kwargs[1].get("conversation")
        assert conversation[0].role == "user"
        assert conversation[1].role == "model"


# ===========================================================================
# 3. Session Isolation Eval
# ===========================================================================

class TestSessionIsolationEval:
    """Evaluate that sessions for different PRs are independent."""

    async def test_different_prs_get_separate_sessions(self):
        engine, _, _ = _build_engine("Answer")
        ref1 = _make_ref(repo="api", number=1)
        ref2 = _make_ref(repo="api", number=2)
        await engine.ask(ref1, "Q for PR1")
        await engine.ask(ref2, "Q for PR2")
        s1 = engine.get_session(ref1)
        s2 = engine.get_session(ref2)
        assert len(s1.messages) == 1
        assert len(s2.messages) == 1
        assert s1.messages[0].question == "Q for PR1"
        assert s2.messages[0].question == "Q for PR2"

    async def test_resetting_one_does_not_affect_other(self):
        engine, _, _ = _build_engine("Answer")
        ref1 = _make_ref(number=10)
        ref2 = _make_ref(number=20)
        await engine.ask(ref1, "Q1")
        await engine.ask(ref2, "Q2")
        engine.reset_session(ref1)
        assert len(engine.get_session(ref1).messages) == 0
        assert len(engine.get_session(ref2).messages) == 1

    async def test_same_pr_different_numbers_are_separate(self):
        engine, _, _ = _build_engine("Answer")
        ref_a = _make_ref(owner="acme", repo="web", number=5)
        ref_b = _make_ref(owner="acme", repo="web", number=6)
        await engine.ask(ref_a, "Q-A")
        session_a = engine.get_session(ref_a)
        session_b = engine.get_session(ref_b)
        assert len(session_a.messages) == 1
        assert len(session_b.messages) == 0

    async def test_session_persists_across_multiple_asks(self):
        engine, _, _ = _build_engine("Answer")
        ref = _make_ref()
        await engine.ask(ref, "Q1")
        await engine.ask(ref, "Q2")
        await engine.ask(ref, "Q3")
        session = engine.get_session(ref)
        assert len(session.messages) == 3
        assert [m.question for m in session.messages] == ["Q1", "Q2", "Q3"]


# ===========================================================================
# 4. Code Selection Quality Eval
# ===========================================================================

class TestCodeSelectionQualityEval:
    """Evaluate selection helpers against realistic FileDiff objects."""

    def _diffs(self) -> list[FileDiff]:
        """Build a realistic multi-hunk, multi-file diff list."""
        return [
            FileDiff(
                filename="src/auth.py",
                status="modified",
                additions=4,
                deletions=1,
                hunks=[
                    DiffHunk(
                        header="@@ -10,5 +10,8 @@ def authenticate():",
                        old_start=10,
                        old_lines=5,
                        new_start=10,
                        new_lines=8,
                        lines=[
                            " def authenticate():",
                            "+    token = get_token()",
                            "+    if not token:",
                            "+        raise AuthError()",
                            "     return True",
                            " ",
                            " def logout():",
                            "+    clear_session()",
                        ],
                    ),
                    DiffHunk(
                        header="@@ -30,3 +33,5 @@ def refresh():",
                        old_start=30,
                        old_lines=3,
                        new_start=33,
                        new_lines=5,
                        lines=[
                            " def refresh():",
                            "+    new_token = mint_token()",
                            "+    return new_token",
                            "     pass",
                        ],
                    ),
                ],
            ),
            FileDiff(
                filename="src/db.py",
                status="added",
                additions=5,
                deletions=0,
                hunks=[
                    DiffHunk(
                        header="@@ -0,0 +1,5 @@",
                        old_start=0,
                        old_lines=0,
                        new_start=1,
                        new_lines=5,
                        lines=[
                            "+import sqlite3",
                            "+",
                            "+def connect():",
                            "+    return sqlite3.connect('app.db')",
                            "+",
                        ],
                    ),
                ],
            ),
        ]

    # -- select_line --

    def test_select_line_valid(self):
        diffs = self._diffs()
        sel = select_line(diffs, "src/auth.py", 11)
        assert sel is not None
        assert sel.mode == SelectionMode.LINE
        assert sel.file == "src/auth.py"
        assert sel.content != ""

    def test_select_line_wrong_file(self):
        diffs = self._diffs()
        result = select_line(diffs, "src/nonexistent.py", 11)
        assert result is None

    def test_select_line_out_of_range(self):
        diffs = self._diffs()
        result = select_line(diffs, "src/auth.py", 999)
        assert result is None

    # -- select_range --

    def test_select_range_valid(self):
        diffs = self._diffs()
        sel = select_range(diffs, "src/auth.py", 10, 14)
        assert sel is not None
        assert sel.mode == SelectionMode.RANGE
        assert sel.line_start == 10
        assert sel.line_end == 14

    def test_select_range_no_overlap(self):
        diffs = self._diffs()
        result = select_range(diffs, "src/auth.py", 500, 510)
        assert result is None

    # -- select_hunk --

    def test_select_hunk_valid_index(self):
        diffs = self._diffs()
        sel = select_hunk(diffs, "src/auth.py", hunk_index=0)
        assert sel is not None
        assert sel.mode == SelectionMode.HUNK
        assert sel.hunk_header is not None
        assert "authenticate" in sel.hunk_header

    def test_select_hunk_second_index(self):
        diffs = self._diffs()
        sel = select_hunk(diffs, "src/auth.py", hunk_index=1)
        assert sel is not None
        assert "refresh" in sel.hunk_header

    def test_select_hunk_out_of_bounds(self):
        diffs = self._diffs()
        result = select_hunk(diffs, "src/auth.py", hunk_index=99)
        assert result is None

    # -- select_file --

    def test_select_file_all_hunks_collected(self):
        diffs = self._diffs()
        sel = select_file(diffs, "src/auth.py")
        assert sel is not None
        assert sel.mode == SelectionMode.FILE
        # Both hunk headers should be present
        assert "authenticate" in sel.content
        assert "refresh" in sel.content

    def test_select_file_missing_file(self):
        diffs = self._diffs()
        result = select_file(diffs, "src/nope.py")
        assert result is None

    # -- select_changeset --

    def test_select_changeset_all_files_included(self):
        diffs = self._diffs()
        sel = select_changeset(diffs)
        assert sel is not None
        assert sel.mode == SelectionMode.CHANGESET
        assert "src/auth.py" in sel.content
        assert "src/db.py" in sel.content

    # -- format_selection_context --

    def test_format_none_selection(self):
        result = format_selection_context(None)
        assert result == "(no code selected)"

    def test_format_with_selection(self):
        sel = CodeSelection(
            mode=SelectionMode.LINE,
            file="src/auth.py",
            content="token = get_token()",
            line_start=11,
            line_end=11,
        )
        result = format_selection_context(sel)
        assert "src/auth.py" in result
        assert "token = get_token()" in result
        assert "```" in result

    def test_format_truncates_long_content(self):
        long_content = "x" * 5000
        sel = CodeSelection(
            mode=SelectionMode.FILE,
            file="src/big.py",
            content=long_content,
        )
        result = format_selection_context(sel)
        # content[:3000] is used internally — verify the output doesn't contain the full 5000 chars
        assert len(result) < 5000


# ===========================================================================
# 5. Command Handling Completeness Eval
# ===========================================================================

class TestCommandHandlingEval:
    """Evaluate that all known commands are handled and non-commands return None."""

    def _engine_with_diffs(self) -> QAEngine:
        gh = AsyncMock()
        reasoning = AsyncMock()
        engine = QAEngine(github_client=gh, reasoning_engine=reasoning)
        # Pre-populate caches so files/info commands work
        ref = _make_ref()
        key = engine._session_key(ref)
        engine._diffs_cache[key] = [_make_file_diff()]
        engine._pr_summary_cache[key] = "PR #42: Add auth\nAuthor: dev"
        return engine

    def test_quit_returns_session_end(self):
        engine = self._engine_with_diffs()
        assert engine.handle_command(_make_ref(), "quit") == "SESSION_END"

    def test_exit_returns_session_end(self):
        engine = self._engine_with_diffs()
        assert engine.handle_command(_make_ref(), "exit") == "SESSION_END"

    def test_q_returns_session_end(self):
        engine = self._engine_with_diffs()
        assert engine.handle_command(_make_ref(), "q") == "SESSION_END"

    def test_help_returns_usage(self):
        engine = self._engine_with_diffs()
        result = engine.handle_command(_make_ref(), "help")
        assert result is not None
        assert "quit" in result
        assert "reset" in result

    def test_reset_clears_session(self):
        engine = self._engine_with_diffs()
        ref = _make_ref()
        # Add a message to the session manually
        session = engine.get_session(ref)
        session.add(QAMessage(role="assistant", question="Q", answer="A"))
        result = engine.handle_command(ref, "reset")
        assert result is not None
        assert "cleared" in result.lower()
        assert len(session.messages) == 0

    def test_history_empty_session(self):
        engine = self._engine_with_diffs()
        result = engine.handle_command(_make_ref(), "history")
        assert result is not None
        assert "no conversation" in result.lower()

    def test_history_with_messages(self):
        engine = self._engine_with_diffs()
        ref = _make_ref()
        session = engine.get_session(ref)
        session.add(QAMessage(role="assistant", question="What is X?", answer="X is Y."))
        result = engine.handle_command(ref, "history")
        assert result is not None
        assert "What is X?" in result

    def test_files_command(self):
        engine = self._engine_with_diffs()
        result = engine.handle_command(_make_ref(), "files")
        assert result is not None
        assert "src/auth.py" in result

    def test_info_command(self):
        engine = self._engine_with_diffs()
        result = engine.handle_command(_make_ref(), "info")
        assert result is not None
        assert "PR #42" in result

    def test_non_command_returns_none(self):
        engine = self._engine_with_diffs()
        result = engine.handle_command(_make_ref(), "What does this code do?")
        assert result is None

    def test_all_qa_commands_recognized(self):
        """All commands in QA_COMMANDS set should be handled (not return None)."""
        engine = self._engine_with_diffs()
        ref = _make_ref()
        for cmd in QA_COMMANDS:
            result = engine.handle_command(ref, cmd)
            assert result is not None, f"Command '{cmd}' was not handled (returned None)"


# ===========================================================================
# 6. Citation Extraction from Answers Eval
# ===========================================================================

class TestCitationExtractionEval:
    """Golden dataset of answer texts and expected citation counts/files."""

    @pytest.mark.parametrize(
        "answer_text, expected_count, expected_files",
        [
            # Standard format: file lines N-M
            (
                "The bug is in src/auth.py lines 10-20",
                1,
                ["src/auth.py"],
            ),
            # Single line format
            (
                "See src/auth.py line 5 for the issue",
                1,
                ["src/auth.py"],
            ),
            # Colon format: file:N
            (
                "Check src/utils.py:42",
                1,
                ["src/utils.py"],
            ),
            # Colon range format: file:N-M
            (
                "The problem spans src/db.py:100-120",
                1,
                ["src/db.py"],
            ),
            # Multiple citations
            (
                "Issues in src/auth.py lines 10-15 and src/db.py:30-40 plus tests/test_auth.py line 5",
                3,
                ["src/auth.py", "src/db.py", "tests/test_auth.py"],
            ),
            # No citations at all
            (
                "Everything looks fine, no issues found in this PR.",
                0,
                [],
            ),
            # Citation with underscore and dash in filename
            (
                "See my-module/auth_handler.py lines 1-10",
                1,
                ["my-module/auth_handler.py"],
            ),
            # Deeply nested path
            (
                "The function in src/services/auth/jwt_validator.py:55 is vulnerable",
                1,
                ["src/services/auth/jwt_validator.py"],
            ),
            # Unicode dash (en-dash) in range
            (
                "Check src/main.py lines 10\u201320",
                1,
                ["src/main.py"],
            ),
        ],
        ids=[
            "standard_range",
            "single_line",
            "colon_single",
            "colon_range",
            "multiple_citations",
            "no_citations",
            "special_chars_filename",
            "deeply_nested_path",
            "en_dash_range",
        ],
    )
    def test_citation_extraction_golden(self, answer_text, expected_count, expected_files):
        citations = extract_citations(answer_text)
        assert len(citations) == expected_count
        extracted_files = [c.file for c in citations]
        for f in expected_files:
            assert f in extracted_files, f"Expected file {f} not found in {extracted_files}"

    def test_citation_line_numbers_correct(self):
        citations = extract_citations("src/auth.py lines 10-20")
        assert len(citations) == 1
        assert citations[0].line_start == 10
        assert citations[0].line_end == 20

    def test_citation_single_line_start_equals_end(self):
        citations = extract_citations("src/auth.py line 5")
        assert len(citations) == 1
        assert citations[0].line_start == 5
        assert citations[0].line_end == 5

    def test_citation_str_representation(self):
        citations = extract_citations("src/auth.py lines 10-20")
        assert len(citations) == 1
        s = str(citations[0])
        assert "src/auth.py" in s
        assert "10" in s
        assert "20" in s
