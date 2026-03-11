"""Data models for the RunOwl Testing Engine (Phase 2a)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FrameworkType(StrEnum):
    PYTEST = "pytest"
    JEST = "jest"
    VITEST = "vitest"
    PLAYWRIGHT = "playwright"
    UNKNOWN = "unknown"


class TestType(StrEnum):
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"


class TestStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"
    TIMEOUT = "timeout"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Generated test case (before execution)
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    """A single generated test case."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    type: TestType = TestType.UNIT
    framework: FrameworkType = FrameworkType.PYTEST
    # The generated test source code
    code: str = ""
    # Which source file / function this test covers
    source_file: str = ""
    source_function: str = ""
    # Line range in the PR diff this test targets
    diff_line_start: int = 0
    diff_line_end: int = 0
    confidence: Confidence = Confidence.MEDIUM
    # Natural language description of what the test checks
    description: str = ""


# ---------------------------------------------------------------------------
# Execution result for a single test case
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    """Execution result for a single TestCase."""

    test_id: str = ""
    test_name: str = ""
    status: TestStatus = TestStatus.SKIP
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    error_message: str = ""
    # Path to recorded video clip (if E2E)
    video_path: str | None = None
    # Path to session replay JSON (if E2E)
    replay_path: str | None = None
    # Screenshot paths (on failure)
    screenshots: list[str] = field(default_factory=list)
    executed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status in (TestStatus.FAIL, TestStatus.ERROR, TestStatus.TIMEOUT)


# ---------------------------------------------------------------------------
# Test suite — collection of cases for a single PR
# ---------------------------------------------------------------------------


@dataclass
class TestSuite:
    """All generated tests and their results for a PR."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    pr_ref: str = ""  # "owner/repo#123"
    cases: list[TestCase] = field(default_factory=list)
    results: list[TestResult] = field(default_factory=list)
    framework: FrameworkType = FrameworkType.UNKNOWN
    created_at: datetime = field(default_factory=datetime.utcnow)
    # Raw output from generation agent
    generation_raw: str = ""
    generation_success: bool = False
    generation_error: str | None = None

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAIL)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.ERROR)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.SKIP)

    @property
    def timed_out(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.TIMEOUT)

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errors == 0

    @property
    def has_failures(self) -> bool:
        return self.failed > 0 or self.errors > 0

    def result_for(self, test_id: str) -> TestResult | None:
        return next((r for r in self.results if r.test_id == test_id), None)

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pr_ref": self.pr_ref,
            "framework": self.framework,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "timed_out": self.timed_out,
            "all_passed": self.all_passed,
        }
