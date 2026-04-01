"""Tests for ReviewAgent orchestration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from github.models import PRMetadata, PRRef
from reasoning.models import ReasoningTrace, RLMResult
from review.agent import ReviewAgent
from review.models import Severity

PR_REF = PRRef(owner="acme", repo="widget", number=3)

SAMPLE_REVIEW_OUTPUT = """
[P1] security: Hardcoded secret in config
File: src/config.py lines 5-5
Description: The JWT secret is hardcoded as a string literal.
Fix: Move to environment variable.

[P3] informational: Unused import
File: src/main.py:2
Description: The `os` module is imported but never used.
"""


def _make_metadata() -> PRMetadata:
    from github.models import PRFile

    return PRMetadata(
        number=3,
        title="Add config",
        body="Adds config module",
        author="bob",
        base_branch="main",
        head_branch="feat/config",
        head_sha="abc123",
        base_sha="def456",
        state="open",
        commits=[],
        files=[
            PRFile(
                filename="src/config.py",
                status="added",
                additions=10,
                deletions=0,
                changes=10,
                patch="@@ -0,0 +1,10 @@\n+JWT_SECRET = 'hardcoded'\n+# more lines\n",
            )
        ],
        additions=10,
        deletions=0,
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
    engine._step_cb = None
    engine.review_pr = AsyncMock(
        return_value=RLMResult(
            output=SAMPLE_REVIEW_OUTPUT,
            trace=ReasoningTrace(),
            conversation=[],
            success=True,
        )
    )
    engine.ask = AsyncMock(
        return_value=RLMResult(
            output="The JWT secret should be in an env var.",
            trace=ReasoningTrace(),
            conversation=[],
            success=True,
        )
    )
    return engine


class TestReviewAgent:
    async def test_returns_review_result(self, mock_gh: MagicMock, mock_engine: MagicMock) -> None:
        agent = ReviewAgent(mock_gh, mock_engine)
        result = await agent.review(PR_REF)
        assert result.success
        assert len(result.findings) == 2

    async def test_findings_severity_order(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        agent = ReviewAgent(mock_gh, mock_engine)
        result = await agent.review(PR_REF)
        severities = [f.severity for f in result.findings]
        # "Hardcoded secret" is promoted from P1 → P0 by the reclassifier
        assert severities[0] == Severity.P0
        assert severities[1] == Severity.P3

    async def test_engine_failure_returns_failure_result(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        mock_engine.review_pr = AsyncMock(
            return_value=RLMResult(
                output="",
                trace=ReasoningTrace(),
                conversation=[],
                success=False,
                error="Gemini quota exceeded",
            )
        )
        agent = ReviewAgent(mock_gh, mock_engine)
        result = await agent.review(PR_REF)
        assert not result.success
        assert "Gemini quota exceeded" in (result.error or "")

    async def test_github_error_returns_failure_result(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        mock_gh.get_pr_metadata = AsyncMock(side_effect=Exception("GitHub API down"))
        agent = ReviewAgent(mock_gh, mock_engine)
        result = await agent.review(PR_REF)
        assert not result.success

    async def test_step_callback_set_on_engine(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        agent = ReviewAgent(mock_gh, mock_engine)
        cb = MagicMock()
        await agent.review(PR_REF, step_callback=cb)
        assert mock_engine._step_cb == cb

    async def test_ask_returns_answer_and_conversation(
        self, mock_gh: MagicMock, mock_engine: MagicMock
    ) -> None:
        agent = ReviewAgent(mock_gh, mock_engine)
        answer, convo = await agent.ask(PR_REF, "Is the JWT secret safe?")
        assert "JWT" in answer
        assert isinstance(convo, list)
