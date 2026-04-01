"""End-to-end tests for the test generation pipeline (parsing logic only).

Exercises _extract_description, _infer_test_type, _parse_test_cases,
TestSuite aggregation, and results formatting — without any Claude API calls.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from testing.generator import _extract_description, _infer_test_type, _parse_test_cases
from testing.models import (
    Confidence,
    FrameworkType,
    TestCase,
    TestResult,
    TestStatus,
    TestSuite,
    TestType,
)
from testing.results import (
    _suite_from_dict,
    _suite_to_dict,
    format_results_json,
    format_results_markdown,
)


# ---------------------------------------------------------------------------
# Realistic Claude output fixtures
# ---------------------------------------------------------------------------

_CLAUDE_OUTPUT_MULTI = """\
Here are the generated tests for the PR changes:

```python
# tests/test_auth.py
# confidence: high
# covers: src/auth.py:15
\"\"\"Test login audit logging\"\"\"
import pytest

def test_login_writes_audit_log(mocker):
    mock_audit = mocker.patch("src.auth.audit_log")
    login("testuser")
    mock_audit.assert_called_once_with("testuser", "login")

def test_login_returns_token():
    result = login("testuser")
    assert result is not None
```

```typescript
// tests/api.test.ts
// confidence: medium
// covers: src/api.ts:42
// Integration test for API endpoint
import { describe, it, expect } from 'vitest';
import { createApp } from '../src/app';
import supertest from 'supertest';

describe('POST /api/login', () => {
  it('returns 200 on valid credentials', async () => {
    const app = createApp();
    const res = await supertest(app).post('/api/login').send({ user: 'test' });
    expect(res.status).toBe(200);
  });
});
```

```python
# tests/test_utils.py
# confidence: low
# covers: src/utils.py:5
# Helper utility tests
import pytest

def test_helper_returns_none():
    from src.utils import helper
    assert helper() is None
```
"""

_CLAUDE_OUTPUT_PLAYWRIGHT = """\
```python
# tests/e2e/test_login_flow.py
# confidence: high
# covers: src/auth.py:10
\"\"\"E2E login flow test\"\"\"
from playwright.sync_api import Page

def test_login_page_loads(page: Page):
    page.goto("/login")
    assert page.title() == "Login"

def test_login_form_submit(page: Page):
    page.goto("/login")
    page.fill("#username", "admin")
    page.click("button[type=submit]")
    assert page.url.endswith("/dashboard")
```
"""

_CLAUDE_OUTPUT_HTTPX = """\
```python
# tests/test_api_integration.py
# confidence: medium
# covers: src/api.py:20
# Integration tests using httpx
import httpx
import pytest

@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/health")
    assert response.status_code == 200
```
"""


# ---------------------------------------------------------------------------
# Full parse flow
# ---------------------------------------------------------------------------


class TestFullParseFlow:
    """Realistic Claude output with multiple Python+TypeScript test blocks
    -> parsed test cases with correct types, confidence, source files."""

    def test_parses_multiple_blocks(self) -> None:
        cases = _parse_test_cases(_CLAUDE_OUTPUT_MULTI, FrameworkType.PYTEST)
        assert len(cases) == 3

    def test_first_case_metadata(self) -> None:
        cases = _parse_test_cases(_CLAUDE_OUTPUT_MULTI, FrameworkType.PYTEST)
        py_case = cases[0]
        assert py_case.name == "tests/test_auth.py"
        assert py_case.confidence == Confidence.HIGH
        assert py_case.source_file == "src/auth.py"
        assert py_case.diff_line_start == 15

    def test_second_case_is_integration(self) -> None:
        cases = _parse_test_cases(_CLAUDE_OUTPUT_MULTI, FrameworkType.PYTEST)
        ts_case = cases[1]
        assert ts_case.name == "tests/api.test.ts"
        assert ts_case.type == TestType.INTEGRATION
        assert ts_case.confidence == Confidence.MEDIUM
        # _COVERS_RE only matches '#' comments, not '//' — so source_file is empty
        # for TypeScript blocks using // comments
        assert ts_case.source_file == ""

    def test_third_case_is_low_confidence(self) -> None:
        cases = _parse_test_cases(_CLAUDE_OUTPUT_MULTI, FrameworkType.PYTEST)
        util_case = cases[2]
        assert util_case.name == "tests/test_utils.py"
        assert util_case.confidence == Confidence.LOW
        assert util_case.source_file == "src/utils.py"

    def test_descriptions_extracted(self) -> None:
        cases = _parse_test_cases(_CLAUDE_OUTPUT_MULTI, FrameworkType.PYTEST)
        # _extract_description picks the first non-confidence/covers comment,
        # which is the filename comment "# tests/test_auth.py"
        assert cases[0].description == "tests/test_auth.py"
        # Third case likewise gets its filename comment as description
        assert cases[2].description != ""

    def test_code_content_present(self) -> None:
        cases = _parse_test_cases(_CLAUDE_OUTPUT_MULTI, FrameworkType.PYTEST)
        for case in cases:
            assert len(case.code) > 20
            assert "def " in case.code or "describe" in case.code


# ---------------------------------------------------------------------------
# Test type inference
# ---------------------------------------------------------------------------


class TestTypeInference:
    """pytest code -> UNIT, httpx code -> INTEGRATION, Playwright code -> E2E."""

    def test_plain_pytest_is_unit(self) -> None:
        code = "def test_foo():\n    assert 1 + 1 == 2"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.UNIT

    def test_httpx_code_is_integration(self) -> None:
        code = "import httpx\nasync def test_api():\n    async with httpx.AsyncClient() as c:\n        pass"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.INTEGRATION

    def test_test_client_is_integration(self) -> None:
        code = "from app import test_client\ndef test_endpoint():\n    resp = test_client.get('/health')"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.INTEGRATION

    def test_supertest_is_integration(self) -> None:
        code = "import supertest from 'supertest';\nconst res = await supertest(app).get('/api/foo');"
        assert _infer_test_type(code, FrameworkType.JEST) == TestType.INTEGRATION

    def test_api_route_is_integration(self) -> None:
        code = "response = client.get('/api/users')\nassert response.status_code == 200"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.INTEGRATION

    def test_playwright_framework_is_e2e(self) -> None:
        code = "def test_something():\n    pass"
        assert _infer_test_type(code, FrameworkType.PLAYWRIGHT) == TestType.E2E

    def test_page_dot_usage_is_e2e(self) -> None:
        code = "def test_login(page):\n    page.goto('/login')"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.E2E

    def test_browser_dot_usage_is_e2e(self) -> None:
        code = "async def test_browser():\n    ctx = await browser.new_context()"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.E2E


# ---------------------------------------------------------------------------
# TestSuite aggregation
# ---------------------------------------------------------------------------


class TestSuiteAggregation:
    """Mixed pass/fail/error/skip/timeout results -> correct counts and properties."""

    @pytest.fixture
    def mixed_suite(self) -> TestSuite:
        suite = TestSuite(
            pr_ref="acme/widgets#42",
            framework=FrameworkType.PYTEST,
            generation_success=True,
        )
        suite.results = [
            TestResult(test_id="1", test_name="test_a", status=TestStatus.PASS, duration_ms=100),
            TestResult(test_id="2", test_name="test_b", status=TestStatus.PASS, duration_ms=50),
            TestResult(test_id="3", test_name="test_c", status=TestStatus.FAIL, duration_ms=200,
                       error_message="AssertionError: expected 1 got 2"),
            TestResult(test_id="4", test_name="test_d", status=TestStatus.ERROR, duration_ms=10,
                       error_message="ImportError: no module named 'foo'"),
            TestResult(test_id="5", test_name="test_e", status=TestStatus.SKIP),
            TestResult(test_id="6", test_name="test_f", status=TestStatus.TIMEOUT, duration_ms=30000),
        ]
        return suite

    def test_total_count(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.total == 6

    def test_passed_count(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.passed == 2

    def test_failed_count(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.failed == 1

    def test_errors_count(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.errors == 1

    def test_skipped_count(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.skipped == 1

    def test_timed_out_count(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.timed_out == 1

    def test_all_passed_is_false(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.all_passed is False

    def test_has_failures_is_true(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.has_failures is True

    def test_all_passed_when_all_pass(self) -> None:
        suite = TestSuite(pr_ref="x/y#1", framework=FrameworkType.PYTEST)
        suite.results = [
            TestResult(test_id="1", test_name="t1", status=TestStatus.PASS),
            TestResult(test_id="2", test_name="t2", status=TestStatus.PASS),
        ]
        assert suite.all_passed is True
        assert suite.has_failures is False

    def test_all_passed_false_when_empty(self) -> None:
        suite = TestSuite(pr_ref="x/y#1", framework=FrameworkType.PYTEST)
        assert suite.all_passed is False

    def test_result_for_lookup(self, mixed_suite: TestSuite) -> None:
        r = mixed_suite.result_for("3")
        assert r is not None
        assert r.test_name == "test_c"
        assert r.status == TestStatus.FAIL

    def test_result_for_missing(self, mixed_suite: TestSuite) -> None:
        assert mixed_suite.result_for("999") is None

    def test_to_summary(self, mixed_suite: TestSuite) -> None:
        summary = mixed_suite.to_summary()
        assert summary["total"] == 6
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["errors"] == 1
        assert summary["skipped"] == 1
        assert summary["timed_out"] == 1
        assert summary["all_passed"] is False


# ---------------------------------------------------------------------------
# Results formatting — markdown
# ---------------------------------------------------------------------------


class TestMarkdownFormatting:
    """Markdown output for all-pass suite, suite with failures, suite with generation error."""

    def test_all_pass_markdown(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#1",
            framework=FrameworkType.PYTEST,
            generation_success=True,
        )
        suite.results = [
            TestResult(test_id="1", test_name="test_ok", status=TestStatus.PASS, duration_ms=120),
        ]
        md = format_results_markdown(suite)
        assert "All Passed" in md
        assert "test_ok" in md
        assert "pass" in md.lower()
        assert "120" in md

    def test_failure_markdown_includes_details(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#2",
            framework=FrameworkType.PYTEST,
            generation_success=True,
        )
        suite.results = [
            TestResult(test_id="1", test_name="test_pass", status=TestStatus.PASS),
            TestResult(
                test_id="2",
                test_name="test_broken",
                status=TestStatus.FAIL,
                error_message="AssertionError: expected True",
            ),
        ]
        md = format_results_markdown(suite)
        assert "Failures Detected" in md
        assert "test_broken" in md
        assert "AssertionError" in md
        assert "<details>" in md

    def test_generation_error_markdown(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#3",
            framework=FrameworkType.PYTEST,
            generation_success=False,
            generation_error="Claude API rate limit exceeded",
        )
        md = format_results_markdown(suite)
        assert "generation failed" in md.lower() or "rate limit" in md.lower()

    def test_empty_results_no_generation(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#4",
            framework=FrameworkType.PYTEST,
            generation_success=False,
            generation_error="no test cases were produced",
        )
        md = format_results_markdown(suite)
        assert "no test cases" in md.lower()

    def test_markdown_contains_framework(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#5",
            framework=FrameworkType.JEST,
            generation_success=True,
        )
        suite.results = [
            TestResult(test_id="1", test_name="t1", status=TestStatus.PASS),
        ]
        md = format_results_markdown(suite)
        assert "jest" in md.lower()

    def test_error_status_in_markdown(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#6",
            framework=FrameworkType.PYTEST,
            generation_success=True,
        )
        suite.results = [
            TestResult(
                test_id="1",
                test_name="test_crash",
                status=TestStatus.ERROR,
                error_message="RuntimeError: segfault",
            ),
        ]
        md = format_results_markdown(suite)
        assert "test_crash" in md
        assert "RuntimeError" in md


# ---------------------------------------------------------------------------
# Results formatting — JSON
# ---------------------------------------------------------------------------


class TestJSONFormatting:
    """JSON formatting with correct structure."""

    def test_json_structure(self) -> None:
        suite = TestSuite(
            id="test-suite-id",
            pr_ref="acme/widgets#7",
            framework=FrameworkType.PYTEST,
            generation_success=True,
        )
        suite.results = [
            TestResult(test_id="r1", test_name="test_one", status=TestStatus.PASS, duration_ms=50),
            TestResult(test_id="r2", test_name="test_two", status=TestStatus.FAIL, duration_ms=100,
                       error_message="assertion failed"),
        ]
        data = format_results_json(suite)

        assert data["suite_id"] == "test-suite-id"
        assert data["pr_ref"] == "acme/widgets#7"
        assert data["framework"] == "pytest"
        assert data["generation_success"] is True
        assert data["generation_error"] is None

        assert "summary" in data
        assert data["summary"]["total"] == 2
        assert data["summary"]["passed"] == 1
        assert data["summary"]["failed"] == 1

        assert len(data["results"]) == 2
        assert data["results"][0]["test_id"] == "r1"
        assert data["results"][0]["status"] == "pass"
        assert data["results"][1]["error_message"] == "assertion failed"

    def test_json_serializable(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#8",
            framework=FrameworkType.VITEST,
            generation_success=True,
        )
        suite.results = [
            TestResult(test_id="1", test_name="t", status=TestStatus.PASS),
        ]
        data = format_results_json(suite)
        serialized = json.dumps(data)
        assert isinstance(serialized, str)
        roundtrip = json.loads(serialized)
        assert roundtrip["framework"] == "vitest"

    def test_json_empty_suite(self) -> None:
        suite = TestSuite(
            pr_ref="acme/widgets#9",
            framework=FrameworkType.UNKNOWN,
            generation_success=False,
            generation_error="no output",
        )
        data = format_results_json(suite)
        assert data["results"] == []
        assert data["generation_success"] is False
        assert data["generation_error"] == "no output"


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """_suite_to_dict -> _suite_from_dict preserves data."""

    def test_round_trip_basic(self) -> None:
        suite = TestSuite(
            id="rt-001",
            pr_ref="org/repo#100",
            framework=FrameworkType.PYTEST,
            generation_success=True,
            generation_error=None,
        )
        now = datetime.utcnow()
        suite.results = [
            TestResult(
                test_id="t1",
                test_name="test_round",
                status=TestStatus.PASS,
                duration_ms=42.5,
                stdout="ok",
                stderr="",
                error_message="",
                video_path=None,
                replay_path=None,
                screenshots=[],
                executed_at=now,
            ),
            TestResult(
                test_id="t2",
                test_name="test_fail",
                status=TestStatus.FAIL,
                duration_ms=100.0,
                stdout="",
                stderr="traceback",
                error_message="AssertionError",
                video_path="/tmp/video.webm",
                replay_path="/tmp/replay.json",
                screenshots=["/tmp/ss1.png"],
                executed_at=now,
            ),
        ]
        d = _suite_to_dict(suite)
        restored = _suite_from_dict(d)

        assert restored.id == "rt-001"
        assert restored.pr_ref == "org/repo#100"
        assert restored.framework == FrameworkType.PYTEST
        assert restored.generation_success is True
        assert restored.generation_error is None
        assert len(restored.results) == 2

        r0 = restored.results[0]
        assert r0.test_id == "t1"
        assert r0.test_name == "test_round"
        assert r0.status == TestStatus.PASS
        assert r0.duration_ms == 42.5

        r1 = restored.results[1]
        assert r1.test_id == "t2"
        assert r1.status == TestStatus.FAIL
        assert r1.error_message == "AssertionError"
        assert r1.video_path == "/tmp/video.webm"
        assert r1.replay_path == "/tmp/replay.json"
        assert r1.screenshots == ["/tmp/ss1.png"]

    def test_round_trip_via_json(self) -> None:
        suite = TestSuite(
            id="rt-002",
            pr_ref="acme/x#5",
            framework=FrameworkType.JEST,
            generation_success=False,
            generation_error="timeout",
        )
        suite.results = [
            TestResult(
                test_id="x",
                test_name="test_timeout",
                status=TestStatus.TIMEOUT,
                duration_ms=30000,
                executed_at=datetime(2025, 1, 15, 12, 0, 0),
            ),
        ]
        d = _suite_to_dict(suite)
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        restored = _suite_from_dict(d2)

        assert restored.id == "rt-002"
        assert restored.framework == FrameworkType.JEST
        assert restored.generation_error == "timeout"
        assert restored.results[0].status == TestStatus.TIMEOUT

    def test_round_trip_empty_results(self) -> None:
        suite = TestSuite(
            id="rt-003",
            pr_ref="acme/y#1",
            framework=FrameworkType.UNKNOWN,
        )
        d = _suite_to_dict(suite)
        restored = _suite_from_dict(d)
        assert restored.results == []
        assert restored.framework == FrameworkType.UNKNOWN


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Deduplication of identical test blocks."""

    def test_duplicate_code_blocks_deduplicated(self) -> None:
        raw = """\
```python
# tests/test_dup.py
def test_same():
    assert True
```

Some explanation text here.

```python
# tests/test_dup.py
def test_same():
    assert True
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1

    def test_different_blocks_kept(self) -> None:
        raw = """\
```python
# tests/test_a.py
def test_alpha():
    assert 1 == 1
```

```python
# tests/test_b.py
def test_beta():
    assert 2 == 2
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 2

    def test_empty_blocks_skipped(self) -> None:
        raw = """\
```python
```

```python
# tests/test_real.py
def test_something():
    pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1


# ---------------------------------------------------------------------------
# Framework detection edge cases
# ---------------------------------------------------------------------------


class TestFrameworkEdgeCases:
    """Framework detection edge cases in _infer_test_type."""

    def test_mixed_httpx_and_page_prefers_e2e(self) -> None:
        # page. takes priority (checked first via framework)
        code = "import httpx\ndef test_mixed():\n    page.goto('/test')"
        result = _infer_test_type(code, FrameworkType.PYTEST)
        assert result == TestType.E2E

    def test_empty_code_defaults_to_unit(self) -> None:
        assert _infer_test_type("", FrameworkType.PYTEST) == TestType.UNIT

    def test_vitest_simple_code_is_unit(self) -> None:
        code = "describe('math', () => { it('adds', () => { expect(1+1).toBe(2); }); });"
        assert _infer_test_type(code, FrameworkType.VITEST) == TestType.UNIT

    def test_jest_with_supertest_is_integration(self) -> None:
        code = "const request = require('supertest');\nrequest(app).get('/api/health');"
        assert _infer_test_type(code, FrameworkType.JEST) == TestType.INTEGRATION

    def test_playwright_framework_always_e2e(self) -> None:
        code = "def test_minimal():\n    pass"
        assert _infer_test_type(code, FrameworkType.PLAYWRIGHT) == TestType.E2E


# ---------------------------------------------------------------------------
# _extract_description edge cases
# ---------------------------------------------------------------------------


class TestExtractDescription:
    """Direct tests for _extract_description."""

    def test_docstring_extraction(self) -> None:
        code = '"""Check that login works"""\ndef test_login():\n    pass'
        assert "login" in _extract_description(code).lower()

    def test_comment_extraction(self) -> None:
        code = "# Verify the signup flow\ndef test_signup():\n    pass"
        desc = _extract_description(code)
        assert "signup" in desc.lower() or "Verify" in desc

    def test_skips_confidence_comment(self) -> None:
        code = "# confidence: high\n# Real description\ndef test():\n    pass"
        desc = _extract_description(code)
        assert "confidence" not in desc.lower()
        assert desc != ""

    def test_skips_covers_comment(self) -> None:
        code = "# covers: src/auth.py:10\n# Actual description\ndef test():\n    pass"
        desc = _extract_description(code)
        assert "covers" not in desc.lower()
        assert desc != ""

    def test_no_description(self) -> None:
        code = "def test_bare():\n    assert True"
        desc = _extract_description(code)
        assert desc == ""

    def test_single_quote_docstring(self) -> None:
        code = "'''Tests the helper function'''\ndef test():\n    pass"
        desc = _extract_description(code)
        assert "helper" in desc.lower()
