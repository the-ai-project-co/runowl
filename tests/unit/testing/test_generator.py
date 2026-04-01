"""Tests for testing.generator — parsing logic (no Claude API calls)."""

from testing.generator import _extract_description, _infer_test_type, _parse_test_cases
from testing.models import FrameworkType, TestType


class TestParseTestCases:
    def test_parses_python_block(self) -> None:
        raw = """
Here are the generated tests:

```python
# tests/test_auth.py
# confidence: high
# covers: src/auth.py:42

def test_login_returns_token():
    assert True
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1
        assert cases[0].confidence.value == "high"
        assert cases[0].source_file == "src/auth.py"
        assert cases[0].diff_line_start == 42

    def test_parses_multiple_blocks(self) -> None:
        raw = """
```python
# tests/test_a.py
def test_a(): pass
```

```python
# tests/test_b.py
def test_b(): pass
```
"""
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 2

    def test_deduplicates_identical_blocks(self) -> None:
        block = "```python\ndef test_dupe(): pass\n```"
        raw = block + "\n\n" + block
        cases = _parse_test_cases(raw, FrameworkType.PYTEST)
        assert len(cases) == 1

    def test_empty_output_returns_empty(self) -> None:
        cases = _parse_test_cases("No code here.", FrameworkType.PYTEST)
        assert cases == []

    def test_typescript_block(self) -> None:
        raw = """
```typescript
// tests/auth.test.ts
describe("auth", () => { it("works", () => {}); });
```
"""
        cases = _parse_test_cases(raw, FrameworkType.JEST)
        assert len(cases) == 1


class TestInferTestType:
    def test_playwright_code_is_e2e(self) -> None:
        code = "await page.goto('/login')"
        assert _infer_test_type(code, FrameworkType.PLAYWRIGHT) == TestType.E2E

    def test_playwright_framework_forces_e2e(self) -> None:
        code = "def test_something(): pass"
        assert _infer_test_type(code, FrameworkType.PLAYWRIGHT) == TestType.E2E

    def test_httpx_is_integration(self) -> None:
        code = "import httpx\nclient.get('/api/users')"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.INTEGRATION

    def test_plain_pytest_is_unit(self) -> None:
        code = "def test_add(): assert 1 + 1 == 2"
        assert _infer_test_type(code, FrameworkType.PYTEST) == TestType.UNIT


class TestExtractDescription:
    def test_extracts_first_comment(self) -> None:
        code = "# Test that login works\ndef test_login(): pass"
        assert _extract_description(code) == "Test that login works"

    def test_skips_confidence_comment(self) -> None:
        code = "# confidence: high\n# Test the auth flow\ndef test_auth(): pass"
        assert _extract_description(code) == "Test the auth flow"

    def test_empty_code(self) -> None:
        assert _extract_description("") == ""
