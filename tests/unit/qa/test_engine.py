"""Unit tests for QA session models and command handling."""

from unittest.mock import MagicMock

from github.models import PRRef
from qa.engine import QAEngine
from qa.models import QAMessage, QASession

PR_REF = PRRef(owner="acme", repo="widget", number=9)


class TestQASession:
    def test_add_and_retrieve(self) -> None:
        session = QASession(pr_ref_str="acme/widget#9")
        msg = QAMessage(role="assistant", question="Q?", answer="A.")
        session.add(msg)
        assert len(session.messages) == 1

    def test_reset_clears_messages(self) -> None:
        session = QASession(pr_ref_str="acme/widget#9")
        session.add(QAMessage(role="assistant", question="Q?", answer="A."))
        session.reset()
        assert len(session.messages) == 0

    def test_last_n_returns_correct_slice(self) -> None:
        session = QASession(pr_ref_str="acme/widget#9")
        for i in range(10):
            session.add(QAMessage(role="assistant", question=f"Q{i}", answer=f"A{i}"))
        assert len(session.last_n(3)) == 3

    def test_history_text_includes_questions(self) -> None:
        session = QASession(pr_ref_str="acme/widget#9")
        session.add(
            QAMessage(role="assistant", question="What is JWT?", answer="A token standard.")
        )
        assert "What is JWT?" in session.history_text


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
