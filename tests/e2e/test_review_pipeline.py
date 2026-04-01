"""End-to-end tests for the full RunOwl review pipeline.

Exercises the FULL review pipeline with mocked external services
(Gemini API at the SDK level, GitHub API via pytest-httpx) but real
internal code paths -- no internal mocking.

Pipeline under test:
  1. GitHubClient fetches PR metadata + files + diffs (HTTP mocked)
  2. Diff parser extracts hunks from patches
  3. ReviewAgent orchestrates: context -> ReasoningEngine -> parse -> reclassify -> validate
  4. Formatter outputs markdown and JSON
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from github.client import GitHubClient
from github.models import PRRef
from reasoning.engine import ReasoningEngine
from review.agent import ReviewAgent
from review.formatter import format_review_json, format_review_markdown
from review.models import FindingType, Severity

# ── Shared constants ──────────────────────────────────────────────────────────

PR_REF = PRRef(owner="acme", repo="webapp", number=42)
_GH = "https://api.github.com"

# ── Realistic PR payloads ─────────────────────────────────────────────────────

_PR_PAYLOAD = {
    "number": 42,
    "title": "Add user search endpoint",
    "body": "Implements GET /users/search with query parameter filtering.",
    "user": {"login": "alice"},
    "base": {"ref": "main", "sha": "base000"},
    "head": {"ref": "feat/user-search", "sha": "head999"},
    "state": "open",
    "additions": 85,
    "deletions": 3,
    "changed_files": 3,
}

_COMMITS_PAYLOAD = [
    {
        "sha": "head999",
        "commit": {
            "message": "feat: add user search endpoint",
            "author": {"name": "Alice"},
        },
    },
]

# Realistic patches with actual diff content for citation validation
_SEARCH_PY_PATCH = (
    "@@ -0,0 +1,25 @@\n"
    "+import sqlite3\n"
    "+from flask import Flask, request, jsonify\n"
    "+\n"
    "+app = Flask(__name__)\n"
    "+\n"
    "+@app.route('/users/search')\n"
    "+def search_users():\n"
    "+    query = request.args.get('q', '')\n"
    "+    conn = sqlite3.connect('users.db')\n"
    "+    cursor = conn.cursor()\n"
    '+    cursor.execute(f"SELECT * FROM users WHERE name LIKE \'%{query}%\'")\n'
    "+    results = cursor.fetchall()\n"
    "+    conn.close()\n"
    "+    return jsonify(results)\n"
    "+\n"
    "+@app.route('/users/<int:user_id>/profile')\n"
    "+def user_profile(user_id):\n"
    "+    name = request.args.get('name', '')\n"
    '+    return f"<h1>Welcome, {name}</h1>"\n'
    "+\n"
    "+# TODO: add pagination\n"
    "+# TODO: add rate limiting\n"
    "+\n"
    "+unused_var = 42\n"
    "+\n"
)

_UTILS_PY_PATCH = (
    "@@ -10,6 +10,12 @@\n"
    " import os\n"
    " import logging\n"
    " \n"
    "+def format_name(name):\n"
    "+    # code smell: too many responsibilities\n"
    "+    name = name.strip()\n"
    "+    name = name.title()\n"
    "+    return name\n"
    "+\n"
)

_CONFIG_PY_PATCH = (
    "@@ -1,3 +1,5 @@\n"
    " DEBUG = True\n"
    "+# nit: inconsistent naming style\n"
    "+appTitle = 'My App'\n"
)

_FILES_PAYLOAD = [
    {
        "filename": "src/search.py",
        "status": "added",
        "additions": 25,
        "deletions": 0,
        "changes": 25,
        "patch": _SEARCH_PY_PATCH,
    },
    {
        "filename": "src/utils.py",
        "status": "modified",
        "additions": 6,
        "deletions": 0,
        "changes": 6,
        "patch": _UTILS_PY_PATCH,
    },
    {
        "filename": "src/config.py",
        "status": "modified",
        "additions": 2,
        "deletions": 0,
        "changes": 2,
        "patch": _CONFIG_PY_PATCH,
    },
]

# ── Gemini mock response builders ─────────────────────────────────────────────


def _gemini_text_response(text: str) -> MagicMock:
    """Build a mock Gemini GenerateContentResponse with plain text output."""
    part = MagicMock()
    part.text = text
    part.function_call = None

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _gemini_tool_call_response(tool_name: str, tool_args: dict) -> MagicMock:
    """Build a mock Gemini response that issues a function/tool call."""
    fc = MagicMock()
    fc.name = tool_name
    fc.args = tool_args

    tool_part = MagicMock()
    tool_part.function_call = fc
    tool_part.text = None

    tool_content = MagicMock()
    tool_content.parts = [tool_part]

    tool_candidate = MagicMock()
    tool_candidate.content = tool_content

    response = MagicMock()
    response.candidates = [tool_candidate]
    return response


def _gemini_empty_response() -> MagicMock:
    """Build a mock Gemini response with no candidates."""
    response = MagicMock()
    response.candidates = []
    return response


# ── Structured findings output from the "Gemini model" ───────────────────────

_MULTI_FINDING_OUTPUT = """\
Here is my review of PR #42: Add user search endpoint.

[P0] security: SQL Injection in user search endpoint
File: src/search.py lines 11-11
Description: The search query is interpolated directly into a SQL string via f-string. \
An attacker can inject arbitrary SQL through the `q` parameter, leading to full database compromise. \
This is a textbook SQL injection vulnerability.
Fix: Use parameterized queries: `cursor.execute("SELECT * FROM users WHERE name LIKE ?", (f"%{query}%",))`

[P1] security: Reflected XSS in user profile page
File: src/search.py lines 19-19
Description: User-supplied `name` parameter is rendered directly into HTML via f-string without escaping. \
An attacker can inject arbitrary JavaScript via the name parameter, enabling cross-site scripting attacks.
Fix: Use a templating engine with auto-escaping, or at minimum `markupsafe.escape(name)`.

[P2] bug: Code smell in format_name utility
File: src/utils.py lines 13-15
Description: The format_name function chains multiple string operations that could be a single \
expression. This is a minor code smell that reduces readability.
Fix: Combine into `return name.strip().title()`.

[P3] informational: Inconsistent naming style in config
File: src/config.py lines 3-3
Description: Variable `appTitle` uses camelCase which is inconsistent with the Python PEP 8 \
convention of snake_case used elsewhere in the project. This is a minor style issue.
"""

_NO_FINDINGS_OUTPUT = """\
I have reviewed PR #42: Add user search endpoint.

The code changes look correct and follow established patterns. No issues found.

Summary: Clean PR with no actionable findings.
"""

_QA_ANSWER_OUTPUT = """\
The search endpoint at `src/search.py:11` is vulnerable to SQL injection because \
the query parameter is directly interpolated into the SQL string using an f-string. \
An attacker could pass a value like `' OR 1=1 --` to dump the entire users table. \
Use parameterized queries to fix this.
"""

# ── File content for FETCH_FILE tool calls ────────────────────────────────────

_SEARCH_PY_FULL = """\
import sqlite3
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/users/search')
def search_users():
    query = request.args.get('q', '')
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE name LIKE '%{query}%'")
    results = cursor.fetchall()
    conn.close()
    return jsonify(results)

@app.route('/users/<int:user_id>/profile')
def user_profile(user_id):
    name = request.args.get('name', '')
    return f"<h1>Welcome, {name}</h1>"

# TODO: add pagination
# TODO: add rate limiting

unused_var = 42
"""

_UTILS_PY_FULL = (
    "import os\nimport logging\n\ndef format_name(name):\n    name = name.strip()\n"
    "    name = name.title()\n    return name\n"
)

# ── HTTP response helpers ─────────────────────────────────────────────────────


def _github_pr_responses(httpx_mock: HTTPXMock) -> None:
    """Register the three GitHub API responses for get_pr_metadata.

    get_pr_metadata fires three concurrent requests via asyncio.gather:
      1. GET /repos/:owner/:repo/pulls/:number
      2. GET /repos/:owner/:repo/pulls/:number/commits
      3. GET /repos/:owner/:repo/pulls/:number/files?per_page=100

    We use URL pattern matching so order of arrival does not matter.
    """
    httpx_mock.add_response(
        url=f"{_GH}/repos/acme/webapp/pulls/42",
        json=_PR_PAYLOAD,
    )
    httpx_mock.add_response(
        url=f"{_GH}/repos/acme/webapp/pulls/42/commits",
        json=_COMMITS_PAYLOAD,
    )
    httpx_mock.add_response(
        url=httpx.URL(f"{_GH}/repos/acme/webapp/pulls/42/files", params={"per_page": "100"}),
        json=_FILES_PAYLOAD,
    )


def _github_file_response(httpx_mock: HTTPXMock, path: str, content: str) -> None:
    """Register a GitHub file content response for a FETCH_FILE tool call."""
    encoded = base64.b64encode(content.encode()).decode()
    httpx_mock.add_response(
        url=httpx.URL(f"{_GH}/repos/acme/webapp/contents/{path}", params={"ref": "head999"}),
        json={
            "content": encoded + "\n",
            "sha": "filesha123",
            "size": len(content),
            "type": "file",
        },
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def github_client():
    """Create a real GitHubClient (HTTP mocked by pytest-httpx)."""
    client = GitHubClient(token="test-token-e2e")
    yield client
    await client.close()


@pytest.fixture
def reasoning_engine(github_client: GitHubClient):
    """Create a real ReasoningEngine with a real GitHubClient."""
    return ReasoningEngine(github_client=github_client, api_key="fake-gemini-key")


@pytest.fixture
def review_agent(github_client: GitHubClient, reasoning_engine: ReasoningEngine):
    """Create a real ReviewAgent wired with real internal components."""
    return ReviewAgent(github_client=github_client, reasoning_engine=reasoning_engine)


# ── Test 1: Full review with multiple findings ───────────────────────────────


class TestFullReviewPipeline:
    """Exercise the complete pipeline: GitHub fetch -> parse -> RLM -> findings."""

    async def test_full_review_with_multiple_findings(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """A PR with SQL injection, XSS, code smell, and style issue is reviewed
        end-to-end. Verifies that all four findings are parsed, severity is
        reclassified, and citations are validated against real diff hunks."""
        # Mock GitHub API (HTTP layer)
        _github_pr_responses(httpx_mock)

        # Mock Gemini SDK: tool call (FETCH_FILE) then final text with findings
        tool_response = _gemini_tool_call_response("FETCH_FILE", {"path": "src/search.py"})
        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)
        _github_file_response(httpx_mock, "src/search.py", _SEARCH_PY_FULL)

        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            side_effect=[tool_response, text_response],
        ):
            result = await review_agent.review(PR_REF)

        # Pipeline succeeded
        assert result.success is True
        assert result.error is None

        # All four findings were parsed
        assert len(result.findings) == 4

        # Findings are sorted by severity (P0 first)
        severities = [f.severity for f in result.findings]
        assert severities == [Severity.P0, Severity.P1, Severity.P2, Severity.P3]

        # Verify each finding type
        types = [f.type for f in result.findings]
        assert FindingType.SECURITY in types
        assert FindingType.BUG in types
        assert FindingType.INFORMATIONAL in types

        # P0 finding is the SQL injection
        p0 = result.findings[0]
        assert p0.severity == Severity.P0
        assert "sql" in p0.title.lower() or "sql" in p0.description.lower()
        assert p0.citation.file == "src/search.py"
        assert p0.fix is not None

        # P1 finding is the XSS
        p1 = result.findings[1]
        assert p1.severity == Severity.P1
        assert "xss" in p1.title.lower() or "xss" in p1.description.lower()
        assert p1.citation.file == "src/search.py"
        assert p1.fix is not None

        # P2 finding is the code smell
        p2 = result.findings[2]
        assert p2.severity == Severity.P2
        assert p2.citation.file == "src/utils.py"

        # P3 finding is the style issue
        p3 = result.findings[3]
        assert p3.severity == Severity.P3
        assert p3.citation.file == "src/config.py"

        # Blocking findings include P0 and P1
        assert len(result.blocking) == 2
        assert all(f.blocks_merge for f in result.blocking)

        # PR summary was generated
        assert result.pr_summary != ""
        assert "42" in result.pr_summary
        assert "alice" in result.pr_summary

        # Raw output preserved
        assert "SQL" in result.raw_output

    async def test_blocking_findings_have_fix_suggestions(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """P0 and P1 findings always have a fix suggestion (ensured by pipeline)."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        assert result.success
        for finding in result.findings:
            if finding.blocks_merge:
                assert finding.fix is not None
                assert len(finding.fix) > 0


# ── Test 2: Severity reclassification ─────────────────────────────────────────


class TestSeverityReclassification:
    """Verify that the severity reclassifier promotes findings based on content."""

    async def test_sql_injection_promoted_to_p0(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """A finding labeled P2 by the LLM but mentioning SQL injection
        gets promoted to P0 by the reclassifier."""
        _github_pr_responses(httpx_mock)

        # Gemini labels this as P2 but it mentions SQL injection
        mislabeled_output = """\
[P2] security: Possible query issue in search
File: src/search.py lines 11-11
Description: The user input is used in a SQL injection vulnerable pattern. \
The f-string interpolation into the SQL query allows arbitrary SQL execution.
Fix: Use parameterized queries.
"""
        text_response = _gemini_text_response(mislabeled_output)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        assert result.success
        assert len(result.findings) == 1
        # Reclassifier should promote P2 -> P0 based on "SQL injection" signal
        assert result.findings[0].severity == Severity.P0

    async def test_xss_promoted_to_p1(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """A finding labeled P3 mentioning XSS gets promoted to P1."""
        _github_pr_responses(httpx_mock)

        mislabeled_output = """\
[P3] security: Minor HTML rendering concern
File: src/search.py lines 19-19
Description: Cross-site scripting (XSS) is possible because user input \
is rendered directly into the HTML response without escaping.
Fix: Escape user input before rendering.
"""
        text_response = _gemini_text_response(mislabeled_output)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        assert result.success
        assert len(result.findings) == 1
        # "cross-site scripting" matches the P1 signal for XSS
        assert result.findings[0].severity == Severity.P1


# ── Test 3: Citation validation against diff hunks ────────────────────────────


class TestCitationValidation:
    """Verify that citations are validated against actual diff hunks."""

    async def test_citations_within_diff_are_kept(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """Findings with citations inside the diff hunk range pass validation."""
        _github_pr_responses(httpx_mock)

        # Citation at line 11 of src/search.py is within the diff (lines 1-25)
        output_with_valid_citation = """\
[P0] security: SQL Injection vulnerability
File: src/search.py lines 11-11
Description: SQL injection via f-string interpolation in the query.
Fix: Use parameterized queries.
"""
        text_response = _gemini_text_response(output_with_valid_citation)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        assert result.success
        assert len(result.findings) == 1
        citation = result.findings[0].citation
        assert citation.file == "src/search.py"
        assert citation.line_start == 11
        assert citation.line_end == 11

    async def test_citations_reference_correct_files(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """Each finding's citation references a file that exists in the PR diff."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        assert result.success
        diff_files = {"src/search.py", "src/utils.py", "src/config.py"}
        for finding in result.findings:
            assert finding.citation.file in diff_files


# ── Test 4: Engine failure returns failure result ─────────────────────────────


class TestEngineFailure:
    """Verify graceful handling when the Gemini API fails."""

    async def test_gemini_exception_returns_failure(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """A Gemini API error results in ReviewResult.success=False with error details."""
        _github_pr_responses(httpx_mock)

        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            side_effect=Exception("Gemini API quota exceeded: 429 Too Many Requests"),
        ):
            result = await review_agent.review(PR_REF)

        assert result.success is False
        assert result.error is not None
        assert "quota" in result.error.lower() or "429" in result.error
        assert len(result.findings) == 0

    async def test_gemini_empty_response_returns_failure(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """A Gemini response with no candidates results in failure."""
        _github_pr_responses(httpx_mock)

        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=_gemini_empty_response(),
        ):
            result = await review_agent.review(PR_REF)

        assert result.success is False
        assert result.error is not None

    @pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
    async def test_github_api_failure_returns_failure(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
    ) -> None:
        """A GitHub API error (e.g. 500) propagates as a review failure.

        Note: tenacity retries the _get method 5 times with exponential backoff.
        The retry fires on raise_for_status() for 500s. We register enough 500
        responses for all retry attempts across all three concurrent requests.
        """
        # get_pr_metadata fires 3 concurrent requests via asyncio.gather.
        # Each request retries up to 5 times. Register 15 error responses.
        for _ in range(15):
            httpx_mock.add_response(status_code=500, json={"message": "Internal Server Error"})

        result = await review_agent.review(PR_REF)

        assert result.success is False
        assert result.error is not None


# ── Test 5: Clean review with no findings ─────────────────────────────────────


class TestCleanReview:
    """Verify handling of PRs with no issues found."""

    async def test_no_findings_returns_clean_result(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """A clean PR produces a successful result with zero findings."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_NO_FINDINGS_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        assert result.success is True
        assert result.error is None
        assert len(result.findings) == 0
        assert len(result.blocking) == 0
        assert len(result.critical) == 0
        assert len(result.high) == 0
        assert result.raw_output != ""
        assert result.pr_summary != ""


# ── Test 6: Output formatting (JSON and Markdown) ────────────────────────────


class TestOutputFormatting:
    """Verify the formatter produces correct markdown and JSON from results."""

    async def test_markdown_output_contains_all_findings(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """Markdown output contains headers, badges, and all finding details."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        md = format_review_markdown(result)

        # Header present
        assert "## RunOwl Code Review" in md

        # Blocking status
        assert "blocking issue" in md.lower()

        # All severity badges present
        assert "P0 CRITICAL" in md
        assert "P1 HIGH" in md
        assert "P2 MEDIUM" in md
        assert "P3 LOW" in md

        # Finding titles or descriptions present
        assert "src/search.py" in md
        assert "src/utils.py" in md
        assert "src/config.py" in md

        # Footer
        assert "RunOwl" in md

    async def test_markdown_for_clean_review(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """A clean review produces markdown with a 'no issues' message."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_NO_FINDINGS_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        md = format_review_markdown(result)

        assert "## RunOwl Code Review" in md
        assert "No blocking issues" in md or "No issues found" in md
        assert "0 finding" in md.lower() or "no issues" in md.lower()

    async def test_markdown_for_failure(self) -> None:
        """A failed review produces an error markdown block."""
        from review.models import ReviewResult

        failed = ReviewResult(success=False, error="Gemini API quota exceeded")
        md = format_review_markdown(failed)
        assert "Failed" in md
        assert "Gemini API quota exceeded" in md

    async def test_json_output_structure(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """JSON output contains the expected structure with all fields."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        data = format_review_json(result)

        # Top-level fields
        assert data["success"] is True
        assert data["error"] is None

        # Summary section
        summary = data["summary"]
        assert summary["total"] == 4
        assert summary["blocking"] == 2
        assert summary["by_severity"]["P0"] == 1
        assert summary["by_severity"]["P1"] == 1
        assert summary["by_severity"]["P2"] == 1
        assert summary["by_severity"]["P3"] == 1

        # Findings array
        findings = data["findings"]
        assert len(findings) == 4

        # Each finding has all required fields
        for f in findings:
            assert "severity" in f
            assert "type" in f
            assert "title" in f
            assert "description" in f
            assert "citation" in f
            assert "file" in f["citation"]
            assert "line_start" in f["citation"]
            assert "line_end" in f["citation"]
            assert "fix" in f
            assert "blocks_merge" in f

        # P0 finding blocks merge
        p0_findings = [f for f in findings if f["severity"] == "P0"]
        assert len(p0_findings) == 1
        assert p0_findings[0]["blocks_merge"] is True

        # P3 finding does not block merge
        p3_findings = [f for f in findings if f["severity"] == "P3"]
        assert len(p3_findings) == 1
        assert p3_findings[0]["blocks_merge"] is False

    async def test_json_output_is_serializable(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """JSON output dict is fully JSON-serializable (no dataclass leaks)."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        data = format_review_json(result)
        # This will raise TypeError if any non-serializable objects leak through
        serialized = json.dumps(data)
        assert isinstance(serialized, str)
        # Round-trip back
        parsed = json.loads(serialized)
        assert parsed["success"] is True
        assert len(parsed["findings"]) == 4

    async def test_json_failure_output(self) -> None:
        """Failed review JSON has success=False and error details."""
        from review.models import ReviewResult

        failed = ReviewResult(success=False, error="API timeout after 30s")
        data = format_review_json(failed)

        assert data["success"] is False
        assert data["error"] == "API timeout after 30s"
        assert data["summary"]["total"] == 0
        assert data["summary"]["blocking"] == 0
        assert len(data["findings"]) == 0


# ── Test 7: Interactive Q&A via `ask` method ──────────────────────────────────


class TestInteractiveQA:
    """Verify the ask method for interactive Q&A about a PR."""

    async def test_ask_returns_answer_and_conversation(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """The ask method returns a text answer and updated conversation history."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_QA_ANSWER_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            answer, conversation = await review_agent.ask(
                PR_REF,
                "Is the search endpoint vulnerable to SQL injection?",
            )

        assert isinstance(answer, str)
        assert len(answer) > 0
        assert "sql" in answer.lower() or "injection" in answer.lower()

        # Conversation history is returned for follow-up questions
        assert isinstance(conversation, list)
        assert len(conversation) >= 2  # at least user question + model answer

    async def test_ask_with_selected_code(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """The ask method accepts selected code context."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(
            "Yes, this line is vulnerable. The f-string interpolation allows SQL injection."
        )
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            answer, conversation = await review_agent.ask(
                PR_REF,
                "Is this line safe?",
                selected_code='cursor.execute(f"SELECT * FROM users WHERE name LIKE \'%{query}%\'")',
            )

        assert isinstance(answer, str)
        assert len(answer) > 0

    async def test_ask_with_conversation_history(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """Follow-up questions can pass prior conversation for context."""
        # First question
        _github_pr_responses(httpx_mock)

        first_response = _gemini_text_response(_QA_ANSWER_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=first_response,
        ):
            answer1, convo1 = await review_agent.ask(
                PR_REF,
                "Is the search endpoint safe?",
            )

        # Follow-up question with conversation context
        # Re-register GitHub responses for second call
        _github_pr_responses(httpx_mock)

        followup_response = _gemini_text_response(
            "To fix it, replace the f-string with a parameterized query: "
            '`cursor.execute("SELECT * FROM users WHERE name LIKE ?", (f"%{query}%",))`'
        )
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=followup_response,
        ):
            answer2, convo2 = await review_agent.ask(
                PR_REF,
                "How do I fix it?",
                conversation=convo1,
            )

        assert isinstance(answer2, str)
        assert "parameterized" in answer2.lower() or "fix" in answer2.lower()
        # Conversation grew with the follow-up exchange
        assert len(convo2) > len(convo1)

    async def test_ask_with_tool_call(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """The ask path supports tool calls (FETCH_FILE) before answering."""
        _github_pr_responses(httpx_mock)
        _github_file_response(httpx_mock, "src/search.py", _SEARCH_PY_FULL)

        tool_response = _gemini_tool_call_response("FETCH_FILE", {"path": "src/search.py"})
        text_response = _gemini_text_response(
            "After examining the file, the search function at line 11 uses "
            "direct string interpolation in a SQL query, which is vulnerable."
        )
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            side_effect=[tool_response, text_response],
        ):
            answer, conversation = await review_agent.ask(
                PR_REF,
                "Can you look at src/search.py and tell me if it's safe?",
            )

        assert isinstance(answer, str)
        assert "vulnerable" in answer.lower() or "interpolation" in answer.lower()


# ── Test: Multi-step tool usage ───────────────────────────────────────────────


class TestMultiStepToolUsage:
    """Verify the engine handles multi-step tool calls before producing output."""

    async def test_multiple_tool_calls_before_final_output(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """The engine can make multiple FETCH_FILE calls across iterations
        before producing the final review output."""
        _github_pr_responses(httpx_mock)

        # Register file responses for two FETCH_FILE calls
        _github_file_response(httpx_mock, "src/search.py", _SEARCH_PY_FULL)
        _github_file_response(httpx_mock, "src/utils.py", _UTILS_PY_FULL)

        # Gemini makes two tool calls (one per iteration) then produces findings
        tool1 = _gemini_tool_call_response("FETCH_FILE", {"path": "src/search.py"})
        tool2 = _gemini_tool_call_response("FETCH_FILE", {"path": "src/utils.py"})
        final = _gemini_text_response(_MULTI_FINDING_OUTPUT)

        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            side_effect=[tool1, tool2, final],
        ):
            result = await review_agent.review(PR_REF)

        assert result.success is True
        assert len(result.findings) == 4

    async def test_step_callback_receives_all_steps(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """The step callback receives reasoning, tool call, LLM call, and output steps."""
        _github_pr_responses(httpx_mock)
        _github_file_response(httpx_mock, "src/search.py", _SEARCH_PY_FULL)

        tool_response = _gemini_tool_call_response("FETCH_FILE", {"path": "src/search.py"})
        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)

        steps_received = []

        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            side_effect=[tool_response, text_response],
        ):
            result = await review_agent.review(
                PR_REF,
                step_callback=lambda step: steps_received.append(step),
            )

        assert result.success
        step_types = {s.type for s in steps_received}
        # Should have at least reasoning, llm_call, tool_call, and output steps
        assert "reasoning" in step_types
        assert "llm_call" in step_types
        assert "tool_call" in step_types
        assert "output" in step_types


# ── Test: ReviewResult property accessors ─────────────────────────────────────


class TestReviewResultAccessors:
    """Verify the ReviewResult convenience properties work through the pipeline."""

    async def test_by_severity_and_by_type(
        self,
        httpx_mock: HTTPXMock,
        review_agent: ReviewAgent,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        """The by_severity and by_type accessors return correct subsets."""
        _github_pr_responses(httpx_mock)

        text_response = _gemini_text_response(_MULTI_FINDING_OUTPUT)
        with patch.object(
            reasoning_engine._gemini.models,
            "generate_content",
            return_value=text_response,
        ):
            result = await review_agent.review(PR_REF)

        assert result.success

        # by_severity
        assert len(result.by_severity(Severity.P0)) == 1
        assert len(result.by_severity(Severity.P1)) == 1
        assert len(result.by_severity(Severity.P2)) == 1
        assert len(result.by_severity(Severity.P3)) == 1

        # by_type
        security_findings = result.by_type(FindingType.SECURITY)
        assert len(security_findings) >= 2  # SQL injection + XSS

        # critical and high convenience
        assert len(result.critical) == 1
        assert len(result.high) == 1
