"""Tests for finding parser and citation extractor."""

from review.citations import extract_citations, validate_citations
from review.models import Citation, FindingType, Severity
from review.parser import parse_findings

# ── Citation extraction ───────────────────────────────────────────────────────


class TestExtractCitations:
    def test_file_lines_format(self) -> None:
        text = "See src/auth.py lines 10-20 for the issue."
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0].file == "src/auth.py"
        assert citations[0].line_start == 10
        assert citations[0].line_end == 20

    def test_file_colon_format(self) -> None:
        citations = extract_citations("src/auth.py:42-55")
        assert citations[0].line_start == 42
        assert citations[0].line_end == 55

    def test_single_line(self) -> None:
        citations = extract_citations("src/main.py line 7")
        assert citations[0].line_start == 7
        assert citations[0].line_end == 7

    def test_multiple_citations(self) -> None:
        text = "src/a.py:1-5 and src/b.py lines 10-15"
        citations = extract_citations(text)
        assert len(citations) == 2

    def test_no_citations(self) -> None:
        assert extract_citations("No files mentioned here.") == []


class TestValidateCitations:
    def _make_diff(self, filename: str, hunk_start: int, hunk_lines: int):
        from github.models import DiffHunk, FileDiff

        return FileDiff(
            filename=filename,
            status="modified",
            additions=hunk_lines,
            deletions=0,
            hunks=[
                DiffHunk(
                    header=f"@@ -{hunk_start},{hunk_lines} +{hunk_start},{hunk_lines} @@",
                    old_start=hunk_start,
                    old_lines=hunk_lines,
                    new_start=hunk_start,
                    new_lines=hunk_lines,
                    lines=[],
                )
            ],
        )

    def test_citation_within_hunk_valid(self) -> None:
        diff = self._make_diff("src/auth.py", hunk_start=10, hunk_lines=20)
        citation = Citation(file="src/auth.py", line_start=12, line_end=15)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1

    def test_citation_outside_hunk_invalid(self) -> None:
        diff = self._make_diff("src/auth.py", hunk_start=10, hunk_lines=5)
        citation = Citation(file="src/auth.py", line_start=100, line_end=110)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0

    def test_wrong_file_invalid(self) -> None:
        diff = self._make_diff("src/auth.py", hunk_start=1, hunk_lines=50)
        citation = Citation(file="src/other.py", line_start=5, line_end=10)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0


# ── Finding parser ─────────────────────────────────────────────────────────────


SAMPLE_OUTPUT = """
[P0] bug: Unhandled None dereference in login handler
File: src/auth.py lines 42-44
Description: The user object is accessed without checking for None, causing a crash when the user is not found.
Fix: Add a None check before accessing user.id.

[P1] security: SQL query built with string concatenation
File: src/db.py:88-90
Description: User input is concatenated directly into a SQL query, enabling injection attacks.
Fix: Use parameterized queries or an ORM.

[P2] investigation: Unusual branching logic in token validation
File: src/tokens.py lines 15-20
Description: The token expiry check uses a non-standard comparison that may allow expired tokens.

[P3] informational: Variable name is ambiguous
File: src/utils.py:7
Description: The variable `d` should be renamed to something descriptive.
"""


class TestParseFindings:
    def test_parses_four_findings(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert len(findings) == 4

    def test_p0_finding_severity(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[0].severity == Severity.P0

    def test_p0_finding_type(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[0].type == FindingType.BUG

    def test_p1_security_type(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[1].type == FindingType.SECURITY

    def test_p2_investigation_type(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[2].type == FindingType.INVESTIGATION

    def test_p3_informational_type(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[3].type == FindingType.INFORMATIONAL

    def test_fix_present_for_p0(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        p0 = findings[0]
        assert p0.fix is not None
        assert "None check" in p0.fix

    def test_fix_present_for_p1(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[1].fix is not None

    def test_fix_absent_for_p3(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        p3 = findings[3]
        assert p3.fix is None

    def test_citation_extracted_for_p0(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        c = findings[0].citation
        assert c.file == "src/auth.py"
        assert c.line_start == 42
        assert c.line_end == 44

    def test_sorted_by_severity(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        severities = [f.severity for f in findings]
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert severities == sorted(severities, key=lambda s: order[s])

    def test_empty_output_returns_empty(self) -> None:
        assert parse_findings("") == []

    def test_no_findings_in_text(self) -> None:
        assert parse_findings("This PR looks good. No issues found.") == []

    def test_blocks_merge_p0_p1(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[0].blocks_merge is True
        assert findings[1].blocks_merge is True

    def test_does_not_block_merge_p2_p3(self) -> None:
        findings = parse_findings(SAMPLE_OUTPUT)
        assert findings[2].blocks_merge is False
        assert findings[3].blocks_merge is False
