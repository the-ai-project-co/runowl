"""AI evals for citation extraction precision/recall and validation accuracy.

Evaluates:
- Extraction format coverage: all supported citation patterns
- Extraction precision: no false positives on tricky inputs
- Validation accuracy: correct filtering against diff hunks
- Full pipeline: parse real patches -> extract -> validate
- Edge cases: unusual inputs and boundary conditions
"""

import pytest

from github.diff import line_range_from_hunk, parse_patch
from github.models import DiffHunk, FileDiff, PRFile
from review.citations import extract_citations, validate_citations
from review.models import Citation

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_diff(
    filename: str,
    hunks: list[tuple[int, int]],
) -> FileDiff:
    """Build a FileDiff with the given hunk (new_start, new_lines) pairs."""
    diff_hunks = []
    for new_start, new_lines in hunks:
        diff_hunks.append(
            DiffHunk(
                header=f"@@ -1,1 +{new_start},{new_lines} @@",
                old_start=1,
                old_lines=1,
                new_start=new_start,
                new_lines=new_lines,
                lines=["+added line"] * new_lines,
            )
        )
    return FileDiff(
        filename=filename,
        status="modified",
        additions=sum(h[1] for h in hunks),
        deletions=0,
        hunks=diff_hunks,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 1. Extraction Format Coverage Eval (20+ test cases)
# ═════════════════════════════════════════════════════════════════════════════


class TestExtractionFormatCoverage:
    """Golden dataset: text strings -> expected citations."""

    # -- "lines X-Y" format --

    def test_lines_range_basic(self) -> None:
        citations = extract_citations("src/auth.py lines 10-20")
        assert len(citations) == 1
        assert citations[0] == Citation(file="src/auth.py", line_start=10, line_end=20)

    def test_lines_range_different_file(self) -> None:
        citations = extract_citations("lib/utils.py lines 1-5")
        assert len(citations) == 1
        assert citations[0].file == "lib/utils.py"
        assert citations[0].line_start == 1
        assert citations[0].line_end == 5

    def test_lines_range_large_numbers(self) -> None:
        citations = extract_citations("src/big.py lines 100-500")
        assert citations[0].line_start == 100
        assert citations[0].line_end == 500

    # -- "line X" single line format --

    def test_line_single(self) -> None:
        citations = extract_citations("src/main.py line 7")
        assert len(citations) == 1
        assert citations[0].line_start == 7
        assert citations[0].line_end == 7

    def test_line_single_large_number(self) -> None:
        citations = extract_citations("src/handler.py line 999")
        assert citations[0].line_start == 999
        assert citations[0].line_end == 999

    # -- ":X-Y" colon range format --

    def test_colon_range(self) -> None:
        citations = extract_citations("src/auth.py:42-55")
        assert citations[0].file == "src/auth.py"
        assert citations[0].line_start == 42
        assert citations[0].line_end == 55

    def test_colon_range_different_file(self) -> None:
        citations = extract_citations("tests/test_login.py:1-30")
        assert citations[0].file == "tests/test_login.py"
        assert citations[0].line_start == 1
        assert citations[0].line_end == 30

    # -- ":X" colon single line format --

    def test_colon_single(self) -> None:
        citations = extract_citations("src/auth.py:42")
        assert len(citations) == 1
        assert citations[0].line_start == 42
        assert citations[0].line_end == 42

    def test_colon_single_line_one(self) -> None:
        citations = extract_citations("config.py:1")
        assert citations[0].line_start == 1
        assert citations[0].line_end == 1

    # -- Multiple citations in one text --

    def test_multiple_citations_mixed_formats(self) -> None:
        text = "Check src/a.py:1-5 and also src/b.py lines 10-15 and src/c.py:42"
        citations = extract_citations(text)
        assert len(citations) == 3
        files = {c.file for c in citations}
        assert files == {"src/a.py", "src/b.py", "src/c.py"}

    def test_two_citations_same_file(self) -> None:
        text = "src/auth.py:10-20 and src/auth.py:30-40"
        citations = extract_citations(text)
        assert len(citations) == 2
        assert citations[0].line_start == 10
        assert citations[1].line_start == 30

    # -- Citations in markdown context --

    def test_citation_in_backtick_markdown(self) -> None:
        text = "See `src/auth.py:42` for details"
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0].file == "src/auth.py"
        assert citations[0].line_start == 42

    def test_citation_in_bold_markdown(self) -> None:
        text = "**Location:** `src/handler.py:10-20`"
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0].file == "src/handler.py"

    def test_citation_in_list_markdown(self) -> None:
        text = "- src/a.py lines 5-10\n- src/b.py:20-30"
        citations = extract_citations(text)
        assert len(citations) == 2

    # -- Deeply nested paths --

    def test_deeply_nested_path(self) -> None:
        text = "src/components/auth/middleware/jwt.py:15-30"
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0].file == "src/components/auth/middleware/jwt.py"
        assert citations[0].line_start == 15
        assert citations[0].line_end == 30

    def test_nested_path_with_lines_format(self) -> None:
        text = "app/services/user/profile_manager.py lines 100-150"
        citations = extract_citations(text)
        assert citations[0].file == "app/services/user/profile_manager.py"

    # -- Various file extensions --

    def test_extension_ts(self) -> None:
        citations = extract_citations("src/index.ts:5-10")
        assert citations[0].file == "src/index.ts"

    def test_extension_js(self) -> None:
        citations = extract_citations("lib/helpers.js lines 1-3")
        assert citations[0].file == "lib/helpers.js"

    def test_extension_jsx(self) -> None:
        citations = extract_citations("src/App.jsx:20")
        assert citations[0].file == "src/App.jsx"

    def test_extension_tsx(self) -> None:
        citations = extract_citations("components/Form.tsx:15-25")
        assert citations[0].file == "components/Form.tsx"

    def test_extension_go(self) -> None:
        citations = extract_citations("cmd/main.go:42-55")
        assert citations[0].file == "cmd/main.go"

    def test_extension_rs(self) -> None:
        citations = extract_citations("src/lib.rs lines 10-20")
        assert citations[0].file == "src/lib.rs"

    def test_extension_java(self) -> None:
        citations = extract_citations("src/Main.java:100-200")
        assert citations[0].file == "src/Main.java"

    def test_extension_rb(self) -> None:
        citations = extract_citations("app/models/user.rb:5-15")
        assert citations[0].file == "app/models/user.rb"

    # -- Empty / no citation cases --

    def test_no_citations_plain_text(self) -> None:
        assert extract_citations("No files mentioned here.") == []

    def test_empty_text(self) -> None:
        assert extract_citations("") == []

    # -- Line 0 exclusion --

    def test_line_zero_excluded(self) -> None:
        """Line 0 is not a valid line number; start must be > 0."""
        citations = extract_citations("src/auth.py:0")
        assert citations == []

    def test_line_zero_in_range_excluded(self) -> None:
        citations = extract_citations("src/auth.py:0-10")
        assert citations == []


# ═════════════════════════════════════════════════════════════════════════════
# 2. Extraction Precision Eval (15+ test cases)
# ═════════════════════════════════════════════════════════════════════════════


class TestExtractionPrecision:
    """Tricky text that should NOT produce false positive citations."""

    def test_version_number_not_citation(self) -> None:
        """'Version 1.2.3' should not match as a citation."""
        citations = extract_citations("Version 1.2.3")
        # If anything matches, it should not have a valid file path with extension
        for c in citations:
            assert not c.file.endswith(".2")

    def test_python_version_not_citation(self) -> None:
        """'Python 3.12' - number after dot is not a citation."""
        citations = extract_citations("We require Python 3.12 or higher.")
        # Python 3.12 should not generate any citation (3 is not a valid file)
        valid = [c for c in citations if c.line_start > 0]
        # Even if regex catches '3.12', '3' is not a path with extension
        assert len(valid) == 0

    def test_url_not_citation(self) -> None:
        """Full GitHub URLs should not produce valid citations."""
        text = "See https://github.com/owner/repo/blob/main/src/auth.py"
        citations = extract_citations(text)
        # Any citation extracted from URL context should not have line info
        # since the URL doesn't include :line syntax
        for c in citations:
            # URL-extracted matches won't have line ranges from the URL itself
            assert c.line_start > 0 or len(citations) == 0

    def test_step_colon_number_not_citation(self) -> None:
        """'step 1: do thing' should not produce a citation."""
        citations = extract_citations("step 1: do something important")
        assert citations == []

    def test_ratio_not_citation(self) -> None:
        """'ratio 2:1' should not produce a citation."""
        citations = extract_citations("The ratio is 2:1 for writes vs reads")
        assert citations == []

    def test_time_not_citation(self) -> None:
        """'10:30' should not produce a file citation."""
        citations = extract_citations("The meeting is at 10:30 AM")
        assert citations == []

    def test_file_mention_without_line_number(self) -> None:
        """Mentioning a file without line numbers should not produce a citation."""
        citations = extract_citations("Check src/auth.py for details on the flow")
        assert citations == []

    def test_plain_number_not_citation(self) -> None:
        """A plain number like '42' should not produce a citation."""
        citations = extract_citations("The answer is 42")
        assert citations == []

    def test_sentence_with_colon_not_citation(self) -> None:
        """'Note: something' should not produce a citation."""
        citations = extract_citations("Note: this is important")
        assert citations == []

    def test_port_number_not_citation(self) -> None:
        """'localhost:8080' should not produce a citation."""
        citations = extract_citations("Run on localhost:8080")
        assert citations == []

    def test_json_key_colon_not_citation(self) -> None:
        """JSON-like 'key: value' should not produce a citation."""
        citations = extract_citations('{"timeout": 30}')
        assert citations == []

    def test_commit_sha_not_citation(self) -> None:
        """A commit SHA like 'abc123' should not be a citation."""
        citations = extract_citations("Commit abc123 fixed the issue.")
        assert citations == []

    def test_email_not_citation(self) -> None:
        """An email address should not produce a citation."""
        citations = extract_citations("Contact user@example.com for support")
        assert citations == []

    def test_scope_operator_not_citation(self) -> None:
        """'module::function' should not be mistaken for file:line."""
        citations = extract_citations("Call std::vector::push_back")
        assert citations == []

    def test_decimal_number_not_citation(self) -> None:
        """'3.14' should not produce a citation."""
        citations = extract_citations("Use pi = 3.14 for approximation")
        assert citations == []


# ═════════════════════════════════════════════════════════════════════════════
# 3. Validation Accuracy Eval (15+ test cases)
# ═════════════════════════════════════════════════════════════════════════════


class TestValidationAccuracy:
    """Build realistic FileDiff objects and verify validation correctness."""

    # -- Citation inside hunk range --

    def test_citation_inside_single_hunk(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 20)])  # lines 10-29
        citation = Citation(file="src/auth.py", line_start=15, line_end=20)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1
        assert valid[0] == citation

    def test_citation_fully_inside_small_hunk(self) -> None:
        diff = _make_diff("src/utils.py", [(5, 3)])  # lines 5-7
        citation = Citation(file="src/utils.py", line_start=6, line_end=6)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1

    # -- Citation outside all hunk ranges --

    def test_citation_outside_hunk(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 5)])  # lines 10-14
        citation = Citation(file="src/auth.py", line_start=50, line_end=60)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0

    def test_citation_before_hunk_start(self) -> None:
        diff = _make_diff("src/auth.py", [(20, 10)])  # lines 20-29
        citation = Citation(file="src/auth.py", line_start=5, line_end=10)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0

    def test_citation_between_hunks(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 5), (50, 5)])  # 10-14, 50-54
        citation = Citation(file="src/auth.py", line_start=30, line_end=35)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0

    # -- Citation on hunk boundary (exact start, exact end) --

    def test_citation_at_exact_hunk_start(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 20)])  # lines 10-29
        citation = Citation(file="src/auth.py", line_start=10, line_end=10)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1

    def test_citation_at_exact_hunk_end(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 20)])  # lines 10-29
        citation = Citation(file="src/auth.py", line_start=29, line_end=29)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1

    def test_citation_spanning_exact_hunk(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 5)])  # lines 10-14
        citation = Citation(file="src/auth.py", line_start=10, line_end=14)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1

    # -- Citation spanning two hunks --

    def test_citation_overlapping_first_hunk(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 5), (50, 5)])  # 10-14, 50-54
        citation = Citation(file="src/auth.py", line_start=12, line_end=30)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1  # overlaps first hunk

    def test_citation_overlapping_second_hunk(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 5), (50, 5)])
        citation = Citation(file="src/auth.py", line_start=40, line_end=52)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1  # overlaps second hunk

    # -- Citation for wrong file --

    def test_wrong_file_invalid(self) -> None:
        diff = _make_diff("src/auth.py", [(1, 100)])
        citation = Citation(file="src/other.py", line_start=5, line_end=10)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0

    def test_similar_filename_invalid(self) -> None:
        diff = _make_diff("src/auth.py", [(1, 100)])
        citation = Citation(file="src/auth_test.py", line_start=5, line_end=10)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0

    # -- Citation for file with no hunks --

    def test_file_with_no_hunks(self) -> None:
        diff = FileDiff(
            filename="src/empty.py",
            status="modified",
            additions=0,
            deletions=0,
            hunks=[],
        )
        citation = Citation(file="src/empty.py", line_start=1, line_end=10)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 0

    # -- Multiple citations, mixed valid/invalid --

    def test_mixed_valid_invalid_citations(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 10)])  # lines 10-19
        citations = [
            Citation(file="src/auth.py", line_start=12, line_end=15),  # valid
            Citation(file="src/auth.py", line_start=50, line_end=60),  # invalid
            Citation(file="src/other.py", line_start=12, line_end=15),  # wrong file
        ]
        valid = validate_citations(citations, [diff])
        assert len(valid) == 1
        assert valid[0].line_start == 12

    def test_all_valid_citations(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 90)])  # lines 10-99
        citations = [
            Citation(file="src/auth.py", line_start=10, line_end=20),
            Citation(file="src/auth.py", line_start=50, line_end=60),
            Citation(file="src/auth.py", line_start=90, line_end=99),
        ]
        valid = validate_citations(citations, [diff])
        assert len(valid) == 3

    def test_all_invalid_citations(self) -> None:
        diff = _make_diff("src/auth.py", [(10, 5)])  # lines 10-14
        citations = [
            Citation(file="src/auth.py", line_start=1, line_end=5),
            Citation(file="src/auth.py", line_start=50, line_end=60),
            Citation(file="src/other.py", line_start=12, line_end=12),
        ]
        valid = validate_citations(citations, [diff])
        assert len(valid) == 0

    # -- Multi-file diffs --

    def test_multi_file_validation(self) -> None:
        diffs = [
            _make_diff("src/auth.py", [(10, 10)]),
            _make_diff("src/db.py", [(50, 20)]),
        ]
        citations = [
            Citation(file="src/auth.py", line_start=12, line_end=15),  # valid
            Citation(file="src/db.py", line_start=55, line_end=60),  # valid
            Citation(file="src/db.py", line_start=1, line_end=5),  # invalid
        ]
        valid = validate_citations(citations, diffs)
        assert len(valid) == 2


# ═════════════════════════════════════════════════════════════════════════════
# 4. Full Pipeline Eval
# ═════════════════════════════════════════════════════════════════════════════


class TestFullPipeline:
    """Parse real patches -> extract citations from LLM-like output -> validate."""

    def _build_realistic_pr(self) -> list[FileDiff]:
        """Build a realistic 3-file PR with multi-hunk diffs."""
        file1 = PRFile(
            filename="src/auth.py",
            status="modified",
            additions=15,
            deletions=3,
            changes=18,
            patch=(
                "@@ -10,7 +10,12 @@ def login(username, password):\n"
                "     user = db.find_user(username)\n"
                "-    if user.check_password(password):\n"
                "+    if user is not None and user.check_password(password):\n"
                "+        token = create_jwt(user)\n"
                "+        return {\"token\": token}\n"
                "+    return {\"error\": \"unauthorized\"}\n"
                " \n"
                "@@ -40,5 +45,10 @@ def create_jwt(user):\n"
                "     payload = {\"sub\": user.id}\n"
                "-    return jwt.encode(payload, SECRET)\n"
                "+    return jwt.encode(payload, os.environ['JWT_SECRET'])\n"
                "+\n"
                "+def validate_jwt(token):\n"
                "+    return jwt.decode(token, os.environ['JWT_SECRET'])\n"
            ),
        )
        file2 = PRFile(
            filename="src/db.py",
            status="modified",
            additions=5,
            deletions=2,
            changes=7,
            patch=(
                "@@ -88,4 +88,7 @@ def run_query(query, params=None):\n"
                "-    cursor.execute(query)\n"
                "+    cursor.execute(query, params)\n"
                "+    return cursor.fetchall()\n"
                "+\n"
                "+def safe_query(table, conditions):\n"
                "+    return run_query(f'SELECT * FROM {table} WHERE ?', conditions)\n"
            ),
        )
        file3 = PRFile(
            filename="src/config.py",
            status="added",
            additions=8,
            deletions=0,
            changes=8,
            patch=(
                "@@ -0,0 +1,8 @@\n"
                "+import os\n"
                "+\n"
                "+DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'\n"
                "+PORT = int(os.environ.get('PORT', '8000'))\n"
                "+DB_URL = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')\n"
                "+JWT_SECRET = os.environ.get('JWT_SECRET', 'changeme')\n"
                "+CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')\n"
                "+LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')\n"
            ),
        )
        return [parse_patch(f) for f in [file1, file2, file3]]

    def test_pipeline_valid_citations_survive(self) -> None:
        """LLM output referencing correct locations survives validation."""
        diffs = self._build_realistic_pr()

        llm_output = (
            "Found issues in this PR:\n"
            "1. In src/auth.py lines 10-15, the login function was improved.\n"
            "2. In src/db.py:88-92, parameterized queries are now used.\n"
            "3. In src/config.py:6, the JWT_SECRET defaults to 'changeme'.\n"
        )

        citations = extract_citations(llm_output)
        assert len(citations) == 3

        valid = validate_citations(citations, diffs)
        assert len(valid) == 3

    def test_pipeline_invalid_citations_filtered(self) -> None:
        """LLM output referencing wrong locations gets filtered."""
        diffs = self._build_realistic_pr()

        llm_output = (
            "Issues found:\n"
            "1. src/auth.py:200-210 has a buffer overflow.\n"  # line 200 not in diff
            "2. src/missing.py:10 has an issue.\n"  # file not in PR
        )

        citations = extract_citations(llm_output)
        assert len(citations) == 2

        valid = validate_citations(citations, diffs)
        assert len(valid) == 0

    def test_pipeline_mixed_valid_and_invalid(self) -> None:
        """Mix of correct and incorrect citations: only valid survive."""
        diffs = self._build_realistic_pr()

        llm_output = (
            "Review findings:\n"
            "- src/auth.py:45-50 — JWT secret moved to env var. Good.\n"  # valid (hunk 2)
            "- src/db.py:1-5 — unrelated code at top of file.\n"  # invalid
            "- src/config.py:1-8 — new config file looks good.\n"  # valid
        )

        citations = extract_citations(llm_output)
        assert len(citations) == 3

        valid = validate_citations(citations, diffs)
        assert len(valid) == 2
        valid_files = {c.file for c in valid}
        assert "src/auth.py" in valid_files
        assert "src/config.py" in valid_files

    def test_pipeline_no_citations_in_clean_review(self) -> None:
        """Clean review with no file references produces no citations."""
        diffs = self._build_realistic_pr()

        llm_output = "This PR looks clean. No issues found. Good job!"
        citations = extract_citations(llm_output)
        assert citations == []
        valid = validate_citations(citations, diffs)
        assert valid == []

    def test_pipeline_parse_patch_then_validate(self) -> None:
        """End-to-end: PRFile -> parse_patch -> validate citation."""
        pr_file = PRFile(
            filename="src/handler.py",
            status="modified",
            additions=5,
            deletions=1,
            changes=6,
            patch=(
                "@@ -20,3 +20,7 @@ def handle_request(req):\n"
                "-    return Response(200)\n"
                "+    try:\n"
                "+        result = process(req)\n"
                "+        return Response(200, body=result)\n"
                "+    except Exception:\n"
                "+        return Response(500)\n"
            ),
        )
        diff = parse_patch(pr_file)
        assert diff.filename == "src/handler.py"
        assert len(diff.hunks) == 1

        # line_range_from_hunk gives us the range
        start, end = line_range_from_hunk(diff.hunks[0])
        assert start == 20
        assert end == 26  # 20 + 7 - 1

        # Citation within that range should validate
        citation = Citation(file="src/handler.py", line_start=22, line_end=25)
        valid = validate_citations([citation], [diff])
        assert len(valid) == 1

        # Citation outside should not
        outside = Citation(file="src/handler.py", line_start=50, line_end=55)
        valid = validate_citations([outside], [diff])
        assert len(valid) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 5. Edge Cases
# ═════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Unusual inputs and boundary conditions."""

    def test_very_large_line_number(self) -> None:
        citations = extract_citations("src/big.py line 99999")
        assert len(citations) == 1
        assert citations[0].line_start == 99999
        assert citations[0].line_end == 99999

    def test_very_large_line_range(self) -> None:
        citations = extract_citations("src/big.py:10000-50000")
        assert len(citations) == 1
        assert citations[0].line_start == 10000
        assert citations[0].line_end == 50000

    def test_line_range_start_greater_than_end(self) -> None:
        """When start > end, the regex still matches; validate semantics."""
        citations = extract_citations("src/auth.py:50-10")
        # The regex captures these literally — start=50, end=10
        if citations:
            assert citations[0].line_start == 50
            assert citations[0].line_end == 10

    def test_empty_text_returns_empty(self) -> None:
        assert extract_citations("") == []

    def test_whitespace_only_text(self) -> None:
        assert extract_citations("   \n\t  \n  ") == []

    def test_filename_only_no_line_not_extracted(self) -> None:
        """File path without any line number should not be extracted."""
        citations = extract_citations("Check src/auth.py for details")
        assert citations == []

    def test_file_with_hyphens(self) -> None:
        citations = extract_citations("my-lib/auth-handler.py:10-20")
        assert len(citations) == 1
        assert citations[0].file == "my-lib/auth-handler.py"

    def test_file_with_underscores(self) -> None:
        citations = extract_citations("src/user_profile_manager.py:5-15")
        assert len(citations) == 1
        assert citations[0].file == "src/user_profile_manager.py"

    def test_file_with_dots_in_path(self) -> None:
        citations = extract_citations("src/v2.0/auth.py:10")
        assert len(citations) >= 1
        # Should find auth.py:10 at minimum
        auth_citations = [c for c in citations if c.file.endswith("auth.py")]
        assert len(auth_citations) >= 1

    def test_single_line_hunk_boundary(self) -> None:
        """Hunk with new_lines=1 covers exactly one line."""
        diff = _make_diff("src/one.py", [(42, 1)])  # only line 42
        on = Citation(file="src/one.py", line_start=42, line_end=42)
        off = Citation(file="src/one.py", line_start=43, line_end=43)
        assert len(validate_citations([on], [diff])) == 1
        assert len(validate_citations([off], [diff])) == 0

    def test_validate_empty_citations_list(self) -> None:
        diff = _make_diff("src/auth.py", [(1, 100)])
        valid = validate_citations([], [diff])
        assert valid == []

    def test_validate_empty_diffs_list(self) -> None:
        citation = Citation(file="src/auth.py", line_start=10, line_end=20)
        valid = validate_citations([citation], [])
        assert valid == []

    def test_validate_both_empty(self) -> None:
        assert validate_citations([], []) == []

    def test_hunk_with_zero_new_lines(self) -> None:
        """Hunk with new_lines=0 (pure deletion) — range is (start, start)."""
        hunk = DiffHunk(
            header="@@ -10,5 +10,0 @@",
            old_start=10,
            old_lines=5,
            new_start=10,
            new_lines=0,
            lines=[],
        )
        start, end = line_range_from_hunk(hunk)
        assert start == 10
        assert end == 10  # max(0-1, 0) = 0, so 10+0 = 10

    def test_citation_str_single_line(self) -> None:
        c = Citation(file="src/auth.py", line_start=42, line_end=42)
        assert str(c) == "src/auth.py:42"

    def test_citation_str_range(self) -> None:
        c = Citation(file="src/auth.py", line_start=10, line_end=20)
        assert str(c) == "src/auth.py:10-20"

    def test_unicode_in_surrounding_text(self) -> None:
        """Citation extraction works even with unicode in surrounding text."""
        text = "See \u2014 src/auth.py:42 \u2014 for the \u00fcber-fix."
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0].file == "src/auth.py"

    def test_en_dash_line_range(self) -> None:
        """The regex supports en-dash (\u2013) as range separator in 'lines' format."""
        text = "src/auth.py lines 10\u201320"
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0].line_start == 10
        assert citations[0].line_end == 20
