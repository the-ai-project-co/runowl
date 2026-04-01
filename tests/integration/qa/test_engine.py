"""Integration tests for the Q&A engine (mocked backends)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from github.models import PRMetadata, PRRef
from qa.engine import QAEngine
from qa.models import CodeSelection, SelectionMode
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
