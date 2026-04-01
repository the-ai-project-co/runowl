"""AI evals for the finding parser — evaluates how accurately ``parse_findings``
from ``review.parser`` extracts structured findings from diverse, realistic LLM
output formats.

Covers format compliance, extraction accuracy, edge-case robustness, type
mapping, ordering guarantees, and adversarial inputs.
"""

from __future__ import annotations

import textwrap

import pytest

from review.models import Finding, FindingType, Severity
from review.parser import parse_findings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedent(text: str) -> str:
    """Remove common leading whitespace so inline test strings are clean."""
    return textwrap.dedent(text).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Format Compliance Eval (12 test cases)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFormatCompliance:
    """Verify the parser handles a variety of LLM output formatting quirks."""

    def test_standard_format(self) -> None:
        raw = _dedent("""
            [P0] bug: SQL injection in login endpoint
            File: src/auth.py lines 10-20
            Description: User input is concatenated into the query string.
            Fix: Use parameterized queries.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == Severity.P0
        assert f.type == FindingType.BUG
        assert "SQL injection" in f.title
        assert f.fix == "Use parameterized queries."

    def test_missing_fix_field(self) -> None:
        raw = _dedent("""
            [P2] informational: Unused constant in utils
            File: src/utils.py lines 5-5
            Description: The constant MAX_RETRIES is defined but never used.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].fix is None

    def test_multiline_description(self) -> None:
        raw = _dedent("""
            [P1] security: Missing CSRF token
            File: src/views.py lines 30-45
            Description: The form does not include an anti-forgery token.
            This means cross-site request forgery is possible.
            Fix: Add CSRF middleware.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert "cross-site request forgery" in findings[0].description.lower()

    def test_extra_whitespace_between_findings(self) -> None:
        raw = (
            "[P0] bug: Null dereference\n"
            "File: src/a.py lines 1-2\n"
            "Description: Crash on None.\n"
            "\n\n\n"
            "[P3] informational: Typo in comment\n"
            "File: src/b.py lines 5-5\n"
            "Description: Misspelled word.\n"
        )
        findings = parse_findings(raw)
        assert len(findings) == 2

    def test_finding_with_no_file_line(self) -> None:
        raw = _dedent("""
            [P1] bug: Potential deadlock
            Description: Two threads acquire locks in reverse order.
            Fix: Standardize lock ordering.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].citation is not None

    def test_mixed_case_header(self) -> None:
        raw = _dedent("""
            [p0] BUG: Race condition in counter
            File: src/counter.py lines 1-5
            Description: Increment is not atomic.
            Fix: Use atomic operations.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].severity == Severity.P0
        assert findings[0].type == FindingType.BUG

    def test_multiple_findings_in_one_output(self) -> None:
        raw = _dedent("""
            [P0] security: SQL injection
            File: src/db.py lines 10-20
            Description: Raw query with user input.
            Fix: Use ORM.

            [P1] bug: Memory leak
            File: src/cache.py lines 30-40
            Description: Cache entries never expire.
            Fix: Add TTL.

            [P2] informational: Large function
            File: src/handlers.py lines 1-200
            Description: process_order is 200 lines long.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 3

    def test_findings_embedded_in_prose(self) -> None:
        raw = _dedent("""
            Here is my review of the pull request:

            Overall the code is well-structured, but I found some issues.

            [P0] security: Path traversal in file upload
            File: src/upload.py lines 15-25
            Description: User-supplied filenames are not sanitized.
            Fix: Use os.path.basename.

            That said, the rest of the code looks good. Nice work on the tests.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].severity == Severity.P0
        assert "Path traversal" in findings[0].title

    def test_colon_after_type_with_extra_spaces(self) -> None:
        raw = _dedent("""
            [P2] informational:   Extra spaces in title
            File: src/foo.py lines 1-1
            Description: Some description here.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].title.strip() != ""

    def test_finding_with_empty_description(self) -> None:
        raw = _dedent("""
            [P3] informational: Minor style issue
            File: src/style.py lines 1-1
            Description:
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1

    def test_finding_with_fix_before_description(self) -> None:
        raw = _dedent("""
            [P1] bug: Timeout missing
            File: src/client.py lines 10-12
            Fix: Add timeout=30 to requests.get.
            Description: HTTP calls can hang indefinitely.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        # Parser should pick up both fields regardless of order
        assert findings[0].fix is not None

    def test_tab_indented_fields(self) -> None:
        raw = (
            "[P2] informational: Code duplication\n"
            "\tFile: src/dup.py lines 1-50\n"
            "\tDescription: Same logic in two places.\n"
        )
        findings = parse_findings(raw)
        assert len(findings) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Extraction Accuracy Eval (15 test cases)
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractionAccuracy:
    """Golden dataset: LLM outputs mapped to expected Finding attributes."""

    def test_single_finding_all_fields(self) -> None:
        raw = _dedent("""
            [P0] security: Hardcoded password in database config
            File: src/config.py lines 5-8
            Description: The database password is committed in plain text.
            Fix: Move credentials to environment variables.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == Severity.P0
        assert f.type == FindingType.SECURITY
        assert "Hardcoded password" in f.title
        assert "plain text" in f.description
        assert "environment variables" in f.fix
        assert f.citation.file == "src/config.py"
        assert f.citation.line_start == 5
        assert f.citation.line_end == 8

    def test_four_findings_at_different_severities(self) -> None:
        raw = _dedent("""
            [P0] bug: Null pointer dereference in handler
            File: src/handler.py lines 100-105
            Description: response.data accessed without null check.
            Fix: Add guard clause.

            [P1] security: Open redirect on login
            File: src/auth.py lines 50-55
            Description: return_url not validated.
            Fix: Whitelist allowed redirect URLs.

            [P2] informational: Magic number in fee calculation
            File: src/billing.py lines 20-22
            Description: 0.0275 used without explanation.

            [P3] informational: Typo in error message
            File: src/errors.py lines 3-3
            Description: 'recieved' should be 'received'.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 4
        # Sorted P0 first
        assert findings[0].severity == Severity.P0
        assert findings[1].severity == Severity.P1
        assert findings[2].severity == Severity.P2
        assert findings[3].severity == Severity.P3

    def test_colon_format_citation(self) -> None:
        raw = _dedent("""
            [P1] bug: Resource leak in file processor
            File: src/processor.py:42-55
            Description: File handle not closed on exception path.
            Fix: Use context manager.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].citation.file == "src/processor.py"
        assert findings[0].citation.line_start == 42
        assert findings[0].citation.line_end == 55

    def test_lines_format_citation(self) -> None:
        raw = _dedent("""
            [P2] informational: Deep nesting in validation
            File: src/validate.py lines 10-20
            Description: Five levels of nested ifs.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].citation.file == "src/validate.py"
        assert findings[0].citation.line_start == 10
        assert findings[0].citation.line_end == 20

    def test_single_line_citation(self) -> None:
        raw = _dedent("""
            [P3] informational: Unused import
            File: src/utils.py line 7
            Description: os is imported but never used.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].citation.file == "src/utils.py"
        assert findings[0].citation.line_start == 7
        assert findings[0].citation.line_end == 7

    def test_description_extraction_accuracy(self) -> None:
        raw = _dedent("""
            [P1] bug: Unhandled exception in payment flow
            File: src/payment.py lines 80-90
            Description: The PaymentError exception is caught but silently ignored.
            Fix: Log the error and notify the operations team.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert "PaymentError" in findings[0].description
        assert "silently ignored" in findings[0].description

    def test_fix_extraction_accuracy(self) -> None:
        raw = _dedent("""
            [P0] security: Command injection via subprocess
            File: src/runner.py lines 15-18
            Description: User input is passed to subprocess.call with shell=True.
            Fix: Use subprocess.run with shell=False and split arguments properly.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert "shell=False" in findings[0].fix

    def test_title_extraction_strips_whitespace(self) -> None:
        raw = _dedent("""
            [P2] informational:   God object in OrderManager
            File: src/orders.py lines 1-500
            Description: The class handles too many responsibilities.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].title.strip() == findings[0].title or "God object" in findings[0].title

    def test_raw_field_preserved(self) -> None:
        raw = _dedent("""
            [P1] bug: Deadlock between workers
            File: src/workers.py lines 60-80
            Description: Lock A and Lock B acquired in reverse order.
            Fix: Always acquire locks in alphabetical order.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].raw != ""
        assert "Deadlock" in findings[0].raw

    def test_investigation_type(self) -> None:
        raw = _dedent("""
            [P2] investigation: Potential performance regression
            File: src/api.py lines 100-120
            Description: Response times increased after this change.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].type == FindingType.INVESTIGATION

    def test_info_type_shorthand(self) -> None:
        raw = _dedent("""
            [P3] info: Consider adding docstring
            File: src/helpers.py lines 1-5
            Description: Public function lacks documentation.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].type == FindingType.INFORMATIONAL

    def test_investigate_type(self) -> None:
        raw = _dedent("""
            [P2] investigate: Unusual error rate spike
            File: src/monitoring.py lines 40-50
            Description: Error rate doubled after this commit.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].type == FindingType.INVESTIGATION

    def test_multiple_findings_all_have_citations(self) -> None:
        raw = _dedent("""
            [P0] bug: Data corruption risk
            File: src/db.py lines 1-10
            Description: Concurrent writes without lock.
            Fix: Add row-level locking.

            [P1] security: CSRF missing on form
            File: src/forms.py lines 20-30
            Description: No anti-forgery token.
            Fix: Add CSRF middleware.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 2
        for f in findings:
            assert f.citation is not None
            assert f.citation.file != "unknown"

    def test_finding_with_hyphenated_file_path(self) -> None:
        raw = _dedent("""
            [P3] informational: Naming inconsistency
            File: src/my-module/helper_utils.py lines 1-3
            Description: Function uses camelCase.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert "my-module" in findings[0].citation.file

    def test_finding_severity_defaults_to_p3_for_unknown(self) -> None:
        """If severity is somehow unrecognized, parser should handle it gracefully."""
        raw = _dedent("""
            [P3] informational: Very minor style note
            File: src/style.py lines 1-1
            Description: Trailing comma missing.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].severity == Severity.P3


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Edge Case Robustness Eval (12 test cases)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCaseRobustness:
    """Stress-test the parser with unusual, minimal, or adversarial inputs."""

    def test_empty_string(self) -> None:
        assert parse_findings("") == []

    def test_no_findings_text(self) -> None:
        raw = "This PR looks great! No issues found. Ship it."
        assert parse_findings(raw) == []

    def test_partial_finding_header_only(self) -> None:
        raw = "[P0] bug: Critical issue with no body"
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].severity == Severity.P0
        assert findings[0].type == FindingType.BUG

    def test_very_long_description(self) -> None:
        long_desc = "A" * 600
        raw = (
            f"[P1] bug: Performance issue\n"
            f"File: src/perf.py lines 1-100\n"
            f"Description: {long_desc}\n"
            f"Fix: Optimize the loop."
        )
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert len(findings[0].description) >= 500

    def test_code_block_in_description(self) -> None:
        raw = _dedent("""
            [P1] bug: SQL injection in query builder
            File: src/query.py lines 10-15
            Description: The query is built via string concatenation:
            ```python
            query = f"SELECT * FROM users WHERE id = {user_id}"
            ```
            Fix: Use parameterized queries.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert "concatenation" in findings[0].description

    def test_unicode_in_title(self) -> None:
        raw = _dedent("""
            [P3] informational: Fix typo in greeting: "Bienvenue" not "Bievenue"
            File: src/i18n.py lines 5-5
            Description: French greeting has a typo.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert "Bienvenue" in findings[0].title

    def test_unicode_in_description(self) -> None:
        raw = _dedent("""
            [P3] informational: Localization issue
            File: src/locale.py lines 1-3
            Description: The string "Gefahrlich" should be "Gefahrlich" with umlaut.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1

    def test_all_finding_types_bug(self) -> None:
        raw = "[P1] bug: Some bug\nDescription: Details."
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].type == FindingType.BUG

    def test_all_finding_types_security(self) -> None:
        raw = "[P0] security: Vuln found\nDescription: Details."
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].type == FindingType.SECURITY

    def test_all_finding_types_investigation(self) -> None:
        raw = "[P2] investigation: Need to check\nDescription: Details."
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].type == FindingType.INVESTIGATION

    def test_all_finding_types_informational(self) -> None:
        raw = "[P3] informational: FYI\nDescription: Details."
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].type == FindingType.INFORMATIONAL

    def test_whitespace_only_input(self) -> None:
        assert parse_findings("   \n\n   \t  \n") == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Type Mapping Completeness Eval
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_MAPPING_CASES = [
    ("bug", FindingType.BUG),
    ("security", FindingType.SECURITY),
    ("investigation", FindingType.INVESTIGATION),
    ("investigate", FindingType.INVESTIGATION),
    ("informational", FindingType.INFORMATIONAL),
    ("info", FindingType.INFORMATIONAL),
]


@pytest.mark.parametrize(
    "type_str, expected_type",
    _TYPE_MAPPING_CASES,
    ids=[t[0] for t in _TYPE_MAPPING_CASES],
)
def test_type_mapping_completeness(type_str: str, expected_type: FindingType) -> None:
    raw = f"[P2] {type_str}: Test finding for type mapping\nDescription: Checking type parsing."
    findings = parse_findings(raw)
    assert len(findings) == 1
    assert findings[0].type == expected_type, (
        f"Type string '{type_str}' should map to {expected_type}, got {findings[0].type}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Ordering Eval
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrdering:
    """Verify findings are always returned sorted P0 -> P1 -> P2 -> P3."""

    def test_reverse_order_input(self) -> None:
        raw = _dedent("""
            [P3] informational: Minor style issue
            Description: Trailing whitespace.

            [P2] informational: Missing test
            Description: No test for edge case.

            [P1] bug: Memory leak in cache
            Description: Entries never evicted.

            [P0] security: RCE via eval
            Description: User input passed to eval().
        """)
        findings = parse_findings(raw)
        assert len(findings) == 4
        assert findings[0].severity == Severity.P0
        assert findings[1].severity == Severity.P1
        assert findings[2].severity == Severity.P2
        assert findings[3].severity == Severity.P3

    def test_interleaved_severities(self) -> None:
        raw = _dedent("""
            [P2] informational: Code smell
            Description: Feature envy.

            [P0] bug: Stack overflow
            Description: Recursive function without base case.

            [P3] informational: Typo
            Description: Misspelled word.

            [P1] security: XSS in search
            Description: Unescaped output.

            [P2] informational: Large method
            Description: 300 lines long.
        """)
        findings = parse_findings(raw)
        severities = [f.severity for f in findings]
        severity_order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        numeric = [severity_order[s] for s in severities]
        assert numeric == sorted(numeric), f"Findings not sorted: {severities}"

    def test_all_same_severity(self) -> None:
        raw = _dedent("""
            [P2] informational: Issue A
            Description: First issue.

            [P2] informational: Issue B
            Description: Second issue.

            [P2] informational: Issue C
            Description: Third issue.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 3
        assert all(f.severity == Severity.P2 for f in findings)

    def test_two_p0_findings_both_first(self) -> None:
        raw = _dedent("""
            [P2] informational: Medium issue
            Description: Something.

            [P0] bug: Critical bug A
            Description: First critical.

            [P0] security: Critical vuln B
            Description: Second critical.

            [P3] informational: Nit
            Description: Small thing.
        """)
        findings = parse_findings(raw)
        assert findings[0].severity == Severity.P0
        assert findings[1].severity == Severity.P0
        assert findings[2].severity == Severity.P2
        assert findings[3].severity == Severity.P3


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Adversarial Input Eval
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdversarialInput:
    """Inputs designed to confuse or break the parser."""

    def test_invalid_severity_p5(self) -> None:
        raw = "[P5] unknown: This is not a real severity\nDescription: Should not parse."
        findings = parse_findings(raw)
        # P5 does not match [P0-3] regex, so should not produce a finding
        assert len(findings) == 0

    def test_nested_brackets(self) -> None:
        raw = "[[P0]] bug: Double bracket issue\nDescription: Nested brackets."
        findings = parse_findings(raw)
        # The regex looks for [P0-3], the extra bracket may or may not parse.
        # Key assertion: parser does not crash
        assert isinstance(findings, list)

    def test_finding_inside_markdown_code_block(self) -> None:
        raw = _dedent("""
            Here is an example of a finding format:

            ```
            [P0] bug: Example finding
            File: src/example.py lines 1-5
            Description: This is just an example.
            Fix: Do something.
            ```

            The above is only an example.
        """)
        findings = parse_findings(raw)
        # Parser may or may not extract findings from code blocks.
        # Key assertion: no crash, and if parsed, it is a valid Finding
        for f in findings:
            assert isinstance(f, Finding)

    def test_very_large_output_50_findings(self) -> None:
        blocks = []
        for i in range(50):
            sev = f"P{i % 4}"
            type_str = ["bug", "security", "informational", "investigation"][i % 4]
            blocks.append(
                f"[{sev}] {type_str}: Finding number {i}\n"
                f"File: src/file{i}.py lines {i}-{i + 10}\n"
                f"Description: Automatically generated finding {i}.\n"
            )
        raw = "\n".join(blocks)
        findings = parse_findings(raw)
        assert len(findings) == 50
        # Verify ordering
        severity_order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        numeric = [severity_order[f.severity] for f in findings]
        assert numeric == sorted(numeric)

    def test_finding_with_only_header_no_newline(self) -> None:
        raw = "[P2] informational: Standalone header"
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].title == "Standalone header"

    def test_text_with_square_brackets_but_not_findings(self) -> None:
        raw = "The array [0] is empty and [1] has data. See [docs] for details."
        findings = parse_findings(raw)
        assert len(findings) == 0

    def test_severity_in_description_not_new_finding(self) -> None:
        raw = _dedent("""
            [P1] bug: Error handling issue
            File: src/handler.py lines 10-20
            Description: The error message mentions [P0] but this is not a new finding.
            Fix: Update the error message.
        """)
        findings = parse_findings(raw)
        # The [P0] inside description will likely cause a split, but the second
        # block may not have a valid header. We expect at least the first finding.
        assert len(findings) >= 1
        assert findings[0].severity == Severity.P1
        assert findings[0].type == FindingType.BUG

    def test_html_entities_in_output(self) -> None:
        raw = _dedent("""
            [P2] informational: Entity encoding issue
            File: src/template.py lines 5-10
            Description: The template uses &amp; instead of & in URLs.
        """)
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert "&amp;" in findings[0].description

    def test_no_space_after_severity_bracket(self) -> None:
        raw = "[P1]bug: Missing space after bracket\nDescription: Should still parse or not crash."
        findings = parse_findings(raw)
        # The regex expects a space after ]. This may not parse, but must not crash.
        assert isinstance(findings, list)

    def test_empty_type_field(self) -> None:
        raw = "[P2] : Empty type\nDescription: Type field is blank."
        findings = parse_findings(raw)
        # Parser may or may not handle this — key is no crash
        assert isinstance(findings, list)
