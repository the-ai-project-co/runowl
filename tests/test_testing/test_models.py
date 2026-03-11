"""Tests for testing.models."""

from testing.models import (
    Confidence,
    FrameworkType,
    TestCase,
    TestResult,
    TestStatus,
    TestSuite,
    TestType,
)


class TestTestSuiteAggregation:
    def _make_suite(self, statuses: list[TestStatus]) -> TestSuite:
        suite = TestSuite(pr_ref="owner/repo#1")
        for i, status in enumerate(statuses):
            suite.results.append(
                TestResult(test_id=str(i), test_name=f"test_{i}", status=status)
            )
        return suite

    def test_all_passed(self) -> None:
        suite = self._make_suite([TestStatus.PASS, TestStatus.PASS])
        assert suite.all_passed is True
        assert suite.has_failures is False

    def test_has_failures_on_fail(self) -> None:
        suite = self._make_suite([TestStatus.PASS, TestStatus.FAIL])
        assert suite.all_passed is False
        assert suite.has_failures is True

    def test_has_failures_on_error(self) -> None:
        suite = self._make_suite([TestStatus.ERROR])
        assert suite.has_failures is True

    def test_counts(self) -> None:
        suite = self._make_suite(
            [TestStatus.PASS, TestStatus.FAIL, TestStatus.ERROR, TestStatus.SKIP, TestStatus.TIMEOUT]
        )
        assert suite.total == 5
        assert suite.passed == 1
        assert suite.failed == 1
        assert suite.errors == 1
        assert suite.skipped == 1
        assert suite.timed_out == 1

    def test_empty_suite_not_all_passed(self) -> None:
        suite = TestSuite()
        assert suite.all_passed is False

    def test_to_summary_keys(self) -> None:
        suite = self._make_suite([TestStatus.PASS])
        summary = suite.to_summary()
        for key in ("id", "pr_ref", "framework", "total", "passed", "failed", "all_passed"):
            assert key in summary


class TestTestResult:
    def test_passed_property(self) -> None:
        r = TestResult(test_id="1", status=TestStatus.PASS)
        assert r.passed is True
        assert r.failed is False

    def test_failed_property_on_fail(self) -> None:
        r = TestResult(test_id="1", status=TestStatus.FAIL)
        assert r.failed is True

    def test_failed_property_on_timeout(self) -> None:
        r = TestResult(test_id="1", status=TestStatus.TIMEOUT)
        assert r.failed is True

    def test_failed_property_on_pass(self) -> None:
        r = TestResult(test_id="1", status=TestStatus.PASS)
        assert r.failed is False


class TestTestCase:
    def test_defaults(self) -> None:
        case = TestCase()
        assert case.framework == FrameworkType.PYTEST
        assert case.type == TestType.UNIT
        assert case.confidence == Confidence.MEDIUM
        assert case.id  # uuid generated
