"""Executor — dispatches generated tests to the correct runner.

Unit / integration tests  →  sandbox_runner (pytest / jest / vitest subprocess)
E2E / browser tests       →  docker_runner  (Playwright in Docker container)
"""

from __future__ import annotations

import logging

from testing.docker_runner import detect_preview_url, run_e2e_tests
from testing.models import TestCase, TestSuite, TestType
from testing.recorder import attach_recordings
from testing.results import save_suite
from testing.sandbox_runner import run_unit_tests

logger = logging.getLogger(__name__)


async def execute_suite(
    suite: TestSuite,
    pr_body: str = "",
    pr_comments: list[str] | None = None,
) -> TestSuite:
    """
    Run all test cases in a suite, dispatching by type.
    Attaches results to the suite in-place and persists to disk.
    """
    unit_cases: list[TestCase] = []
    e2e_cases: list[TestCase] = []

    for case in suite.cases:
        if case.type == TestType.E2E:
            e2e_cases.append(case)
        else:
            unit_cases.append(case)

    # --- Unit / integration ---
    if unit_cases:
        logger.info(
            "Running %d unit/integration tests (framework: %s)", len(unit_cases), suite.framework
        )
        unit_results = await run_unit_tests(unit_cases, suite.framework)
        suite.results.extend(unit_results)

    # --- E2E / browser ---
    if e2e_cases:
        preview_url = await detect_preview_url(pr_body, pr_comments)
        logger.info(
            "Running %d E2E tests (preview URL: %s)",
            len(e2e_cases),
            preview_url or "none",
        )
        e2e_results = await run_e2e_tests(e2e_cases, preview_url=preview_url)
        suite.results.extend(e2e_results)
        # Attach video / replay artefacts
        attach_recordings(suite, str(suite.id))

    # Persist
    save_suite(suite)

    logger.info(
        "Suite %s complete — %d/%d passed",
        suite.id,
        suite.passed,
        suite.total,
    )
    return suite
