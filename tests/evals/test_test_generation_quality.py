"""AI evals for test generation output quality.

Evaluates how accurately the parsing logic handles diverse Claude output
and whether generated test metadata is correct.
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
# Helpers
# ---------------------------------------------------------------------------


def _suite_with_results(statuses: list[TestStatus], **kwargs) -> TestSuite:
    """Build a TestSuite with results of the given statuses."""
    suite = TestSuite(pr_ref="owner/repo#1", framework=FrameworkType.PYTEST, **kwargs)
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


# ===================================================================
# 1. Parse Quality Golden Dataset (15+ test cases)
# ===================================================================


class TestParseQualityGoldenDataset:
    """Realistic Claude outputs of varying complexity."""

    # -- Python-only output (2-3 blocks) --

    def test_python_two_blocks(self) -> None:
        raw = """Here are the tests I generated:

```python
# tests/test_auth.py
# confidence: high
# covers: src/auth.py:42

import pytest

def test_login_returns_token():
    token = login("user", "pass")
    assert token is not None
```

Some explanation text between the blocks.

```python
# tests/test_users.py
# confidence: medium
# covers: src/users.py:10

def test_create_user():
    user = create_user("alice")
    assert user.name == "alice"
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 2
        assert cases[0].name == "tests/test_auth.py"
        assert cases[0].confidence == Confidence.HIGH
        assert cases[0].source_file == "src/auth.py"
        assert cases[0].diff_line_start == 42
        assert cases[0].framework == FrameworkType.PYTEST
        assert cases[1].name == "tests/test_users.py"
        assert cases[1].confidence == Confidence.MEDIUM
        assert cases[1].source_file == "src/users.py"
        assert cases[1].diff_line_start == 10

    def test_python_three_blocks_with_low_confidence(self) -> None:
        raw = """```python
# tests/test_a.py
# confidence: low
# covers: src/a.py:1
def test_a(): pass
```

```python
# tests/test_b.py
# confidence: high
# covers: src/b.py:55
def test_b(): pass
```

```python
# tests/test_c.py
def test_c(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 3
        assert cases[0].confidence == Confidence.LOW
        assert cases[1].confidence == Confidence.HIGH
        # No confidence annotation => default MEDIUM
        assert cases[2].confidence == Confidence.MEDIUM
        # No covers annotation => empty source_file
        assert cases[2].source_file == ""
        assert cases[2].diff_line_start == 0

    # -- TypeScript-only output (1-2 blocks) --

    def test_typescript_single_block(self) -> None:
        raw = """```typescript
// tests/auth.test.ts
// confidence: high

describe("auth", () => {
    it("should login", () => {
        expect(login()).toBeTruthy();
    });
});
```
"""
        cases = _parse_test_cases(raw, FrameworkType.JEST)
        assert len(cases) == 1
        assert cases[0].name == "tests/auth.test.ts"
        assert cases[0].framework == FrameworkType.JEST

    def test_typescript_two_blocks_js_fence(self) -> None:
        raw = """```js
// tests/utils.test.js
describe("utils", () => { it("works", () => {}); });
```

```ts
// tests/api.test.ts
describe("api", () => { it("fetches", () => {}); });
```
"""
        cases = _parse_test_cases(raw, FrameworkType.VITEST)
        assert len(cases) == 2
        assert cases[0].name == "tests/utils.test.js"
        assert cases[1].name == "tests/api.test.ts"

    # -- Mixed Python + TypeScript --

    def test_mixed_python_and_typescript(self) -> None:
        raw = """```python
# tests/test_backend.py
# confidence: high
# covers: src/backend.py:100
def test_endpoint(): pass
```

```typescript
// tests/frontend.spec.ts
describe("frontend", () => { it("renders", () => {}); });
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 2
        assert cases[0].name == "tests/test_backend.py"
        assert cases[0].confidence == Confidence.HIGH
        assert cases[1].name == "tests/frontend.spec.ts"

    # -- Output with prose between code blocks --

    def test_prose_between_blocks_ignored(self) -> None:
        raw = """I've analyzed the PR diff and generated the following tests.

**Test 1: Authentication**

This test verifies the login endpoint.

```python
# tests/test_login.py
def test_login(): pass
```

**Test 2: Registration**

This test covers user registration.

```python
# tests/test_register.py
def test_register(): pass
```

That's it! Let me know if you need changes.
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 2
        assert cases[0].name == "tests/test_login.py"
        assert cases[1].name == "tests/test_register.py"

    # -- Output with no code blocks --

    def test_no_code_blocks_returns_empty(self) -> None:
        raw = """I reviewed the PR but couldn't generate meaningful tests.
The changes are purely configuration updates."""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert cases == []

    def test_empty_string_returns_empty(self) -> None:
        cases = _parse_test_cases("", FrameworkType.PYTEST)
        assert cases == []

    def test_fenced_block_without_language_tag_still_parsed(self) -> None:
        """The regex makes the language tag optional, so bare ``` blocks are parsed."""
        raw = """```
some generic code
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        # Language tag is optional in _CODE_BLOCK_RE, so this block IS extracted
        assert len(cases) == 1
        assert cases[0].name == "generated_test_1"

    # -- Duplicate blocks --

    def test_duplicate_blocks_deduplicated(self) -> None:
        block = "# tests/test_dup.py\ndef test_dup(): pass"
        raw = f"```python\n{block}\n```\n\n```python\n{block}\n```"
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1

    def test_near_duplicate_blocks_not_deduplicated(self) -> None:
        raw = """```python
# tests/test_a.py
def test_a(): assert True
```

```python
# tests/test_a.py
def test_a(): assert False
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        # Different code content, same filename -- both kept
        assert len(cases) == 2

    # -- Large output with 8+ blocks --

    def test_large_output_eight_blocks(self) -> None:
        blocks = []
        for i in range(8):
            blocks.append(
                f"```python\n# tests/test_mod{i}.py\n"
                f"# confidence: {'high' if i % 3 == 0 else 'medium'}\n"
                f"# covers: src/mod{i}.py:{i * 10 + 1}\n"
                f"def test_func_{i}(): assert {i} == {i}\n```"
            )
        raw = "\n\nSome prose between blocks.\n\n".join(blocks)
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 8
        # Spot check first and last
        assert cases[0].name == "tests/test_mod0.py"
        assert cases[0].confidence == Confidence.HIGH
        assert cases[0].source_file == "src/mod0.py"
        assert cases[0].diff_line_start == 1
        assert cases[7].name == "tests/test_mod7.py"
        assert cases[7].diff_line_start == 71

    def test_large_output_ten_blocks_mixed_frameworks(self) -> None:
        blocks = []
        for i in range(10):
            if i % 2 == 0:
                blocks.append(
                    f"```python\n# tests/test_py{i}.py\ndef test_{i}(): pass\n```"
                )
            else:
                blocks.append(
                    f"```typescript\n// tests/test_ts{i}.spec.ts\n"
                    f'describe("mod{i}", () => {{ it("works", () => {{}}); }});\n```'
                )
        raw = "\n".join(blocks)
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 10

    # -- Edge cases --

    def test_block_without_filename_gets_generic_name(self) -> None:
        raw = """```python
def test_something(): assert True
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1
        assert cases[0].name == "generated_test_1"

    def test_javascript_fence_tag(self) -> None:
        raw = """```javascript
// tests/utils.test.js
describe("utils", () => { it("works", () => {}); });
```
"""
        cases = _parse_test_cases(raw, FrameworkType.JEST)
        assert len(cases) == 1
        assert cases[0].name == "tests/utils.test.js"

    def test_default_confidence_is_medium(self) -> None:
        raw = """```python
# tests/test_no_conf.py
def test_no_confidence(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1
        assert cases[0].confidence == Confidence.MEDIUM


# ===================================================================
# 2. Type Inference Accuracy Eval (15+ test cases)
# ===================================================================


class TestTypeInferenceAccuracyEval:
    """Golden dataset of code snippets mapped to expected TestType."""

    # -- E2E indicators --

    def test_playwright_sync_api_import(self) -> None:
        code = "from playwright.sync_api import Page\ndef test_it(page: Page): pass"
        # "page." is not present in lowercase, but framework detection matters
        # Actually "page:" is there but _infer_test_type checks "page." in lower
        # The import line doesn't have "page." — let's check with PYTEST framework
        # playwright.sync_api doesn't trigger any keyword. But "Page" is capitalized.
        # Actually none of our keywords match here with PYTEST framework.
        # Let's verify: "page." not in code.lower() — "page:" is there, not "page."
        result = _infer_test_type(code, FrameworkType.PYTEST)
        # Without "page." or "browser.", and framework != PLAYWRIGHT, falls to UNIT
        assert result == TestType.UNIT

    def test_playwright_sync_api_import_with_playwright_framework(self) -> None:
        code = "from playwright.sync_api import Page"
        assert _infer_test_type(code, FrameworkType.PLAYWRIGHT) == TestType.E2E

    def test_page_goto_keyword(self) -> None:
        code = 'await page.goto("/login")\nawait page.fill("#user", "alice")'
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.E2E

    def test_page_click_keyword(self) -> None:
        code = 'page.click("#submit")'
        assert _infer_test_type(code, FrameworkType.JEST) == TestType.E2E

    def test_browser_new_context(self) -> None:
        code = "const context = browser.newContext();"
        assert _infer_test_type(code, FrameworkType.JEST) == TestType.E2E

    def test_browser_dot_launch(self) -> None:
        code = "const browser = await chromium.launch();\nawait browser.close();"
        # "browser." is present
        assert _infer_test_type(code, FrameworkType.VITEST) == TestType.E2E

    def test_playwright_framework_forces_e2e(self) -> None:
        code = "def test_something(): assert 1 + 1 == 2"
        assert _infer_test_type(code, FrameworkType.PLAYWRIGHT) == TestType.E2E

    # -- INTEGRATION indicators --

    def test_httpx_import(self) -> None:
        code = "import httpx\nasync with httpx.AsyncClient() as client: pass"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.INTEGRATION

    def test_test_client_get(self) -> None:
        code = 'response = test_client.get("/api/users")'
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.INTEGRATION

    def test_supertest_post(self) -> None:
        code = 'const res = await supertest(app).post("/api/login");'
        assert _infer_test_type(code, FrameworkType.JEST) == TestType.INTEGRATION

    def test_api_path_pattern(self) -> None:
        code = 'response = client.get("/api/users")'
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.INTEGRATION

    def test_api_path_in_typescript(self) -> None:
        code = 'const res = await fetch("/api/data");'
        assert _infer_test_type(code, FrameworkType.JEST) == TestType.INTEGRATION

    # -- UNIT indicators --

    def test_simple_assertion_is_unit(self) -> None:
        code = "def test_add(): assert 1 + 1 == 2"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.UNIT

    def test_plain_pytest_function(self) -> None:
        code = "import pytest\ndef test_it(): pass"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.UNIT

    def test_jest_describe_without_api_keywords(self) -> None:
        code = 'describe("math", () => { it("adds", () => { expect(1+1).toBe(2); }); });'
        assert _infer_test_type(code, FrameworkType.JEST) == TestType.UNIT

    def test_vitest_unit_test(self) -> None:
        code = 'import { describe, it, expect } from "vitest";\nit("works", () => {});'
        assert _infer_test_type(code, FrameworkType.VITEST) == TestType.UNIT

    # -- Priority / override checks --

    def test_page_keyword_overrides_api_path(self) -> None:
        """If code has both page. and /api/, E2E wins because page. is checked first."""
        code = 'await page.goto("/api/login")'
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.E2E

    def test_browser_keyword_overrides_httpx(self) -> None:
        """browser. check comes before httpx check."""
        code = "import httpx\nbrowser.close()"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.E2E


# ===================================================================
# 3. Description Extraction Eval (10+ test cases)
# ===================================================================


class TestDescriptionExtractionEval:
    """Golden dataset for _extract_description."""

    def test_first_comment_extracted(self) -> None:
        code = "# Test login flow\ndef test_login(): pass"
        assert _extract_description(code) == "Test login flow"

    def test_docstring_extracted(self) -> None:
        code = '"""Test auth"""\ndef test_auth(): pass'
        assert _extract_description(code) == "Test auth"

    def test_single_quote_docstring(self) -> None:
        code = "'''Test with single quotes'''\ndef test_it(): pass"
        assert _extract_description(code) == "Test with single quotes"

    def test_skip_confidence_comment(self) -> None:
        code = "# confidence: high\n# Test the auth flow\ndef test_auth(): pass"
        assert _extract_description(code) == "Test the auth flow"

    def test_skip_covers_comment(self) -> None:
        code = "# covers: src/auth.py:42\n# Verify login returns token\ndef test_it(): pass"
        assert _extract_description(code) == "Verify login returns token"

    def test_skip_both_confidence_and_covers(self) -> None:
        code = (
            "# confidence: high\n"
            "# covers: src/auth.py:42\n"
            "# Actual description here\n"
            "def test_it(): pass"
        )
        assert _extract_description(code) == "Actual description here"

    def test_no_comment_returns_empty(self) -> None:
        code = "def test_it(): pass"
        assert _extract_description(code) == ""

    def test_only_confidence_and_covers_returns_empty(self) -> None:
        code = "# confidence: medium\n# covers: src/a.py:1\ndef test_it(): pass"
        assert _extract_description(code) == ""

    def test_empty_code_returns_empty(self) -> None:
        assert _extract_description("") == ""

    def test_comment_with_extra_hashes(self) -> None:
        code = "## Section header\ndef test_it(): pass"
        # Starts with "#" but not "# confidence" or "# covers"
        # lstrip("# ") removes all leading '#' and spaces
        assert _extract_description(code) != ""

    def test_typescript_comment_not_extracted(self) -> None:
        """_extract_description only handles '#' comments, not '//' comments."""
        code = "// Test the API endpoint\nfunction test_it() {}"
        # "//" does not start with "#" or triple-quote
        assert _extract_description(code) == ""

    def test_filename_comment_used_as_description(self) -> None:
        """A filename comment like '# tests/test_auth.py' is a valid # comment
        that doesn't start with 'confidence' or 'covers', so it becomes the description."""
        code = "# tests/test_auth.py\n# confidence: high\ndef test_it(): pass"
        assert _extract_description(code) == "tests/test_auth.py"

    def test_description_past_line_ten_not_found(self) -> None:
        """_extract_description only checks the first 10 lines."""
        lines = ["def func(): pass"] * 11 + ["# This is too far down"]
        code = "\n".join(lines)
        assert _extract_description(code) == ""


# ===================================================================
# 4. Suite Aggregation Quality Eval (8+ test cases)
# ===================================================================


class TestSuiteAggregationQualityEval:
    """Build TestSuites with known results and verify aggregation properties."""

    def test_all_pass(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.PASS])
        assert suite.all_passed is True
        assert suite.has_failures is False
        assert suite.passed == 2
        assert suite.failed == 0
        assert suite.errors == 0

    def test_one_fail(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL])
        assert suite.all_passed is False
        assert suite.has_failures is True
        assert suite.failed == 1

    def test_one_error(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.ERROR])
        assert suite.has_failures is True
        assert suite.errors == 1
        assert suite.all_passed is False

    def test_timeout_counted_as_failure(self) -> None:
        suite = _suite_with_results([TestStatus.TIMEOUT])
        # has_failures checks failed > 0 or errors > 0
        # TIMEOUT is counted by timed_out, not failed or errors
        # So has_failures is False for TIMEOUT-only
        # But TestResult.failed property includes TIMEOUT
        assert suite.timed_out == 1
        # Note: all_passed checks failed==0 and errors==0; TIMEOUT doesn't affect those
        # so all_passed is True if total > 0 and no FAIL/ERROR — even with TIMEOUT
        assert suite.all_passed is True
        # Verify the result-level property still reports it as failed
        assert suite.results[0].failed is True

    def test_skip_not_counted_as_failure(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.SKIP])
        assert suite.has_failures is False
        assert suite.skipped == 1
        # SKIP doesn't prevent all_passed (only FAIL/ERROR do)
        assert suite.all_passed is True

    def test_empty_suite_not_all_passed(self) -> None:
        suite = TestSuite()
        assert suite.all_passed is False
        assert suite.total == 0

    def test_to_summary_has_all_required_keys(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL])
        summary = suite.to_summary()
        required_keys = {
            "id", "pr_ref", "framework", "total", "passed",
            "failed", "errors", "skipped", "timed_out", "all_passed",
        }
        assert required_keys.issubset(summary.keys())
        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["all_passed"] is False

    def test_result_for_returns_correct_result(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL, TestStatus.ERROR])
        result = suite.result_for("1")
        assert result is not None
        assert result.test_name == "test_case_1"
        assert result.status == TestStatus.FAIL

    def test_result_for_returns_none_for_missing_id(self) -> None:
        suite = _suite_with_results([TestStatus.PASS])
        assert suite.result_for("nonexistent") is None

    def test_mixed_statuses_counts(self) -> None:
        suite = _suite_with_results([
            TestStatus.PASS,
            TestStatus.PASS,
            TestStatus.FAIL,
            TestStatus.ERROR,
            TestStatus.SKIP,
            TestStatus.TIMEOUT,
        ])
        assert suite.total == 6
        assert suite.passed == 2
        assert suite.failed == 1
        assert suite.errors == 1
        assert suite.skipped == 1
        assert suite.timed_out == 1
        assert suite.has_failures is True
        assert suite.all_passed is False


# ===================================================================
# 5. Results Formatting Quality Eval (8+ test cases)
# ===================================================================


class TestResultsFormattingQualityEval:
    """Verify markdown and JSON formatting of test results."""

    def test_all_pass_markdown_contains_all_passed(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.PASS])
        md = format_results_markdown(suite)
        assert "All Passed" in md

    def test_failure_markdown_contains_failures_detected(self) -> None:
        suite = _suite_with_results([TestStatus.FAIL])
        md = format_results_markdown(suite)
        assert "Failures Detected" in md

    def test_failure_markdown_contains_error_details(self) -> None:
        suite = _suite_with_results([TestStatus.FAIL])
        suite.results[0].error_message = "AssertionError: expected True got False"
        md = format_results_markdown(suite)
        assert "AssertionError" in md
        assert "Failure details" in md

    def test_generation_error_markdown_shows_error_message(self) -> None:
        suite = TestSuite(pr_ref="owner/repo#1")
        suite.generation_success = False
        suite.generation_error = "Claude API timed out"
        md = format_results_markdown(suite)
        assert "Claude API timed out" in md

    def test_json_has_required_keys(self) -> None:
        suite = _suite_with_results([TestStatus.PASS])
        data = format_results_json(suite)
        assert "suite_id" in data
        assert "pr_ref" in data
        assert "framework" in data
        assert "results" in data
        assert "summary" in data
        assert data["suite_id"] == suite.id
        assert data["pr_ref"] == "owner/repo#1"
        assert data["framework"] == FrameworkType.PYTEST

    def test_json_results_array(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL])
        data = format_results_json(suite)
        assert len(data["results"]) == 2
        assert data["results"][0]["status"] == "pass"
        assert data["results"][1]["status"] == "fail"

    def test_json_is_serializable_roundtrip(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL, TestStatus.ERROR])
        data = format_results_json(suite)
        serialized = json.dumps(data)
        deserialized = json.loads(serialized)
        assert deserialized["suite_id"] == suite.id
        assert len(deserialized["results"]) == 3

    def test_empty_results_handled_gracefully(self) -> None:
        suite = TestSuite(pr_ref="owner/repo#1", framework=FrameworkType.PYTEST)
        suite.generation_success = True
        md = format_results_markdown(suite)
        # No results, but generation_success is True so no error message
        assert "No Results" in md
        data = format_results_json(suite)
        assert data["results"] == []
        assert data["summary"]["total"] == 0

    def test_error_status_markdown_shows_failure_details(self) -> None:
        suite = _suite_with_results([TestStatus.ERROR])
        suite.results[0].error_message = "RuntimeError: unexpected"
        md = format_results_markdown(suite)
        assert "Failures Detected" in md
        assert "RuntimeError" in md


# ===================================================================
# 6. Serialization Fidelity Eval (4+ test cases)
# ===================================================================


class TestSerializationFidelityEval:
    """Round-trip serialization via _suite_to_dict / _suite_from_dict."""

    def test_round_trip_with_results(self) -> None:
        suite = _suite_with_results([TestStatus.PASS, TestStatus.FAIL])
        suite.pr_ref = "myorg/myrepo#42"
        suite.framework = FrameworkType.JEST
        suite.generation_success = True
        suite.generation_error = None

        d = _suite_to_dict(suite)
        restored = _suite_from_dict(d)

        assert restored.id == suite.id
        assert restored.pr_ref == "myorg/myrepo#42"
        assert restored.framework == FrameworkType.JEST
        assert restored.generation_success is True
        assert restored.generation_error is None
        assert len(restored.results) == 2
        assert restored.results[0].status == TestStatus.PASS
        assert restored.results[1].status == TestStatus.FAIL
        assert restored.results[0].test_name == "test_case_0"
        assert restored.results[1].test_name == "test_case_1"

    def test_round_trip_with_all_result_fields(self) -> None:
        suite = TestSuite(
            pr_ref="org/repo#10",
            framework=FrameworkType.PLAYWRIGHT,
            generation_success=True,
        )
        suite.results.append(
            TestResult(
                test_id="abc",
                test_name="test_login_e2e",
                status=TestStatus.FAIL,
                duration_ms=1234.5,
                stdout="some stdout",
                stderr="some stderr",
                error_message="TimeoutError: waiting for selector",
                video_path="/tmp/video.webm",
                replay_path="/tmp/trace.json",
                screenshots=["/tmp/ss1.png", "/tmp/ss2.png"],
            )
        )

        d = _suite_to_dict(suite)
        restored = _suite_from_dict(d)

        r = restored.results[0]
        assert r.test_id == "abc"
        assert r.test_name == "test_login_e2e"
        assert r.status == TestStatus.FAIL
        assert r.duration_ms == 1234.5
        assert r.stdout == "some stdout"
        assert r.stderr == "some stderr"
        assert r.error_message == "TimeoutError: waiting for selector"
        assert r.video_path == "/tmp/video.webm"
        assert r.replay_path == "/tmp/trace.json"
        assert r.screenshots == ["/tmp/ss1.png", "/tmp/ss2.png"]

    def test_round_trip_empty_suite(self) -> None:
        suite = TestSuite(
            pr_ref="org/repo#99",
            framework=FrameworkType.UNKNOWN,
            generation_success=False,
            generation_error="No tests generated",
        )

        d = _suite_to_dict(suite)
        restored = _suite_from_dict(d)

        assert restored.id == suite.id
        assert restored.pr_ref == "org/repo#99"
        assert restored.framework == FrameworkType.UNKNOWN
        assert restored.generation_success is False
        assert restored.generation_error == "No tests generated"
        assert restored.results == []

    def test_datetime_fields_preserved(self) -> None:
        suite = _suite_with_results([TestStatus.PASS])
        original_executed_at = suite.results[0].executed_at

        d = _suite_to_dict(suite)
        restored = _suite_from_dict(d)

        restored_executed_at = restored.results[0].executed_at
        # datetime roundtrip via isoformat -> fromisoformat
        assert isinstance(restored_executed_at, datetime)
        # The microsecond precision may differ slightly due to ISO format,
        # so compare up to the second
        assert restored_executed_at.year == original_executed_at.year
        assert restored_executed_at.month == original_executed_at.month
        assert restored_executed_at.day == original_executed_at.day
        assert restored_executed_at.hour == original_executed_at.hour
        assert restored_executed_at.minute == original_executed_at.minute
        assert restored_executed_at.second == original_executed_at.second

    def test_round_trip_json_dumps_compatible(self) -> None:
        """The dict from _suite_to_dict should be JSON-serializable."""
        suite = _suite_with_results([TestStatus.PASS, TestStatus.ERROR])
        d = _suite_to_dict(suite)
        serialized = json.dumps(d)
        parsed = json.loads(serialized)
        restored = _suite_from_dict(parsed)
        assert restored.id == suite.id
        assert len(restored.results) == 2


# ===================================================================
# 7. Annotation Handling Eval
# ===================================================================


class TestAnnotationHandlingEval:
    """Test the difference between # and // comment handling for annotations."""

    def test_python_covers_annotation_parsed(self) -> None:
        raw = """```python
# tests/test_auth.py
# covers: src/auth.py:42
def test_login(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1
        assert cases[0].source_file == "src/auth.py"
        assert cases[0].diff_line_start == 42

    def test_typescript_covers_annotation_not_parsed(self) -> None:
        """_COVERS_RE only matches '#' comments, not '//' comments.
        TypeScript '// covers:' annotations are NOT parsed."""
        raw = """```typescript
// tests/api.test.ts
// covers: src/api.ts:10
describe("api", () => { it("works", () => {}); });
```
"""
        cases = _parse_test_cases(raw, FrameworkType.JEST)
        assert len(cases) == 1
        # // covers: is not matched by _COVERS_RE (which requires '#')
        assert cases[0].source_file == ""
        assert cases[0].diff_line_start == 0

    def test_python_confidence_annotation_parsed(self) -> None:
        raw = """```python
# tests/test_it.py
# confidence: high
def test_it(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1
        assert cases[0].confidence == Confidence.HIGH

    def test_typescript_confidence_annotation_not_parsed(self) -> None:
        """_CONFIDENCE_RE only matches '#' comments, not '//' comments.
        TypeScript '// confidence:' defaults to MEDIUM."""
        raw = """```typescript
// tests/api.test.ts
// confidence: high
describe("api", () => { it("works", () => {}); });
```
"""
        cases = _parse_test_cases(raw, FrameworkType.JEST)
        assert len(cases) == 1
        # // confidence: high is not matched by _CONFIDENCE_RE
        assert cases[0].confidence == Confidence.MEDIUM

    def test_python_confidence_low(self) -> None:
        raw = """```python
# tests/test_edge.py
# confidence: low
def test_edge(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert cases[0].confidence == Confidence.LOW

    def test_python_confidence_case_insensitive(self) -> None:
        raw = """```python
# tests/test_case.py
# confidence: HIGH
def test_case(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert cases[0].confidence == Confidence.HIGH

    def test_covers_with_deep_path(self) -> None:
        raw = """```python
# tests/test_deep.py
# covers: src/deeply/nested/module.py:999
def test_deep(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert cases[0].source_file == "src/deeply/nested/module.py"
        assert cases[0].diff_line_start == 999

    def test_both_annotations_in_one_block(self) -> None:
        raw = """```python
# tests/test_full.py
# confidence: low
# covers: lib/utils.py:7
def test_full(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1
        assert cases[0].confidence == Confidence.LOW
        assert cases[0].source_file == "lib/utils.py"
        assert cases[0].diff_line_start == 7
