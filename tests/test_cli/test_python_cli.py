"""Tests for the Python CLI module (runowl.cli)."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

from runowl.cli import app
from typer.testing import CliRunner

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")


def plain(text: str) -> str:
    """Strip ANSI escape codes so assertions work regardless of Rich colour output."""
    return _ANSI_RE.sub("", text)


# ── Help & Version ─────────────────────────────────────────────────────────────


class TestHelp:
    def test_help_shows_commands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        out = plain(result.output)
        assert "review" in out
        assert "ask" in out

    def test_review_help(self) -> None:
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        out = plain(result.output)
        assert "--url" in out
        assert "--expert" in out
        assert "--output" in out
        assert "--submit" in out
        assert "--quiet" in out

    def test_ask_help(self) -> None:
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0
        out = plain(result.output)
        assert "--url" in out
        assert "--question" in out


# ── review command validation ─────────────────────────────────────────────────


class TestReviewCommand:
    def test_missing_url_exits_with_error(self) -> None:
        result = runner.invoke(app, ["review"])
        # Typer returns non-zero when required option is missing
        assert result.exit_code != 0

    def test_invalid_pr_url_exits_with_error(self) -> None:
        with patch("runowl.cli._settings") as mock_settings:
            mock_settings.return_value = MagicMock(github_token=None, gemini_api_key="test-key")
            result = runner.invoke(app, ["review", "--url", "https://not-a-github-url.com"])
            assert result.exit_code != 0

    def test_invalid_output_format_exits(self) -> None:
        with patch("runowl.cli._settings") as mock_settings:
            mock_settings.return_value = MagicMock(github_token=None, gemini_api_key="test-key")
            result = runner.invoke(
                app,
                [
                    "review",
                    "--url",
                    "https://github.com/owner/repo/pull/42",
                    "--output",
                    "xml",
                ],
            )
            assert result.exit_code != 0

    def test_review_runs_with_mocked_backend(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings") as mock_settings,
            patch("runowl.cli.GitHubClient") as mock_gh_cls,
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
        ):
            mock_settings.return_value = MagicMock(github_token=None, gemini_api_key="key")
            mock_gh = AsyncMock()
            mock_gh.close = AsyncMock()
            mock_gh_cls.return_value = mock_gh

            mock_agent = AsyncMock()
            mock_agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = mock_agent

            result = runner.invoke(
                app,
                [
                    "review",
                    "--url",
                    "https://github.com/owner/repo/pull/42",
                    "--quiet",
                ],
            )
            assert result.exit_code == 0

    def test_review_json_output(self) -> None:
        from review.models import ReviewResult

        mock_result = ReviewResult(findings=[], success=True)

        with (
            patch("runowl.cli._settings") as mock_settings,
            patch("runowl.cli.GitHubClient") as mock_gh_cls,
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as mock_agent_cls,
            patch("runowl.cli.format_review_json", return_value='{"findings":[]}'),
        ):
            mock_settings.return_value = MagicMock(github_token=None, gemini_api_key="key")
            mock_gh = AsyncMock()
            mock_gh.close = AsyncMock()
            mock_gh_cls.return_value = mock_gh

            mock_agent = AsyncMock()
            mock_agent.review = AsyncMock(return_value=mock_result)
            mock_agent_cls.return_value = mock_agent

            result = runner.invoke(
                app,
                [
                    "review",
                    "--url",
                    "https://github.com/owner/repo/pull/42",
                    "--output",
                    "json",
                    "--quiet",
                ],
            )
            assert result.exit_code == 0
            assert '{"findings":[]}' in plain(result.output)


# ── ask command validation ────────────────────────────────────────────────────


class TestAskCommand:
    def test_missing_url_exits_with_error(self) -> None:
        result = runner.invoke(app, ["ask"])
        assert result.exit_code != 0

    def test_ask_single_question_with_mocked_backend(self) -> None:
        from qa.models import QAMessage

        mock_msg = QAMessage(
            role="assistant",
            question="What does this do?",
            answer="It increments a counter.",
            citations=[],
        )

        with (
            patch("runowl.cli._settings") as mock_settings,
            patch("runowl.cli.GitHubClient") as mock_gh_cls,
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.QAEngine") as mock_engine_cls,
        ):
            mock_settings.return_value = MagicMock(github_token=None, gemini_api_key="key")
            mock_gh = AsyncMock()
            mock_gh.close = AsyncMock()
            mock_gh_cls.return_value = mock_gh

            mock_engine = AsyncMock()
            mock_engine.ask = AsyncMock(return_value=mock_msg)
            mock_engine_cls.return_value = mock_engine

            result = runner.invoke(
                app,
                [
                    "ask",
                    "--url",
                    "https://github.com/owner/repo/pull/42",
                    "--question",
                    "What does this do?",
                ],
            )
            assert result.exit_code == 0
            assert "It increments a counter." in plain(result.output)


# ── output formatting ─────────────────────────────────────────────────────────


class TestOutputFormatting:
    def test_no_findings_message(self) -> None:
        from runowl.cli import _print_rich_review

        from review.models import ReviewResult

        result = ReviewResult(findings=[], success=True)
        # Should not raise
        with patch("runowl.cli.console") as mock_console:
            _print_rich_review(result, quiet=False)
            mock_console.print.assert_called()

    def test_settings_error_exits(self) -> None:
        with patch("runowl.cli.Settings", side_effect=Exception("missing key")):
            result = runner.invoke(
                app,
                ["review", "--url", "https://github.com/owner/repo/pull/42"],
            )
            assert result.exit_code != 0
