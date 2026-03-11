"""Execute unit and integration tests inside the existing Deno sandbox.

For unit/integration tests we write the generated test code to a temp file,
then run the appropriate test runner (pytest / jest / vitest) as a subprocess
with strict resource limits. Results are captured and returned as TestResult objects.

E2E / browser tests are handled separately in docker_runner.py.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

from testing.models import Confidence, FrameworkType, TestCase, TestResult, TestStatus

logger = logging.getLogger(__name__)

# Per-test timeout in seconds
_UNIT_TIMEOUT = 30
_INTEGRATION_TIMEOUT = 60

# Regex patterns to parse pytest output
_PYTEST_PASS = re.compile(r"(\d+) passed")
_PYTEST_FAIL = re.compile(r"(\d+) failed")
_PYTEST_ERROR = re.compile(r"(\d+) error")
_PYTEST_SKIP = re.compile(r"(\d+) skipped")
_PYTEST_ITEM = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED)\s+(.+?)(?:\s+-\s+(.+))?$", re.MULTILINE)

# Regex patterns to parse jest/vitest output
_JEST_PASS = re.compile(r"Tests:\s+.*?(\d+) passed")
_JEST_FAIL = re.compile(r"Tests:\s+.*?(\d+) failed")
_JEST_ITEM = re.compile(r"^\s+([✓✗×●○])\s+(.+?)(?:\s+\((\d+)\s*ms\))?$", re.MULTILINE)


async def run_unit_tests(
    cases: list[TestCase],
    framework: FrameworkType,
    timeout: int = _UNIT_TIMEOUT,
) -> list[TestResult]:
    """
    Write generated test cases to temp files and execute them with the
    appropriate test runner. Returns one TestResult per TestCase.
    """
    if not cases:
        return []

    results: list[TestResult] = []

    if framework == FrameworkType.PYTEST:
        results = await _run_pytest(cases, timeout)
    elif framework in (FrameworkType.JEST, FrameworkType.VITEST):
        results = await _run_jest(cases, framework, timeout)
    else:
        # Unknown framework — mark all as skipped
        for case in cases:
            results.append(
                TestResult(
                    test_id=case.id,
                    test_name=case.name,
                    status=TestStatus.SKIP,
                    stderr=f"Unknown framework: {framework}",
                )
            )

    return results


# ---------------------------------------------------------------------------
# Pytest runner
# ---------------------------------------------------------------------------


async def _run_pytest(cases: list[TestCase], timeout: int) -> list[TestResult]:
    results: list[TestResult] = []

    with tempfile.TemporaryDirectory(prefix="runowl_test_") as tmpdir:
        tmp = Path(tmpdir)

        # Write all test files
        test_files: list[tuple[TestCase, Path]] = []
        for case in cases:
            fname = f"test_{case.id}.py"
            fpath = tmp / fname
            fpath.write_text(case.code, encoding="utf-8")
            test_files.append((case, fpath))

        # Run pytest across all temp files
        cmd = [
            "python", "-m", "pytest",
            "--tb=short",
            "--no-header",
            "-q",
            str(tmp),
        ]

        try:
            import time
            start = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
            )
            try:
                raw_out, raw_err = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                elapsed_ms = (time.monotonic() - start) * 1000
                timed_out = False
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                elapsed_ms = timeout * 1000
                timed_out = True
                raw_out, raw_err = b"", b"Timed out"

            stdout = raw_out.decode("utf-8", errors="replace")
            stderr = raw_err.decode("utf-8", errors="replace")

            # Map each case to a result
            for case, fpath in test_files:
                status = _parse_pytest_status(stdout, fpath.name, timed_out)
                results.append(
                    TestResult(
                        test_id=case.id,
                        test_name=case.name or fpath.name,
                        status=status,
                        duration_ms=elapsed_ms / max(len(cases), 1),
                        stdout=stdout,
                        stderr=stderr,
                        error_message=_extract_pytest_error(stdout, fpath.name),
                    )
                )

        except FileNotFoundError:
            for case, _ in test_files:
                results.append(
                    TestResult(
                        test_id=case.id,
                        test_name=case.name,
                        status=TestStatus.ERROR,
                        stderr="pytest not found — install it with: uv add pytest",
                    )
                )

    return results


def _parse_pytest_status(stdout: str, filename: str, timed_out: bool) -> TestStatus:
    if timed_out:
        return TestStatus.TIMEOUT
    # Look for the file name in the output
    if f"PASSED {filename}" in stdout or f"passed" in stdout and "failed" not in stdout:
        return TestStatus.PASS
    if f"FAILED {filename}" in stdout or "failed" in stdout:
        return TestStatus.FAIL
    if "error" in stdout.lower():
        return TestStatus.ERROR
    return TestStatus.SKIP


def _extract_pytest_error(stdout: str, filename: str) -> str:
    lines = stdout.splitlines()
    capturing = False
    error_lines: list[str] = []
    for line in lines:
        if filename in line and "FAILED" in line:
            capturing = True
        if capturing:
            error_lines.append(line)
            if len(error_lines) > 20:
                break
    return "\n".join(error_lines)


# ---------------------------------------------------------------------------
# Jest / Vitest runner
# ---------------------------------------------------------------------------


async def _run_jest(
    cases: list[TestCase], framework: FrameworkType, timeout: int
) -> list[TestResult]:
    results: list[TestResult] = []

    runner_cmd = "vitest" if framework == FrameworkType.VITEST else "jest"

    with tempfile.TemporaryDirectory(prefix="runowl_test_") as tmpdir:
        tmp = Path(tmpdir)

        test_files: list[tuple[TestCase, Path]] = []
        for case in cases:
            ext = "ts" if "import" in case.code or "describe" in case.code else "js"
            fname = f"{case.id}.test.{ext}"
            fpath = tmp / fname
            fpath.write_text(case.code, encoding="utf-8")
            test_files.append((case, fpath))

        cmd = [runner_cmd, "--no-coverage", str(tmp)]

        try:
            import time
            start = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
            )
            try:
                raw_out, raw_err = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                elapsed_ms = (time.monotonic() - start) * 1000
                timed_out = False
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                elapsed_ms = timeout * 1000
                timed_out = True
                raw_out, raw_err = b"", b"Timed out"

            stdout = raw_out.decode("utf-8", errors="replace")
            stderr = raw_err.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            for case, fpath in test_files:
                if timed_out:
                    status = TestStatus.TIMEOUT
                elif exit_code == 0:
                    status = TestStatus.PASS
                else:
                    status = TestStatus.FAIL

                results.append(
                    TestResult(
                        test_id=case.id,
                        test_name=case.name or fpath.name,
                        status=status,
                        duration_ms=elapsed_ms / max(len(cases), 1),
                        stdout=stdout,
                        stderr=stderr,
                    )
                )

        except FileNotFoundError:
            for case, _ in test_files:
                results.append(
                    TestResult(
                        test_id=case.id,
                        test_name=case.name,
                        status=TestStatus.ERROR,
                        stderr=f"{runner_cmd} not found",
                    )
                )

    return results
