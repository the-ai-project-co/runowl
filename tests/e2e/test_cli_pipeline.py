"""End-to-end tests for the Python CLI (runowl.cli).

Uses typer.testing.CliRunner with real CLI invocation and real output
formatting.  External backends (GitHub, ReasoningEngine, ReviewAgent,
QAEngine) are patched at the top level inside runowl.cli.
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from runowl.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")


def plain(text: str) -> str:
    """Strip ANSI escape codes so assertions work regardless of Rich colour output."""
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

_VALID_URL = "https://github.com/owner/repo/pull/42"
_INVALID_URL = "https://not-a-github-url.com/foo"


def _mock_settings() -> MagicMock:
    return MagicMock(github_token="ghp_fake", gemini_api_key="fake-gemini-key")


def _mock_gh() -> AsyncMock:
    gh = AsyncMock()
    gh.close = AsyncMock()
    return gh


# ---------------------------------------------------------------------------
# 1. Help output shows both commands with all flags
# ---------------------------------------------------------------------------


class TestHelpOutput:
    def test_top_level_help_shows_review_and_ask(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        out = plain(result.output)
        assert "review" in out
        assert "ask" in out

    def test_review_help_shows_all_flags(self) -> None:
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        out = plain(result.output)
        for flag in ("--url", "--expert", "--output", "--submit", "--quiet"):
            assert flag in out, f"Missing flag {flag} in review help"

    def test_ask_help_shows_all_flags(self) -> None:
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0
        out = plain(result.output)
        for flag in ("--url", "--question"):
            assert flag in out, f"Missing flag {flag} in ask help"


# ---------------------------------------------------------------------------
# 2. Review with mocked backend -> clean exit, rich output
# ---------------------------------------------------------------------------


class TestReviewCleanExit:
    def test_review_no_findings_exits_zero(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(app, ["review", "--url", _VALID_URL])

        assert result.exit_code == 0
        out = plain(result.output)
        assert "no issues" in out.lower() or "No issues" in result.output

    def test_review_rich_output_is_default(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(app, ["review", "--url", _VALID_URL])

        # Should succeed without specifying --output (defaults to rich)
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 3. Review with JSON output -> valid JSON in stdout
# ---------------------------------------------------------------------------


class TestReviewJSONOutput:
    def test_json_output_is_valid(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app,
                ["review", "--url", _VALID_URL, "--output", "json"],
            )

        assert result.exit_code == 0
        out = plain(result.output).strip()
        data = json.loads(out)
        assert "success" in data
        assert "findings" in data

    def test_json_output_quiet(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app,
                ["review", "--url", _VALID_URL, "--output", "json", "--quiet"],
            )

        assert result.exit_code == 0
        out = plain(result.output).strip()
        # Quiet JSON should still be valid
        data = json.loads(out)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# 4. Review with markdown output
# ---------------------------------------------------------------------------


class TestReviewMarkdownOutput:
    def test_markdown_output_contains_header(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app,
                ["review", "--url", _VALID_URL, "--output", "markdown"],
            )

        assert result.exit_code == 0
        out = plain(result.output)
        assert "RunOwl" in out
        assert "No issues" in out or "No blocking" in out


# ---------------------------------------------------------------------------
# 5. Review with findings -> non-zero exit code
# ---------------------------------------------------------------------------


class TestReviewWithFindings:
    def test_findings_cause_nonzero_exit(self) -> None:
        from review.models import Citation, Finding, FindingType, ReviewResult, Severity

        finding = Finding(
            severity=Severity.P1,
            type=FindingType.BUG,
            title="Null pointer risk",
            description="Variable may be None when accessed.",
            citation=Citation(file="src/auth.py", line_start=15, line_end=15),
            fix="Add a None check before access.",
        )
        mock_result = ReviewResult(findings=[finding], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(app, ["review", "--url", _VALID_URL])

        assert result.exit_code != 0

    def test_findings_json_nonzero_exit(self) -> None:
        from review.models import Citation, Finding, FindingType, ReviewResult, Severity

        finding = Finding(
            severity=Severity.P2,
            type=FindingType.SECURITY,
            title="Hardcoded secret",
            description="API key found in source.",
            citation=Citation(file="src/config.py", line_start=5, line_end=5),
        )
        mock_result = ReviewResult(findings=[finding], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app, ["review", "--url", _VALID_URL, "--output", "json"]
            )

        assert result.exit_code != 0
        out = plain(result.output).strip()
        data = json.loads(out)
        assert len(data["findings"]) == 1


# ---------------------------------------------------------------------------
# 6. Ask with single question -> answer in output
# ---------------------------------------------------------------------------


class TestAskCommand:
    def test_ask_single_question_returns_answer(self) -> None:
        from qa.models import QAMessage

        mock_msg = QAMessage(
            role="assistant",
            question="What does the change do?",
            answer="It adds validation to the signup form.",
            citations=["src/forms.py:42"],
        )

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.QAEngine") as mock_engine_cls,
        ):
            engine = AsyncMock()
            engine.ask = AsyncMock(return_value=mock_msg)
            mock_engine_cls.return_value = engine

            result = runner.invoke(
                app,
                [
                    "ask",
                    "--url", _VALID_URL,
                    "--question", "What does the change do?",
                ],
            )

        assert result.exit_code == 0
        out = plain(result.output)
        assert "validation" in out.lower()
        assert "signup" in out.lower()

    def test_ask_passes_question_to_engine(self) -> None:
        from qa.models import QAMessage

        mock_msg = QAMessage(
            role="assistant",
            question="Is there a race condition?",
            answer="No race condition detected.",
            citations=[],
        )

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.QAEngine") as mock_engine_cls,
        ):
            engine = AsyncMock()
            engine.ask = AsyncMock(return_value=mock_msg)
            mock_engine_cls.return_value = engine

            runner.invoke(
                app,
                [
                    "ask",
                    "--url", _VALID_URL,
                    "--question", "Is there a race condition?",
                ],
            )

            engine.ask.assert_called_once()
            call_args = engine.ask.call_args
            assert call_args[0][1] == "Is there a race condition?"


# ---------------------------------------------------------------------------
# 7. Missing URL -> error exit
# ---------------------------------------------------------------------------


class TestMissingURL:
    def test_review_missing_url(self) -> None:
        result = runner.invoke(app, ["review"])
        assert result.exit_code != 0

    def test_ask_missing_url(self) -> None:
        result = runner.invoke(app, ["ask"])
        assert result.exit_code != 0

    def test_ask_missing_question(self) -> None:
        result = runner.invoke(app, ["ask", "--url", _VALID_URL])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 8. Invalid URL -> error exit
# ---------------------------------------------------------------------------


class TestInvalidURL:
    def test_review_invalid_url(self) -> None:
        with patch("runowl.cli._settings", return_value=_mock_settings()):
            result = runner.invoke(app, ["review", "--url", _INVALID_URL])
        assert result.exit_code != 0
        out = plain(result.output)
        assert "invalid" in out.lower() or "Invalid" in result.output

    def test_ask_invalid_url(self) -> None:
        with patch("runowl.cli._settings", return_value=_mock_settings()):
            result = runner.invoke(
                app,
                ["ask", "--url", _INVALID_URL, "--question", "test"],
            )
        assert result.exit_code != 0

    def test_review_partial_url(self) -> None:
        with patch("runowl.cli._settings", return_value=_mock_settings()):
            result = runner.invoke(
                app, ["review", "--url", "https://github.com/owner/repo"]
            )
        assert result.exit_code != 0

    def test_review_invalid_output_format(self) -> None:
        with patch("runowl.cli._settings", return_value=_mock_settings()):
            result = runner.invoke(
                app,
                ["review", "--url", _VALID_URL, "--output", "xml"],
            )
        assert result.exit_code != 0
        out = plain(result.output)
        assert "invalid" in out.lower() or "xml" in out.lower()


# ---------------------------------------------------------------------------
# 9. Settings error (missing API key) -> error exit
# ---------------------------------------------------------------------------


class TestSettingsError:
    def test_review_settings_error(self) -> None:
        with patch("runowl.cli._settings", side_effect=Exception("gemini_api_key required")):
            result = runner.invoke(app, ["review", "--url", _VALID_URL])
        assert result.exit_code != 0
        out = plain(result.output)
        assert "configuration" in out.lower() or "error" in out.lower()

    def test_ask_settings_error(self) -> None:
        with patch("runowl.cli._settings", side_effect=Exception("missing API key")):
            result = runner.invoke(
                app,
                ["ask", "--url", _VALID_URL, "--question", "test"],
            )
        assert result.exit_code != 0
        out = plain(result.output)
        assert "configuration" in out.lower() or "error" in out.lower()

    def test_settings_error_message_included(self) -> None:
        with patch("runowl.cli._settings", side_effect=Exception("gemini_api_key field required")):
            result = runner.invoke(app, ["review", "--url", _VALID_URL])
        assert result.exit_code != 0
        out = plain(result.output)
        assert "gemini_api_key" in out.lower() or "Configuration" in result.output


# ---------------------------------------------------------------------------
# 10. Review with --quiet flag
# ---------------------------------------------------------------------------


class TestQuietFlag:
    def test_quiet_review_no_findings(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app, ["review", "--url", _VALID_URL, "--quiet"]
            )

        assert result.exit_code == 0

    def test_quiet_review_with_findings(self) -> None:
        from review.models import Citation, Finding, FindingType, ReviewResult, Severity

        finding = Finding(
            severity=Severity.P3,
            type=FindingType.INFORMATIONAL,
            title="Minor style issue",
            description="Consider renaming variable.",
            citation=Citation(file="src/main.py", line_start=1, line_end=1),
        )
        mock_result = ReviewResult(findings=[finding], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app, ["review", "--url", _VALID_URL, "--quiet"]
            )

        # Findings still cause non-zero exit
        assert result.exit_code != 0

    def test_quiet_json_review(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app,
                ["review", "--url", _VALID_URL, "--output", "json", "--quiet"],
            )

        assert result.exit_code == 0
        out = plain(result.output).strip()
        data = json.loads(out)
        assert data["success"] is True

    def test_quiet_short_flag(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings", return_value=_mock_settings()),
            patch("runowl.cli.GitHubClient", return_value=_mock_gh()),
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            agent = AsyncMock()
            agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = agent

            result = runner.invoke(
                app, ["review", "--url", _VALID_URL, "-q"]
            )

        assert result.exit_code == 0
