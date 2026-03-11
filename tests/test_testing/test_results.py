"""Tests for testing.results — formatting and serialization."""

from testing.models import FrameworkType, TestResult, TestStatus, TestSuite
from testing.results import (
    _suite_from_dict,
    _suite_to_dict,
    format_results_json,
    format_results_markdown,
)


def _suite_with_results(statuses: list[TestStatus]) -> TestSuite:
    suite = TestSuite(pr_ref="owner/repo#1", framework=FrameworkType.PYTEST)
    suite.generation_success = True
    for i, status in enumerate(statuses):
        suite.results.append(
            TestResult(
                test_id=str(i),
                test_name=f"test_case_{i}",
                status=status,
                duration_ms=42.0,
            )
        )
    return suite


class TestFormatResultsMarkdown:
    def test_all_passed_header(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.PASS])
        md = format_results_markdown(suite)
        assert "All Passed" in md

    def test_failures_header(self) -> None:
        suite = _suite_with_results([TestStatus.FAIL])
        md = format_results_markdown(suite)
        assert "Failures Detected" in md

    def test_contains_results_table(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL])
        md = format_results_markdown(suite)
        assert "test_case_0" in md
        assert "test_case_1" in md

    def test_failure_details_section(self) -> None:
        suite = _suite_with_results([TestStatus.FAIL])
        suite.results[0].error_message = "AssertionError: expected True"
        md = format_results_markdown(suite)
        assert "AssertionError" in md

    def test_empty_suite_generation_failed(self) -> None:
        suite = TestSuite(pr_ref="owner/repo#1")
        suite.generation_success = False
        suite.generation_error = "No tests generated"
        md = format_results_markdown(suite)
        assert "No tests generated" in md


class TestFormatResultsJson:
    def test_structure(self) -> None:
        suite = _suite_with_results([TestStatus.PASS])
        data = format_results_json(suite)
        assert data["suite_id"] == suite.id
        assert data["pr_ref"] == "owner/repo#1"
        assert data["framework"] == "pytest"
        assert len(data["results"]) == 1
        assert data["summary"]["total"] == 1

    def test_result_fields(self) -> None:
        suite = _suite_with_results([TestStatus.FAIL])
        suite.results[0].video_path = "/path/to/video.webm"
        data = format_results_json(suite)
        result = data["results"][0]
        assert result["status"] == "fail"
        assert result["video_path"] == "/path/to/video.webm"


class TestSerialization:
    def test_round_trip(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL])
        d = _suite_to_dict(suite)
        restored = _suite_from_dict(d)
        assert restored.id == suite.id
        assert restored.pr_ref == suite.pr_ref
        assert len(restored.results) == 2
        assert restored.results[0].status == TestStatus.PASS
        assert restored.results[1].status == TestStatus.FAIL
