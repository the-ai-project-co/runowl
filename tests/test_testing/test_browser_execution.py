"""Tests for browser execution features: Firefox, parallel execution, and retry logic."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.docker_runner import (
    _split_shards,
    _write_playwright_config,
    run_e2e_tests,
)
from testing.models import TestCase, TestResult, TestStatus


def _make_case(test_id: str = "br000001", code: str = "await page.goto('/')") -> TestCase:
    return TestCase(id=test_id, name=f"test_{test_id}", code=code)


# ---------------------------------------------------------------------------
# Firefox browser support in Playwright config
# ---------------------------------------------------------------------------


class TestFirefoxBrowserSupport:
    def test_chromium_only_no_projects_block(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None, browsers=("chromium",))
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "projects:" not in content
        assert "firefox" not in content

    def test_firefox_added_produces_projects_block(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None, browsers=("chromium", "firefox"))
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "projects:" in content
        assert "Desktop Firefox" in content
        assert "Desktop Chrome" in content

    def test_firefox_only_produces_project_entry(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None, browsers=("firefox",))
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "Desktop Firefox" in content
        assert "Desktop Chrome" not in content


# ---------------------------------------------------------------------------
# Shard splitting
# ---------------------------------------------------------------------------


class TestSplitShards:
    def test_single_worker_returns_one_shard(self) -> None:
        cases = [_make_case(str(i)) for i in range(4)]
        shards = _split_shards(cases, 1)
        assert len(shards) == 1
        assert shards[0] == cases

    def test_two_workers_splits_roughly_evenly(self) -> None:
        cases = [_make_case(str(i)) for i in range(4)]
        shards = _split_shards(cases, 2)
        assert len(shards) == 2
        assert sum(len(s) for s in shards) == 4

    def test_more_workers_than_cases_gives_one_per_case(self) -> None:
        cases = [_make_case(str(i)) for i in range(3)]
        shards = _split_shards(cases, 10)
        assert sum(len(s) for s in shards) == 3

    def test_shard_order_is_preserved(self) -> None:
        cases = [_make_case(str(i)) for i in range(6)]
        shards = _split_shards(cases, 3)
        flat = [c for shard in shards for c in shard]
        assert flat == cases


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


def _make_result(test_id: str, status: TestStatus) -> TestResult:
    return TestResult(test_id=test_id, test_name=f"test_{test_id}", status=status)


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retry_turns_fail_into_pass(self) -> None:
        """First run fails, retry passes — result should be PASS with retry_count=1."""
        from testing.docker_runner import _retry_failures

        case = _make_case("retry001")
        initial_results = [TestResult(test_id="retry001", test_name="test_retry001", status=TestStatus.FAIL)]

        call_count = 0

        async def _fake_run_shard(shard, **kwargs):
            nonlocal call_count
            call_count += 1
            return [TestResult(test_id="retry001", test_name="test_retry001", status=TestStatus.PASS)]

        with patch("testing.docker_runner._run_shard", side_effect=_fake_run_shard):
            results = await _retry_failures(
                results=initial_results,
                cases=[case],
                preview_url=None,
                timeout=30,
                pool=None,
                browsers=("chromium",),
                max_retries=2,
            )

        assert results[0].status == TestStatus.PASS
        assert results[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_when_all_pass(self) -> None:
        """If all tests pass, _run_shard is never called again."""
        from testing.docker_runner import _retry_failures

        case = _make_case("pass001")
        initial_results = [TestResult(test_id="pass001", test_name="test_pass001", status=TestStatus.PASS)]

        with patch("testing.docker_runner._run_shard", new_callable=AsyncMock) as mock_shard:
            results = await _retry_failures(
                results=initial_results,
                cases=[case],
                preview_url=None,
                timeout=30,
                pool=None,
                browsers=("chromium",),
                max_retries=3,
            )

        mock_shard.assert_not_called()
        assert results[0].status == TestStatus.PASS

    @pytest.mark.asyncio
    async def test_retry_count_set_on_retried_result(self) -> None:
        """retry_count on the result reflects the attempt number."""
        from testing.docker_runner import _retry_failures

        case = _make_case("rc001")
        initial_results = [TestResult(test_id="rc001", test_name="test_rc001", status=TestStatus.FAIL)]

        attempt_no = [0]

        async def _fake_shard(shard, **kwargs):
            attempt_no[0] += 1
            r = TestResult(test_id="rc001", test_name="test_rc001", status=TestStatus.FAIL)
            return [r]

        with patch("testing.docker_runner._run_shard", side_effect=_fake_shard):
            results = await _retry_failures(
                results=initial_results,
                cases=[case],
                preview_url=None,
                timeout=30,
                pool=None,
                browsers=("chromium",),
                max_retries=2,
            )

        # Last retry attempt = 2
        assert results[0].retry_count == 2


# ---------------------------------------------------------------------------
# Parallel execution — verify multiple shards dispatched
# ---------------------------------------------------------------------------


class TestParallelExecution:
    @pytest.mark.asyncio
    async def test_two_workers_dispatch_two_shards(self) -> None:
        """With max_workers=2 and 4 cases, _run_shard is called twice."""
        cases = [_make_case(str(i)) for i in range(4)]

        shard_sizes: list[int] = []

        async def _fake_shard(shard, **kwargs):
            shard_sizes.append(len(shard))
            return [
                TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS)
                for c in shard
            ]

        import builtins
        original = builtins.__import__

        def _pass_docker(name, *args, **kwargs):
            if name == "docker":
                return MagicMock()
            return original(name, *args, **kwargs)

        with (
            patch("testing.docker_runner._run_shard", side_effect=_fake_shard),
            patch("builtins.__import__", side_effect=_pass_docker),
        ):
            results = await run_e2e_tests(cases, max_workers=2)

        assert len(shard_sizes) == 2
        assert sum(shard_sizes) == 4
        assert len(results) == 4
        assert all(r.status == TestStatus.PASS for r in results)

    @pytest.mark.asyncio
    async def test_results_are_in_original_case_order(self) -> None:
        """Results from multiple shards are merged in the original case order."""
        cases = [_make_case(str(i)) for i in range(4)]
        case_ids = [c.id for c in cases]

        async def _fake_shard(shard, **kwargs):
            return [
                TestResult(test_id=c.id, test_name=c.name, status=TestStatus.PASS)
                for c in shard
            ]

        import builtins
        original = builtins.__import__

        def _pass_docker(name, *args, **kwargs):
            if name == "docker":
                return MagicMock()
            return original(name, *args, **kwargs)

        with (
            patch("testing.docker_runner._run_shard", side_effect=_fake_shard),
            patch("builtins.__import__", side_effect=_pass_docker),
        ):
            results = await run_e2e_tests(cases, max_workers=2)

        result_ids = [r.test_id for r in results]
        assert result_ids == case_ids
