"""Tests for the Q&A engine."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from github.models import PRMetadata, PRRef
from qa.engine import QAEngine
from qa.models import CodeSelection, QASession, SelectionMode
from reasoning.models import ReasoningTrace, RLMResult

PR_REF = PRRef(owner="acme", repo="widget", number=9)


def _make_metadata() -> PRMetadata:
    from github.models import PRFile

    return PRMetadata(
        number=9,
        title="Refactor auth",
        body="Cleans up auth module",
        author="carol",
        base_branch="main",
        head_branch="refactor/auth",
        head_sha="sha999",
        base_sha="sha000",
        state="open",
        commits=[],
        files=[
            PRFile(
                filename="src/auth.py",
                status="modified",
                additions=5,
                deletions=2,
                changes=7,
                patch="@@ -1,3 +1,6 @@\n ctx\n-old\n+new\n+extra",
            )
        ],
        additions=5,
        deletions=2,
        changed_files=1,
    )


@pytest.fixture
def mock_gh() -> MagicMock:
    gh = MagicMock()
    gh.get_pr_metadata = AsyncMock(return_value=_make_metadata())
    return gh


@pytest.fixture
def mock_engine() -> MagicMock:
    engine = MagicMock()
    engine.ask = AsyncMock(
        return_value=RLMResult(
            output="The auth module uses JWT tokens for session management.",
            trace=ReasoningTrace(),
            conversation=[],
            success=True,
        )
    )
    return engine


class TestQASession:
    def test_add_and_retrieve(self) -> None:
        from qa.models import QAMessage

        session = QASession(pr_ref_str="acme/widget#9")
        msg = QAMessage(role="assistant", question="Q?", answer="A.")
        session.add(msg)
        assert len(session.messages) == 1

    def test_reset_clears_messages(self) -> None:
        from qa.models import QAMessage

        session = QASession(pr_ref_str="acme/widget#9")
        session.add(QAMessage(role="assistant", question="Q?", answer="A."))
        session.reset()
        assert len(session.messages) == 0

    def test_last_n_returns_correct_slice(self) -> None:
        from qa.models import QAMessage

        session = QASession(pr_ref_str="acme/widget#9")
        for i in range(10):
            session.add(QAMessage(role="assistant", question=f"Q{i}", answer=f"A{i}"))
        assert len(session.last_n(3)) == 3

    def test_history_text_includes_questions(self) -> None:
        from qa.models import QAMessage

        session = QASession(pr_ref_str="acme/widget#9")
        session.add(
            QAMessage(role="assistant", question="What is JWT?", answer="A token standard.")
        )
        assert "What is JWT?" in session.history_text


class TestQAEngine:
    async def test_ask_returns_message(self, mock_gh: MagicMock, mock_engine: MagicMock) -> None:
        engine = QAEngine(mock_gh, mock_engine)
        msg = await engine.ask(PR_REF, "How does auth work?")
        assert msg.answer == "The auth module uses JWT tokens for session management."
        assert msg.question == "How does auth work?"

    async def test_message_stored_in_session(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        qa = QAEngine(mock_gh, mock_engine)
        await qa.ask(PR_REF, "First question?")
        await qa.ask(PR_REF, "Second question?")
        session = qa.get_session(PR_REF)
        assert len(session.messages) == 2

    async def test_history_passed_to_reasoning_engine(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        qa = QAEngine(mock_gh, mock_engine)
        await qa.ask(PR_REF, "First question?")
        await qa.ask(PR_REF, "Follow-up?")
        # Second call should pass conversation history
        second_call_kwargs = mock_engine.ask.call_args_list[1][1]
        assert len(second_call_kwargs.get("conversation", [])) > 0

    async def test_with_code_selection(self, mock_gh: MagicMock, mock_engine: MagicMock) -> None:
        qa = QAEngine(mock_gh, mock_engine)
        sel = CodeSelection(
            mode=SelectionMode.RANGE,
            file="src/auth.py",
            content="def login():\n    pass",
            line_start=1,
            line_end=2,
        )
        msg = await qa.ask(PR_REF, "What does this do?", selection=sel)
        assert msg.selection == sel

    async def test_citations_extracted_from_answer(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        mock_engine.ask = AsyncMock(
            return_value=RLMResult(
                output="See src/auth.py lines 10-15 for the token check.",
                trace=ReasoningTrace(),
                conversation=[],
                success=True,
            )
        )
        qa = QAEngine(mock_gh, mock_engine)
        msg = await qa.ask(PR_REF, "Where is the token check?")
        assert any("src/auth.py" in c for c in msg.citations)

    async def test_reset_session(self, mock_gh: MagicMock, mock_engine: MagicMock) -> None:
        qa = QAEngine(mock_gh, mock_engine)
        await qa.ask(PR_REF, "Q?")
        qa.reset_session(PR_REF)
        assert len(qa.get_session(PR_REF).messages) == 0


class TestQAEngineCommands:
    def _engine(self) -> QAEngine:
        return QAEngine(MagicMock(), MagicMock())

    def test_quit_returns_session_end(self) -> None:
        qa = self._engine()
        assert qa.handle_command(PR_REF, "quit") == "SESSION_END"
        assert qa.handle_command(PR_REF, "exit") == "SESSION_END"
        assert qa.handle_command(PR_REF, "q") == "SESSION_END"

    def test_help_returns_commands_list(self) -> None:
        qa = self._engine()
        result = qa.handle_command(PR_REF, "help")
        assert result is not None
        assert "reset" in result
        assert "history" in result

    def test_reset_clears_session(self) -> None:
        from qa.models import QAMessage

        qa = self._engine()
        qa.get_session(PR_REF).add(QAMessage(role="assistant", question="Q?", answer="A."))
        qa.handle_command(PR_REF, "reset")
        assert len(qa.get_session(PR_REF).messages) == 0

    def test_history_with_no_messages(self) -> None:
        qa = self._engine()
        result = qa.handle_command(PR_REF, "history")
        assert "No conversation history" in (result or "")

    def test_files_without_loaded_pr(self) -> None:
        qa = self._engine()
        result = qa.handle_command(PR_REF, "files")
        assert "not yet loaded" in (result or "")

    def test_unknown_input_returns_none(self) -> None:
        qa = self._engine()
        assert qa.handle_command(PR_REF, "What is the meaning of life?") is None
