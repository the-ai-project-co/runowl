"""AI evals for overall review pipeline quality.

Evaluates the complete review flow (with mocked Gemini) against golden PR
scenarios and quality rubrics:
- Golden PR scenarios with specific raw outputs
- Output quality rubric checks (markdown + JSON)
- Completeness: no findings dropped in pipeline
- Consistency: deterministic results
- Error handling: graceful degradation on failures
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from github.client import GitHubClient
from github.models import PRCommit, PRFile, PRMetadata, PRRef
from reasoning.engine import ReasoningEngine
from reasoning.models import ConversationMessage, ReasoningTrace, RLMResult
from review.agent import ReviewAgent
from review.formatter import format_review_json, format_review_markdown
from review.models import (
    Citation,
    Finding,
    FindingType,
    ReviewResult,
    Severity,
)
from review.parser import parse_findings
from review.severity import ensure_fix_for_blocking, reclassify_findings

# ── Test constants ───────────────────────────────────────────────────────────

PR_REF = PRRef(owner="acme", repo="widget", number=42)


def _make_metadata(files: list[PRFile] | None = None) -> PRMetadata:
    """Build a minimal PRMetadata for testing."""
    if files is None:
        files = [
            PRFile(
                filename="src/auth.py",
                status="modified",
                additions=10,
                deletions=2,
                changes=12,
                patch="@@ -10,5 +10,13 @@\n+line\n",
            ),
            PRFile(
                filename="src/db.py",
                status="modified",
                additions=5,
                deletions=1,
                changes=6,
                patch="@@ -80,3 +80,8 @@\n+line\n",
            ),
        ]
    return PRMetadata(
        number=42,
        title="Fix auth and DB issues",
        body="This PR fixes critical auth and database issues.",
        author="alice",
        base_branch="main",
        head_branch="fix/auth-db",
        head_sha="abc123def456",
        base_sha="000111222333",
        state="open",
        commits=[PRCommit(sha="abc123", message="fix auth", author="alice")],
        files=files,
        additions=15,
        deletions=3,
        changed_files=2,
    )


def _make_rlm_result(output: str, success: bool = True, error: str | None = None) -> RLMResult:
    return RLMResult(
        output=output,
        trace=ReasoningTrace(),
        conversation=[],
        success=success,
        error=error,
    )


def _mock_gh(metadata: PRMetadata | None = None) -> MagicMock:
    gh = MagicMock(spec=GitHubClient)
    gh.get_pr_metadata = AsyncMock(return_value=metadata or _make_metadata())
    return gh


def _mock_engine(output: str, success: bool = True, error: str | None = None) -> MagicMock:
    engine = MagicMock()
    engine._step_cb = None
    engine.review_pr = AsyncMock(
        return_value=_make_rlm_result(output, success, error)
    )
    return engine


# ── Helpers for full pipeline execution ──────────────────────────────────────


async def _run_review(raw_output: str, files: list[PRFile] | None = None) -> ReviewResult:
    """Run the full ReviewAgent pipeline with mocked dependencies."""
    metadata = _make_metadata(files)
    gh = _mock_gh(metadata)
    engine = _mock_engine(raw_output)
    agent = ReviewAgent(gh, engine)
    return await agent.review(PR_REF)


def _run_parse_pipeline(raw_output: str) -> list[Finding]:
    """Run parse -> reclassify -> ensure_fix pipeline on raw output."""
    findings = parse_findings(raw_output)
    reclassify_findings(findings)
    ensure_fix_for_blocking(findings)
    return findings


# ═════════════════════════════════════════════════════════════════════════════
# 1. Golden PR Scenarios
# ═════════════════════════════════════════════════════════════════════════════


class TestGoldenScenarioA:
    """Security-Heavy PR: SQL injection P0, XSS P1, CORS P2."""

    RAW = (
        "[P0] security: SQL injection in login endpoint\n"
        "File: src/auth.py lines 10-15\n"
        "Description: User input is directly concatenated into SQL query.\n"
        "Fix: Use parameterized queries.\n"
        "\n"
        "[P1] security: XSS vulnerability in profile page\n"
        "File: src/auth.py:12-13\n"
        "Description: User-supplied HTML is rendered without sanitization, "
        "enabling cross-site scripting attacks.\n"
        "Fix: Sanitize all user input before rendering.\n"
        "\n"
        "[P2] security: CORS misconfiguration\n"
        "File: src/db.py:80-82\n"
        "Description: CORS allows all origins which may expose the API.\n"
    )

    async def test_parses_three_findings(self) -> None:
        result = await _run_review(self.RAW)
        assert result.success
        assert len(result.findings) == 3

    async def test_severity_after_reclassification(self) -> None:
        result = await _run_review(self.RAW)
        severities = [f.severity for f in result.findings]
        assert Severity.P0 in severities
        assert Severity.P1 in severities
        assert Severity.P2 in severities

    async def test_sql_injection_is_p0(self) -> None:
        result = await _run_review(self.RAW)
        sql_finding = [f for f in result.findings if "SQL injection" in f.title]
        assert len(sql_finding) == 1
        assert sql_finding[0].severity == Severity.P0

    async def test_all_have_citations(self) -> None:
        result = await _run_review(self.RAW)
        for finding in result.findings:
            assert finding.citation is not None
            assert finding.citation.file != "unknown"

    async def test_blocking_findings_have_fixes(self) -> None:
        result = await _run_review(self.RAW)
        for finding in result.findings:
            if finding.blocks_merge:
                assert finding.fix is not None
                assert len(finding.fix) > 0

    async def test_markdown_contains_all_findings(self) -> None:
        result = await _run_review(self.RAW)
        md = format_review_markdown(result)
        assert "SQL injection" in md
        assert "XSS" in md or "cross-site scripting" in md.lower()
        assert "CORS" in md

    async def test_json_has_correct_blocking_count(self) -> None:
        result = await _run_review(self.RAW)
        output = format_review_json(result)
        assert output["summary"]["blocking"] == 2  # P0 + P1


class TestGoldenScenarioB:
    """Bug-Only PR: null dereference P0, unhandled exception P1."""

    RAW = (
        "[P0] bug: Null pointer dereference in user handler\n"
        "File: src/auth.py:10-12\n"
        "Description: The user object is accessed without null check, "
        "causing null pointer dereference in production.\n"
        "Fix: Add null check before accessing user.id.\n"
        "\n"
        "[P1] bug: Unhandled exception in DB query\n"
        "File: src/db.py:80-85\n"
        "Description: Database query may throw an unhandled exception "
        "when connection is lost.\n"
        "Fix: Wrap in try-except and log the error.\n"
    )

    async def test_parses_two_findings(self) -> None:
        result = await _run_review(self.RAW)
        assert len(result.findings) == 2

    async def test_null_deref_promoted_to_p0(self) -> None:
        result = await _run_review(self.RAW)
        null_finding = [f for f in result.findings if "Null pointer" in f.title]
        assert len(null_finding) == 1
        assert null_finding[0].severity == Severity.P0

    async def test_unhandled_exception_at_least_p1(self) -> None:
        result = await _run_review(self.RAW)
        exc_finding = [f for f in result.findings if "Unhandled exception" in f.title]
        assert len(exc_finding) == 1
        assert exc_finding[0].severity in (Severity.P0, Severity.P1)

    async def test_both_have_fixes(self) -> None:
        result = await _run_review(self.RAW)
        for finding in result.findings:
            assert finding.fix is not None

    async def test_both_block_merge(self) -> None:
        result = await _run_review(self.RAW)
        assert all(f.blocks_merge for f in result.findings)


class TestGoldenScenarioC:
    """Clean PR: no issues found."""

    RAW = "This PR looks good. No issues found."

    async def test_zero_findings(self) -> None:
        result = await _run_review(self.RAW)
        assert result.success
        assert len(result.findings) == 0

    async def test_markdown_says_no_issues(self) -> None:
        result = await _run_review(self.RAW)
        md = format_review_markdown(result)
        assert "No issues found" in md

    async def test_json_summary_zeroes(self) -> None:
        result = await _run_review(self.RAW)
        output = format_review_json(result)
        assert output["summary"]["total"] == 0
        assert output["summary"]["blocking"] == 0


class TestGoldenScenarioD:
    """Mixed Severity PR: one finding at each severity level."""

    RAW = (
        "[P0] security: SQL injection in login endpoint\n"
        "File: src/auth.py lines 10-13\n"
        "Description: Direct SQL concatenation allows SQL injection.\n"
        "Fix: Use parameterized queries.\n"
        "\n"
        "[P1] bug: Memory leak in connection pool\n"
        "File: src/db.py:80-85\n"
        "Description: Connections are not returned to pool, causing a memory leak.\n"
        "Fix: Use context manager for connections.\n"
        "\n"
        "[P2] investigation: Unusual error handling pattern\n"
        "File: src/auth.py:14-16\n"
        "Description: Errors are silently caught and ignored, which is a code smell.\n"
        "\n"
        "[P3] informational: Naming convention inconsistency\n"
        "File: src/db.py:82\n"
        "Description: Variable naming uses camelCase instead of snake_case.\n"
    )

    async def test_four_findings(self) -> None:
        result = await _run_review(self.RAW)
        assert len(result.findings) == 4

    async def test_sorted_by_severity(self) -> None:
        result = await _run_review(self.RAW)
        severities = [f.severity for f in result.findings]
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert severities == sorted(severities, key=lambda s: order[s])

    async def test_correct_blocking_count(self) -> None:
        result = await _run_review(self.RAW)
        assert len(result.blocking) == 2  # P0 + P1

    async def test_by_severity_breakdown(self) -> None:
        result = await _run_review(self.RAW)
        output = format_review_json(result)
        by_sev = output["summary"]["by_severity"]
        assert by_sev["P0"] == 1
        assert by_sev["P1"] == 1
        assert by_sev["P2"] == 1
        assert by_sev["P3"] == 1

    async def test_non_blocking_no_fix_required(self) -> None:
        """P2 and P3 findings don't need forced fix placeholders."""
        result = await _run_review(self.RAW)
        p3_findings = result.by_severity(Severity.P3)
        for f in p3_findings:
            # P3 should not have the forced placeholder fix
            assert f.fix is None or "Fix required" not in f.fix


class TestGoldenScenarioE:
    """Under-Classified PR: security findings at wrong severity, should be promoted."""

    RAW = (
        "[P2] security: SQL injection in search endpoint\n"
        "File: src/auth.py:10-12\n"
        "Description: User input directly used in SQL query, enabling SQL injection.\n"
        "\n"
        "[P3] security: XSS in user profile\n"
        "File: src/auth.py:14-16\n"
        "Description: Cross-site scripting via unsanitized user input in profile page.\n"
    )

    async def test_sql_injection_promoted_to_p0(self) -> None:
        result = await _run_review(self.RAW)
        sql_finding = [f for f in result.findings if "SQL injection" in f.title]
        assert len(sql_finding) == 1
        assert sql_finding[0].severity == Severity.P0

    async def test_xss_promoted_to_p1(self) -> None:
        result = await _run_review(self.RAW)
        xss_finding = [f for f in result.findings if "XSS" in f.title]
        assert len(xss_finding) == 1
        assert xss_finding[0].severity == Severity.P1

    async def test_promoted_findings_now_block_merge(self) -> None:
        result = await _run_review(self.RAW)
        assert all(f.blocks_merge for f in result.findings)

    async def test_promoted_findings_get_fix_placeholder(self) -> None:
        result = await _run_review(self.RAW)
        for finding in result.findings:
            assert finding.fix is not None
            assert len(finding.fix) > 0


# ═════════════════════════════════════════════════════════════════════════════
# 2. Output Quality Rubric Eval
# ═════════════════════════════════════════════════════════════════════════════


class TestOutputQualityRubric:
    """Evaluate structural quality of markdown and JSON output."""

    SCENARIO_RAW = (
        "[P0] security: SQL injection in login\n"
        "File: src/auth.py:10-15\n"
        "Description: SQL injection vulnerability.\n"
        "Fix: Use parameterized queries.\n"
        "\n"
        "[P1] bug: Null dereference\n"
        "File: src/auth.py:12\n"
        "Description: None dereference causes crash.\n"
        "Fix: Add null check.\n"
        "\n"
        "[P3] informational: Unused import\n"
        "File: src/db.py:80\n"
        "Description: The os module is imported but not used.\n"
    )

    async def test_markdown_contains_runowl_header(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        md = format_review_markdown(result)
        assert "RunOwl" in md

    async def test_markdown_has_severity_badges(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        md = format_review_markdown(result)
        assert "P0" in md
        # Note: the P1 "None dereference" finding gets promoted to P0 by reclassifier
        # (matches P0 signal "none dereference"), so P1 may not appear
        assert "P3" in md

    async def test_markdown_has_finding_titles(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        md = format_review_markdown(result)
        assert "SQL injection" in md
        assert "Null dereference" in md or "None dereference" in md
        assert "Unused import" in md

    async def test_markdown_has_file_references(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        md = format_review_markdown(result)
        assert "src/auth.py" in md
        assert "src/db.py" in md

    async def test_markdown_blocking_findings_have_fix_section(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        md = format_review_markdown(result)
        # P0 and P1 findings should have Fix section in markdown
        assert "**Fix:**" in md

    async def test_json_has_all_required_fields(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        output = format_review_json(result)
        assert "success" in output
        assert "findings" in output
        assert "summary" in output
        summary = output["summary"]
        assert "total" in summary
        assert "blocking" in summary
        assert "by_severity" in summary
        assert "by_type" in summary

    async def test_json_is_serializable(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        output = format_review_json(result)
        # Must not throw
        serialized = json.dumps(output)
        assert isinstance(serialized, str)
        # Round-trip
        deserialized = json.loads(serialized)
        assert deserialized["success"] == output["success"]

    async def test_json_findings_have_all_fields(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        output = format_review_json(result)
        for finding in output["findings"]:
            assert "severity" in finding
            assert "type" in finding
            assert "title" in finding
            assert "description" in finding
            assert "citation" in finding
            assert "file" in finding["citation"]
            assert "line_start" in finding["citation"]
            assert "line_end" in finding["citation"]
            assert "fix" in finding
            assert "blocks_merge" in finding

    async def test_json_severity_values_valid(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        output = format_review_json(result)
        valid_severities = {"P0", "P1", "P2", "P3"}
        for finding in output["findings"]:
            assert finding["severity"] in valid_severities

    async def test_json_type_values_valid(self) -> None:
        result = await _run_review(self.SCENARIO_RAW)
        output = format_review_json(result)
        valid_types = {"bug", "security", "investigation", "informational"}
        for finding in output["findings"]:
            assert finding["type"] in valid_types

    async def test_markdown_failure_result(self) -> None:
        result = ReviewResult(success=False, error="Gemini quota exceeded")
        md = format_review_markdown(result)
        assert "RunOwl" in md
        assert "Failed" in md
        assert "Gemini quota exceeded" in md

    async def test_json_failure_result(self) -> None:
        result = ReviewResult(success=False, error="Gemini quota exceeded")
        output = format_review_json(result)
        assert output["success"] is False
        assert output["error"] == "Gemini quota exceeded"
        assert output["summary"]["total"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# 3. Completeness Eval
# ═════════════════════════════════════════════════════════════════════════════


class TestCompleteness:
    """Verify no findings are dropped during the pipeline."""

    async def test_ten_findings_all_preserved(self) -> None:
        """Parse 10 findings, all must survive the pipeline."""
        raw = ""
        for i in range(10):
            severity = f"P{i % 4}"
            ftype = ["bug", "security", "investigation", "informational"][i % 4]
            raw += (
                f"[{severity}] {ftype}: Finding number {i}\n"
                f"File: src/auth.py:{10 + i}\n"
                f"Description: Description for finding {i}.\n"
                f"Fix: Fix for finding {i}.\n"
                "\n"
            )
        result = await _run_review(raw)
        assert len(result.findings) == 10

    async def test_findings_with_very_long_titles(self) -> None:
        """Long titles should not cause findings to be dropped."""
        long_title = "A" * 200
        raw = (
            f"[P2] bug: {long_title}\n"
            "File: src/auth.py:10\n"
            "Description: A long-titled finding.\n"
        )
        findings = _run_parse_pipeline(raw)
        assert len(findings) == 1
        assert long_title in findings[0].title

    async def test_findings_with_special_chars_in_title(self) -> None:
        """Special characters in titles should not break parsing."""
        raw = (
            "[P2] bug: Fix for <script>alert('xss')</script> & other \"issues\"\n"
            "File: src/auth.py:10\n"
            "Description: HTML special chars in title.\n"
        )
        findings = _run_parse_pipeline(raw)
        assert len(findings) == 1

    async def test_findings_with_unicode_title(self) -> None:
        """Unicode in titles should be preserved."""
        raw = (
            "[P2] bug: Fix for \u00fcber-bug in M\u00fcnchen module\n"
            "File: src/auth.py:10\n"
            "Description: Unicode in the title.\n"
        )
        findings = _run_parse_pipeline(raw)
        assert len(findings) == 1
        assert "\u00fcber" in findings[0].title

    async def test_all_findings_in_markdown_output(self) -> None:
        """Every finding title must appear in the markdown output."""
        raw = ""
        titles = []
        for i in range(5):
            title = f"Unique finding title {i} XYZ{i}"
            titles.append(title)
            raw += (
                f"[P{i % 4}] bug: {title}\n"
                f"File: src/auth.py:{10 + i}\n"
                f"Description: Desc {i}.\n"
                "\n"
            )
        result = await _run_review(raw)
        md = format_review_markdown(result)
        for title in titles:
            assert title in md

    async def test_all_findings_in_json_output(self) -> None:
        """Every finding must appear in JSON output."""
        raw = ""
        titles = []
        for i in range(5):
            title = f"JSON finding {i}"
            titles.append(title)
            raw += (
                f"[P{i % 4}] security: {title}\n"
                f"File: src/auth.py:{10 + i}\n"
                f"Description: Desc {i}.\n"
                "\n"
            )
        result = await _run_review(raw)
        output = format_review_json(result)
        json_titles = {f["title"] for f in output["findings"]}
        for title in titles:
            assert title in json_titles


# ═════════════════════════════════════════════════════════════════════════════
# 4. Consistency Eval
# ═════════════════════════════════════════════════════════════════════════════


class TestConsistency:
    """Same raw output parsed twice must produce identical results."""

    RAW = (
        "[P0] security: SQL injection in login\n"
        "File: src/auth.py:10-15\n"
        "Description: SQL injection via string concatenation.\n"
        "Fix: Use parameterized queries.\n"
        "\n"
        "[P1] bug: Null dereference\n"
        "File: src/db.py:80\n"
        "Description: None dereference in handler.\n"
        "Fix: Add null check.\n"
        "\n"
        "[P3] informational: Unused import\n"
        "File: src/db.py:82\n"
        "Description: os module unused.\n"
    )

    def test_parse_deterministic(self) -> None:
        findings_a = _run_parse_pipeline(self.RAW)
        findings_b = _run_parse_pipeline(self.RAW)
        assert len(findings_a) == len(findings_b)
        for a, b in zip(findings_a, findings_b):
            assert a.severity == b.severity
            assert a.type == b.type
            assert a.title == b.title
            assert a.description == b.description
            assert a.citation.file == b.citation.file
            assert a.citation.line_start == b.citation.line_start
            assert a.citation.line_end == b.citation.line_end

    def test_format_deterministic_markdown(self) -> None:
        findings_a = _run_parse_pipeline(self.RAW)
        findings_b = _run_parse_pipeline(self.RAW)
        result_a = ReviewResult(findings=findings_a, raw_output=self.RAW, success=True)
        result_b = ReviewResult(findings=findings_b, raw_output=self.RAW, success=True)
        assert format_review_markdown(result_a) == format_review_markdown(result_b)

    def test_format_deterministic_json(self) -> None:
        findings_a = _run_parse_pipeline(self.RAW)
        findings_b = _run_parse_pipeline(self.RAW)
        result_a = ReviewResult(findings=findings_a, raw_output=self.RAW, success=True)
        result_b = ReviewResult(findings=findings_b, raw_output=self.RAW, success=True)
        json_a = json.dumps(format_review_json(result_a), sort_keys=True)
        json_b = json.dumps(format_review_json(result_b), sort_keys=True)
        assert json_a == json_b

    async def test_full_pipeline_deterministic(self) -> None:
        """Two runs through the full agent pipeline produce the same findings."""
        result_a = await _run_review(self.RAW)
        result_b = await _run_review(self.RAW)
        assert len(result_a.findings) == len(result_b.findings)
        for a, b in zip(result_a.findings, result_b.findings):
            assert a.severity == b.severity
            assert a.title == b.title


# ═════════════════════════════════════════════════════════════════════════════
# 5. Error Handling Eval
# ═════════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Verify graceful degradation on various failure modes."""

    async def test_engine_returns_failure(self) -> None:
        """Engine success=False -> ReviewResult has error, no findings."""
        gh = _mock_gh()
        engine = _mock_engine("", success=False, error="Gemini quota exceeded")
        agent = ReviewAgent(gh, engine)
        result = await agent.review(PR_REF)
        assert not result.success
        assert result.error is not None
        assert "Gemini quota exceeded" in result.error
        assert len(result.findings) == 0

    async def test_engine_returns_empty_output(self) -> None:
        """Engine returns empty string -> 0 findings, success True from engine
        but ReviewResult reflects no output."""
        gh = _mock_gh()
        engine = _mock_engine("", success=False, error="Reasoning engine returned no output")
        agent = ReviewAgent(gh, engine)
        result = await agent.review(PR_REF)
        assert not result.success
        assert len(result.findings) == 0

    async def test_engine_returns_malformed_output(self) -> None:
        """Engine returns text with no [PX] headers -> 0 findings, success True."""
        raw = "Here is some random text that does not contain any structured findings."
        result = await _run_review(raw)
        assert result.success
        assert len(result.findings) == 0

    async def test_github_api_failure(self) -> None:
        """GitHub API raises exception -> ReviewResult has error."""
        gh = MagicMock(spec=GitHubClient)
        gh.get_pr_metadata = AsyncMock(side_effect=Exception("GitHub API down"))
        engine = _mock_engine("")
        agent = ReviewAgent(gh, engine)
        result = await agent.review(PR_REF)
        assert not result.success
        assert result.error is not None
        assert "GitHub API down" in result.error

    async def test_github_timeout(self) -> None:
        """GitHub times out -> ReviewResult has error."""
        import httpx

        gh = MagicMock(spec=GitHubClient)
        gh.get_pr_metadata = AsyncMock(side_effect=httpx.ReadTimeout("Connection timed out"))
        engine = _mock_engine("")
        agent = ReviewAgent(gh, engine)
        result = await agent.review(PR_REF)
        assert not result.success
        assert result.error is not None

    async def test_engine_exception_caught(self) -> None:
        """Engine.review_pr raises exception -> ReviewResult has error."""
        gh = _mock_gh()
        engine = MagicMock()
        engine._step_cb = None
        engine.review_pr = AsyncMock(side_effect=RuntimeError("Model crashed"))
        agent = ReviewAgent(gh, engine)
        result = await agent.review(PR_REF)
        assert not result.success
        assert "Model crashed" in (result.error or "")

    async def test_partial_malformed_output(self) -> None:
        """Output with some valid and some malformed findings -> only valid parsed."""
        raw = (
            "[P0] security: Real finding\n"
            "File: src/auth.py:10\n"
            "Description: A real security issue.\n"
            "Fix: Fix it.\n"
            "\n"
            "This is not a finding header at all.\n"
            "Just random text between findings.\n"
            "\n"
            "[INVALID] not a severity: broken header\n"
            "File: src/bad.py:1\n"
            "\n"
            "[P1] bug: Another real finding\n"
            "File: src/db.py:80\n"
            "Description: Unhandled exception in query.\n"
            "Fix: Add error handling.\n"
        )
        result = await _run_review(raw)
        assert result.success
        assert len(result.findings) == 2

    async def test_empty_findings_json_structure(self) -> None:
        """Empty findings produce valid JSON structure."""
        result = ReviewResult(findings=[], success=True)
        output = format_review_json(result)
        assert output["success"] is True
        assert output["summary"]["total"] == 0
        assert output["summary"]["blocking"] == 0
        assert output["findings"] == []
        # Must serialize cleanly
        assert json.dumps(output)

    async def test_error_result_json_structure(self) -> None:
        """Error result produces valid JSON structure."""
        result = ReviewResult(success=False, error="Something went wrong")
        output = format_review_json(result)
        assert output["success"] is False
        assert output["error"] == "Something went wrong"
        assert output["summary"]["total"] == 0
        assert json.dumps(output)

    async def test_findings_without_file_line_get_fallback_citation(self) -> None:
        """Findings where parser can't extract citation get fallback citation."""
        raw = (
            "[P2] bug: Some issue without clear file reference\n"
            "Description: Something is wrong but no file line given.\n"
        )
        findings = parse_findings(raw)
        assert len(findings) == 1
        # Parser falls back to Citation(file="unknown", line_start=0, line_end=0)
        # or whatever file ref it can find
        assert findings[0].citation is not None
