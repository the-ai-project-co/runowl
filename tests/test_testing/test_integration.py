"""Integration tests for the full review + test flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from testing.executor import execute_suite
from testing.models import FrameworkType, TestCase, TestResult, TestStatus, TestSuite, TestType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_suite(unit_count: int = 2, e2e_count: int = 0) -> TestSuite:
    suite = TestSuite(pr_ref="owner/repo#42", framework=FrameworkType.PYTEST)
    for i in range(unit_count):
        suite.cases.append(TestCase(id=f"u{i:04d}", name=f"test_unit_{i}", type=TestType.UNIT))
    for i in range(e2e_count):
        suite.cases.append(TestCase(id=f"e{i:04d}", name=f"test_e2e_{i}", type=TestType.E2E))
    return suite


def _make_settings(*, with_anthropic: bool = True) -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = "sk-ant-test" if with_anthropic else None
    s.github_token = "gh_token"
    s.gemini_api_key = "gemini_key"
    return s


# ---------------------------------------------------------------------------
# execute_suite dispatch logic
# ---------------------------------------------------------------------------


class TestExecuteSuiteDispatch:
    @pytest.mark.asyncio
    async def test_unit_only_calls_only_unit_runner(self) -> None:
        suite = _make_suite(unit_count=2, e2e_count=0)
        unit_results = [
            TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS)
            for c in suite.cases
        ]

        with (
            patch("testing.executor.run_unit_tests", new_callable=AsyncMock, return_value=unit_results) as mock_unit,
            patch("testing.executor.run_e2e_tests", new_callable=AsyncMock) as mock_e2e,
            patch("testing.executor.save_suite"),
            patch("testing.executor.attach_recordings"),
        ):
            result = await execute_suite(suite)

        mock_unit.assert_called_once()
        mock_e2e.assert_not_called()
        assert len(result.results) == 2
        assert all(r.status == TestStatus.PASS for r in result.results)

    @pytest.mark.asyncio
    async def test_e2e_only_calls_only_e2e_runner(self) -> None:
        suite = _make_suite(unit_count=0, e2e_count=2)
        e2e_results = [
            TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS)
            for c in suite.cases
        ]

        with (
            patch("testing.executor.run_unit_tests", new_callable=AsyncMock) as mock_unit,
            patch("testing.executor.run_e2e_tests", new_callable=AsyncMock, return_value=e2e_results) as mock_e2e,
            patch("testing.executor.detect_preview_url", new_callable=AsyncMock, return_value=None),
            patch("testing.executor.save_suite"),
            patch("testing.executor.attach_recordings"),
        ):
            result = await execute_suite(suite)

        mock_unit.assert_not_called()
        mock_e2e.assert_called_once()
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_mixed_suite_calls_both_runners(self) -> None:
        suite = _make_suite(unit_count=2, e2e_count=1)
        unit_results = [
            TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS)
            for c in suite.cases if c.type == TestType.UNIT
        ]
        e2e_results = [
            TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS)
            for c in suite.cases if c.type == TestType.E2E
        ]

        with (
            patch("testing.executor.run_unit_tests", new_callable=AsyncMock, return_value=unit_results),
            patch("testing.executor.run_e2e_tests", new_callable=AsyncMock, return_value=e2e_results),
            patch("testing.executor.detect_preview_url", new_callable=AsyncMock, return_value=None),
            patch("testing.executor.save_suite"),
            patch("testing.executor.attach_recordings"),
        ):
            result = await execute_suite(suite, pr_body="Preview URL: https://preview.netlify.app")

        assert len(result.results) == 3

    @pytest.mark.asyncio
    async def test_e2e_runner_called_with_detected_preview_url(self) -> None:
        suite = _make_suite(unit_count=0, e2e_count=1)
        e2e_results = [
            TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS)
            for c in suite.cases
        ]

        with (
            patch("testing.executor.run_e2e_tests", new_callable=AsyncMock, return_value=e2e_results),
            patch(
                "testing.executor.detect_preview_url",
                new_callable=AsyncMock,
                return_value="https://pr42.netlify.app",
            ) as mock_detect,
            patch("testing.executor.save_suite"),
            patch("testing.executor.attach_recordings"),
        ):
            await execute_suite(suite, pr_body="Preview URL: https://pr42.netlify.app")

        mock_detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_suite_is_persisted(self) -> None:
        suite = _make_suite(unit_count=1)
        results = [TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS) for c in suite.cases]

        with (
            patch("testing.executor.run_unit_tests", new_callable=AsyncMock, return_value=results),
            patch("testing.executor.save_suite") as mock_save,
            patch("testing.executor.attach_recordings"),
        ):
            await execute_suite(suite)

        mock_save.assert_called_once_with(suite)


# ---------------------------------------------------------------------------
# Webhook flow: run_review_job with test generation
# ---------------------------------------------------------------------------


class TestWebhookReviewWithTests:
    def _make_event(self) -> MagicMock:
        event = MagicMock()
        event.owner = "owner"
        event.repo = "repo"
        event.pr_number = 42
        event.head_sha = "deadbeef"
        return event

    def _make_review_result(self) -> MagicMock:
        result = MagicMock()
        result.success = True
        result.findings = []
        result.error = None
        return result

    def _make_gen_result(self) -> MagicMock:
        suite = TestSuite(pr_ref="owner/repo#42", framework=FrameworkType.PYTEST)
        suite.generation_success = True
        gen = MagicMock()
        gen.success = True
        gen.suite = suite
        return gen

    @pytest.mark.asyncio
    async def test_posts_two_comments_review_and_tests(self) -> None:
        from webhook.reviewer import run_review_job

        settings = _make_settings(with_anthropic=True)
        event = self._make_event()
        review_result = self._make_review_result()
        gen_result = self._make_gen_result()
        executed_suite = gen_result.suite
        executed_suite.results.append(
            TestResult(test_id="t1", test_name="test_one", status=TestStatus.PASS)
        )

        with (
            patch("webhook.reviewer.GitHubClient") as MockGH,
            patch("webhook.reviewer.ReasoningEngine"),
            patch("webhook.reviewer.ReviewAgent") as MockReviewAgent,
            patch("webhook.reviewer.TestGenerationAgent") as MockTestAgent,
            patch("webhook.reviewer.execute_suite", new_callable=AsyncMock, return_value=executed_suite),
            patch("webhook.reviewer.start_check_run", new_callable=AsyncMock, return_value=1),
            patch("webhook.reviewer.finish_check_run", new_callable=AsyncMock),
        ):
            gh_ctx = AsyncMock()
            gh_ctx.get_pr_metadata = AsyncMock(return_value=_make_metadata_mock())
            gh_ctx.post_pr_comment = AsyncMock()
            MockGH.return_value.__aenter__ = AsyncMock(return_value=gh_ctx)
            MockGH.return_value.__aexit__ = AsyncMock(return_value=None)

            review_agent_instance = AsyncMock()
            review_agent_instance.review = AsyncMock(return_value=review_result)
            MockReviewAgent.return_value = review_agent_instance

            test_agent_instance = AsyncMock()
            test_agent_instance.generate = AsyncMock(return_value=gen_result)
            MockTestAgent.return_value = test_agent_instance

            await run_review_job(event, settings)

        # Should have posted 2 comments: review + test results
        assert gh_ctx.post_pr_comment.call_count == 2

    @pytest.mark.asyncio
    async def test_no_test_generation_when_no_anthropic_key(self) -> None:
        from webhook.reviewer import run_review_job

        settings = _make_settings(with_anthropic=False)
        event = self._make_event()
        review_result = self._make_review_result()

        with (
            patch("webhook.reviewer.GitHubClient") as MockGH,
            patch("webhook.reviewer.ReasoningEngine"),
            patch("webhook.reviewer.ReviewAgent") as MockReviewAgent,
            patch("webhook.reviewer.TestGenerationAgent") as MockTestAgent,
            patch("webhook.reviewer.start_check_run", new_callable=AsyncMock, return_value=1),
            patch("webhook.reviewer.finish_check_run", new_callable=AsyncMock),
        ):
            gh_ctx = AsyncMock()
            gh_ctx.post_pr_comment = AsyncMock()
            MockGH.return_value.__aenter__ = AsyncMock(return_value=gh_ctx)
            MockGH.return_value.__aexit__ = AsyncMock(return_value=None)

            review_agent_instance = AsyncMock()
            review_agent_instance.review = AsyncMock(return_value=review_result)
            MockReviewAgent.return_value = review_agent_instance

            await run_review_job(event, settings)

        MockTestAgent.assert_not_called()


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def _make_metadata_mock() -> MagicMock:
    meta = MagicMock()
    meta.title = "PR title"
    meta.author = "alice"
    meta.head_branch = "feature"
    meta.base_branch = "main"
    meta.head_sha = "abc"
    meta.changed_files = 1
    meta.additions = 5
    meta.deletions = 2
    meta.body = ""
    return meta


class TestCLIIntegration:
    PR_URL = "https://github.com/owner/repo/pull/42"

    def _mock_settings(self, with_anthropic: bool = True) -> MagicMock:
        s = MagicMock()
        s.anthropic_api_key = "sk-ant" if with_anthropic else None
        s.github_token = "gh"
        s.gemini_api_key = "gemini"
        return s

    def _mock_review_result(self) -> MagicMock:
        from review.models import ReviewResult
        r = MagicMock(spec=ReviewResult)
        r.findings = []
        r.success = True
        r.pr_ref = "owner/repo#42"
        r.error = None
        r.execution = MagicMock()
        r.execution.steps = []
        return r

    def _mock_gen_result(self) -> MagicMock:
        suite = TestSuite(pr_ref="owner/repo#42", framework=FrameworkType.PYTEST)
        suite.generation_success = True
        r = MagicMock()
        r.success = True
        r.suite = suite
        r.error = None
        return r

    def test_review_exits_0_when_no_findings(self) -> None:
        from runowl.cli import app

        runner = CliRunner()
        review_result = self._mock_review_result()

        with (
            patch("runowl.cli._settings", return_value=self._mock_settings(with_anthropic=False)),
            patch("runowl.cli.GitHubClient") as MockGH,
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as MockAgent,
        ):
            gh = AsyncMock()
            gh.close = AsyncMock()
            MockGH.return_value = gh

            agent_inst = AsyncMock()
            agent_inst.review = AsyncMock(return_value=review_result)
            MockAgent.return_value = agent_inst

            result = runner.invoke(app, ["review", "--url", self.PR_URL])

        assert result.exit_code == 0

    def test_review_with_test_flag_calls_test_generation(self) -> None:
        from runowl.cli import app

        runner = CliRunner()
        review_result = self._mock_review_result()
        gen_result = self._mock_gen_result()
        executed_suite = gen_result.suite
        executed_suite.results.append(
            TestResult(test_id="t1", test_name="test_one", status=TestStatus.PASS)
        )

        with (
            patch("runowl.cli._settings", return_value=self._mock_settings()),
            patch("runowl.cli.GitHubClient") as MockGH,
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as MockReviewAgent,
            patch("testing.generator.TestGenerationAgent") as MockTestAgent,
            patch("testing.executor.execute_suite", new_callable=AsyncMock, return_value=executed_suite),
        ):
            gh = AsyncMock()
            gh.close = AsyncMock()
            gh.get_pr_metadata = AsyncMock(return_value=_make_metadata_mock())
            MockGH.return_value = gh

            review_agent = AsyncMock()
            review_agent.review = AsyncMock(return_value=review_result)
            MockReviewAgent.return_value = review_agent

            test_agent = AsyncMock()
            test_agent.generate = AsyncMock(return_value=gen_result)
            MockTestAgent.return_value = test_agent

            result = runner.invoke(app, ["review", "--url", self.PR_URL, "--test"])

        assert result.exit_code == 0

    def test_test_only_skips_review(self) -> None:
        from runowl.cli import app

        runner = CliRunner()
        gen_result = self._mock_gen_result()
        executed_suite = gen_result.suite
        executed_suite.results.append(
            TestResult(test_id="t1", test_name="test_one", status=TestStatus.PASS)
        )

        with (
            patch("runowl.cli._settings", return_value=self._mock_settings()),
            patch("runowl.cli.GitHubClient") as MockGH,
            patch("runowl.cli.ReviewAgent") as MockReviewAgent,
            patch("testing.generator.TestGenerationAgent") as MockTestAgent,
            patch("testing.executor.execute_suite", new_callable=AsyncMock, return_value=executed_suite),
        ):
            gh = AsyncMock()
            gh.close = AsyncMock()
            gh.get_pr_metadata = AsyncMock(return_value=_make_metadata_mock())
            MockGH.return_value = gh

            test_agent = AsyncMock()
            test_agent.generate = AsyncMock(return_value=gen_result)
            MockTestAgent.return_value = test_agent

            result = runner.invoke(app, ["review", "--url", self.PR_URL, "--test-only"])

        MockReviewAgent.assert_not_called()
        assert result.exit_code == 0

    def test_json_output_includes_tests_key_when_test_flag_used(self) -> None:
        import json as _json

        from runowl.cli import app

        runner = CliRunner()
        review_result = self._mock_review_result()
        gen_result = self._mock_gen_result()
        executed_suite = gen_result.suite
        executed_suite.results.append(
            TestResult(test_id="t1", test_name="test_one", status=TestStatus.PASS)
        )

        with (
            patch("runowl.cli._settings", return_value=self._mock_settings()),
            patch("runowl.cli.GitHubClient") as MockGH,
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as MockReviewAgent,
            patch("testing.generator.TestGenerationAgent") as MockTestAgent,
            patch("testing.executor.execute_suite", new_callable=AsyncMock, return_value=executed_suite),
        ):
            gh = AsyncMock()
            gh.close = AsyncMock()
            gh.get_pr_metadata = AsyncMock(return_value=_make_metadata_mock())
            MockGH.return_value = gh

            review_agent = AsyncMock()
            review_agent.review = AsyncMock(return_value=review_result)
            MockReviewAgent.return_value = review_agent

            test_agent = AsyncMock()
            test_agent.generate = AsyncMock(return_value=gen_result)
            MockTestAgent.return_value = test_agent

            result = runner.invoke(
                app, ["review", "--url", self.PR_URL, "--test", "--output", "json"]
            )

        assert result.exit_code == 0
        # Extract JSON from output
        output = result.output.strip()
        data = _json.loads(output)
        assert "tests" in data
        assert "suite_id" in data["tests"]

    def test_json_output_without_test_flag_has_no_tests_key(self) -> None:
        import json as _json

        from runowl.cli import app

        runner = CliRunner()
        review_result = self._mock_review_result()

        with (
            patch("runowl.cli._settings", return_value=self._mock_settings(with_anthropic=False)),
            patch("runowl.cli.GitHubClient") as MockGH,
            patch("runowl.cli.ReasoningEngine"),
            patch("runowl.cli.ReviewAgent") as MockReviewAgent,
        ):
            gh = AsyncMock()
            gh.close = AsyncMock()
            MockGH.return_value = gh

            review_agent = AsyncMock()
            review_agent.review = AsyncMock(return_value=review_result)
            MockReviewAgent.return_value = review_agent

            result = runner.invoke(
                app, ["review", "--url", self.PR_URL, "--output", "json"]
            )

        assert result.exit_code == 0
        data = _json.loads(result.output.strip())
        assert "tests" not in data
