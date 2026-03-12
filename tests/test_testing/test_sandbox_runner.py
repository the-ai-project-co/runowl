"""Tests for testing.sandbox_runner — subprocess-based pytest/jest/vitest runner."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.models import FrameworkType, TestCase, TestStatus
from testing.sandbox_runner import (
    _extract_pytest_error,
    _parse_pytest_status,
    run_unit_tests,
)


def _make_case(name: str = "test_foo", framework: FrameworkType = FrameworkType.PYTEST) -> TestCase:
    return TestCase(id="abc12345", name=name, framework=framework, code="def test_foo(): pass")


# ---------------------------------------------------------------------------
# Pure logic — no subprocesses
# ---------------------------------------------------------------------------


class TestParsePytestStatus:
    def test_passed_when_output_contains_passed(self) -> None:
        assert _parse_pytest_status("1 passed", "test_abc.py", False) == TestStatus.PASS

    def test_failed_when_output_contains_failed(self) -> None:
        assert _parse_pytest_status("1 failed", "test_abc.py", False) == TestStatus.FAIL

    def test_error_when_output_contains_error(self) -> None:
        assert _parse_pytest_status("1 error", "test_abc.py", False) == TestStatus.ERROR

    def test_timeout_when_timed_out_flag_set(self) -> None:
        assert _parse_pytest_status("1 passed", "test_abc.py", True) == TestStatus.TIMEOUT

    def test_skip_when_no_recognisable_output(self) -> None:
        assert _parse_pytest_status("collecting ...", "test_abc.py", False) == TestStatus.SKIP


class TestExtractPytestError:
    def test_extracts_lines_after_failed_marker(self) -> None:
        stdout = "FAILED test_abc.py\nAssertionError: 1 != 2\n"
        error = _extract_pytest_error(stdout, "test_abc.py")
        assert "FAILED" in error
        assert "AssertionError" in error

    def test_returns_empty_when_file_not_in_output(self) -> None:
        error = _extract_pytest_error("1 passed", "test_other.py")
        assert error == ""

    def test_caps_at_20_lines(self) -> None:
        lines = ["FAILED test_abc.py"] + [f"line {i}" for i in range(25)]
        stdout = "\n".join(lines)
        error = _extract_pytest_error(stdout, "test_abc.py")
        assert len(error.splitlines()) <= 21  # 20 captured + the FAILED line


# ---------------------------------------------------------------------------
# Empty-list fast path
# ---------------------------------------------------------------------------


class TestRunUnitTestsEmptyList:
    @pytest.mark.asyncio
    async def test_empty_cases_returns_empty(self) -> None:
        result = await run_unit_tests([], FrameworkType.PYTEST)
        assert result == []


# ---------------------------------------------------------------------------
# Unknown framework → SKIP
# ---------------------------------------------------------------------------


class TestRunUnitTestsUnknownFramework:
    @pytest.mark.asyncio
    async def test_unknown_framework_returns_skip(self) -> None:
        cases = [_make_case()]
        results = await run_unit_tests(cases, FrameworkType.UNKNOWN)
        assert len(results) == 1
        assert results[0].status == TestStatus.SKIP
        assert "Unknown framework" in results[0].stderr


# ---------------------------------------------------------------------------
# Mocked subprocess — pytest happy path
# ---------------------------------------------------------------------------


class TestRunUnitTestsPytestMocked:
    @pytest.mark.asyncio
    async def test_passed_result_on_success_output(self) -> None:
        cases = [_make_case()]

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"1 passed", b""))
        mock_proc.returncode = 0

        with patch("testing.sandbox_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await run_unit_tests(cases, FrameworkType.PYTEST)

        assert len(results) == 1
        assert results[0].status == TestStatus.PASS
        assert results[0].test_id == cases[0].id

    @pytest.mark.asyncio
    async def test_failed_result_on_failure_output(self) -> None:
        cases = [_make_case()]

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"1 failed", b""))
        mock_proc.returncode = 1

        with patch("testing.sandbox_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await run_unit_tests(cases, FrameworkType.PYTEST)

        assert results[0].status == TestStatus.FAIL

    @pytest.mark.asyncio
    async def test_timeout_result_on_asyncio_timeout(self) -> None:
        cases = [_make_case()]

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = MagicMock()

        async def _killed_communicate():
            return b"", b""

        mock_proc.communicate.side_effect = None

        # Patch wait_for to raise TimeoutError on first call
        original_wait_for = asyncio.wait_for

        call_count = 0

        async def _fake_wait_for(coro, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # cancel the coro to avoid ResourceWarning
                coro.close()
                raise TimeoutError
            return await original_wait_for(coro, timeout)

        with (
            patch("testing.sandbox_runner.asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("testing.sandbox_runner.asyncio.wait_for", side_effect=_fake_wait_for),
        ):
            mock_proc.communicate = AsyncMock(return_value=(b"", b"Timed out"))
            results = await run_unit_tests(cases, FrameworkType.PYTEST, timeout=1)

        assert results[0].status == TestStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_error_result_when_pytest_not_found(self) -> None:
        cases = [_make_case()]

        with patch(
            "testing.sandbox_runner.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("pytest not found"),
        ):
            results = await run_unit_tests(cases, FrameworkType.PYTEST)

        assert results[0].status == TestStatus.ERROR
        assert "pytest" in results[0].stderr.lower()


# ---------------------------------------------------------------------------
# Mocked subprocess — jest/vitest
# ---------------------------------------------------------------------------


class TestRunUnitTestsJestMocked:
    @pytest.mark.asyncio
    async def test_jest_pass_on_exit_code_0(self) -> None:
        case = TestCase(id="ts001234", name="test_ts", framework=FrameworkType.JEST, code="it('ok', () => {})")

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Tests: 1 passed", b""))
        mock_proc.returncode = 0

        with patch("testing.sandbox_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await run_unit_tests([case], FrameworkType.JEST)

        assert results[0].status == TestStatus.PASS

    @pytest.mark.asyncio
    async def test_vitest_error_when_binary_not_found(self) -> None:
        case = TestCase(id="vt001234", name="test_vt", framework=FrameworkType.VITEST, code="")

        with patch(
            "testing.sandbox_runner.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("vitest not found"),
        ):
            results = await run_unit_tests([case], FrameworkType.VITEST)

        assert results[0].status == TestStatus.ERROR
        assert "vitest" in results[0].stderr.lower()
