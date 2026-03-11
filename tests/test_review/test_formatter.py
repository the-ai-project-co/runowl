"""Tests for review output formatters."""

from review.formatter import format_review_json, format_review_markdown
from review.models import Citation, Finding, FindingType, ReviewResult, Severity


def _make_result(findings=None, success=True, error=None) -> ReviewResult:
    return ReviewResult(
        findings=findings or [],
        raw_output="",
        pr_summary="PR #1: Test",
        success=success,
        error=error,
    )


def _make_finding(severity=Severity.P1, ftype=FindingType.BUG) -> Finding:
    return Finding(
        severity=severity,
        type=ftype,
        title="Test finding",
        description="Something is wrong.",
        citation=Citation(file="src/a.py", line_start=10, line_end=12),
        fix="Fix it like this.",
    )


class TestFormatMarkdown:
    def test_contains_runowl_header(self) -> None:
        result = _make_result()
        md = format_review_markdown(result)
        assert "RunOwl Code Review" in md

    def test_no_findings_shows_clean(self) -> None:
        md = format_review_markdown(_make_result())
        assert "No issues found" in md

    def test_finding_title_present(self) -> None:
        finding = _make_finding()
        md = format_review_markdown(_make_result([finding]))
        assert "Test finding" in md

    def test_p0_badge_present(self) -> None:
        finding = _make_finding(severity=Severity.P0)
        md = format_review_markdown(_make_result([finding]))
        assert "P0" in md

    def test_fix_present_in_output(self) -> None:
        finding = _make_finding()
        md = format_review_markdown(_make_result([finding]))
        assert "Fix it like this." in md

    def test_citation_present(self) -> None:
        finding = _make_finding()
        md = format_review_markdown(_make_result([finding]))
        assert "src/a.py" in md

    def test_failure_result_shows_error(self) -> None:
        result = _make_result(success=False, error="API timeout")
        md = format_review_markdown(result)
        assert "Failed" in md
        assert "API timeout" in md

    def test_blocking_count_in_summary(self) -> None:
        findings = [_make_finding(Severity.P0), _make_finding(Severity.P1)]
        md = format_review_markdown(_make_result(findings))
        assert "2" in md


class TestFormatJson:
    def test_success_field(self) -> None:
        data = format_review_json(_make_result())
        assert data["success"] is True

    def test_total_findings_count(self) -> None:
        findings = [_make_finding(), _make_finding()]
        data = format_review_json(_make_result(findings))
        assert data["summary"]["total"] == 2

    def test_blocking_count(self) -> None:
        findings = [_make_finding(Severity.P0), _make_finding(Severity.P3)]
        data = format_review_json(_make_result(findings))
        assert data["summary"]["blocking"] == 1

    def test_finding_fields_present(self) -> None:
        finding = _make_finding()
        data = format_review_json(_make_result([finding]))
        f = data["findings"][0]
        assert f["severity"] == "P1"
        assert f["type"] == "bug"
        assert f["title"] == "Test finding"
        assert f["citation"]["file"] == "src/a.py"
        assert f["blocks_merge"] is True

    def test_empty_findings_list(self) -> None:
        data = format_review_json(_make_result())
        assert data["findings"] == []

    def test_severity_breakdown(self) -> None:
        findings = [_make_finding(Severity.P0), _make_finding(Severity.P2)]
        data = format_review_json(_make_result(findings))
        assert data["summary"]["by_severity"]["P0"] == 1
        assert data["summary"]["by_severity"]["P2"] == 1
