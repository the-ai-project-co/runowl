"""AI evals for prompt template quality, context building, and format consistency."""

from __future__ import annotations

import re

import pytest

from reasoning.prompts import (
    SYSTEM_PROMPT,
    REVIEW_USER_PROMPT,
    QA_USER_PROMPT,
    CONTEXT_WINDOW_DIFF_LIMIT,
    REPL_DIFF_LIMIT,
)
from reasoning.context import build_pr_summary, build_diff_context
from github.models import PRMetadata, PRFile, DiffHunk, FileDiff, PRCommit
from review.parser import parse_findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata(
    number: int = 42,
    title: str = "Add JWT authentication",
    body: str | None = "Implements token-based auth for API endpoints.",
    author: str = "alice",
    base_branch: str = "main",
    head_branch: str = "feat/auth",
    n_files: int = 2,
    additions: int = 30,
    deletions: int = 5,
) -> PRMetadata:
    files = [
        PRFile(
            filename=f"src/file_{i}.py",
            status="modified",
            additions=additions // max(n_files, 1),
            deletions=deletions // max(n_files, 1),
            changes=(additions + deletions) // max(n_files, 1),
            patch="@@ -1,3 +1,5 @@\n line1\n+added\n line3",
        )
        for i in range(n_files)
    ]
    return PRMetadata(
        number=number,
        title=title,
        body=body,
        author=author,
        base_branch=base_branch,
        head_branch=head_branch,
        head_sha="abc123",
        base_sha="def456",
        state="open",
        commits=[PRCommit(sha="abc123", message="add auth", author=author)],
        files=files,
        additions=additions,
        deletions=deletions,
        changed_files=n_files,
    )


def _make_diff(
    filename: str = "src/auth.py",
    status: str = "modified",
    additions: int = 3,
    deletions: int = 1,
    hunk_header: str = "@@ -10,5 +10,7 @@ def authenticate():",
    lines: list[str] | None = None,
) -> FileDiff:
    if lines is None:
        lines = [
            " def authenticate():",
            "+    token = get_token()",
            "+    if not token:",
            "     return True",
        ]
    return FileDiff(
        filename=filename,
        status=status,
        additions=additions,
        deletions=deletions,
        hunks=[
            DiffHunk(
                header=hunk_header,
                old_start=10,
                old_lines=5,
                new_start=10,
                new_lines=7,
                lines=lines,
            )
        ],
    )


# ===========================================================================
# 1. Prompt Structure Eval
# ===========================================================================

class TestPromptStructureEval:
    """Verify SYSTEM_PROMPT contains all required structural elements."""

    def test_contains_fetch_file_tool(self):
        assert "FETCH_FILE" in SYSTEM_PROMPT

    def test_contains_list_dir_tool(self):
        assert "LIST_DIR" in SYSTEM_PROMPT

    def test_contains_search_code_tool(self):
        assert "SEARCH_CODE" in SYSTEM_PROMPT

    def test_contains_severity_p0(self):
        assert "P0" in SYSTEM_PROMPT

    def test_contains_severity_p1(self):
        assert "P1" in SYSTEM_PROMPT

    def test_contains_severity_p2(self):
        assert "P2" in SYSTEM_PROMPT

    def test_contains_severity_p3(self):
        assert "P3" in SYSTEM_PROMPT

    def test_contains_output_format_file_field(self):
        assert "File:" in SYSTEM_PROMPT

    def test_contains_output_format_description_field(self):
        assert "Description:" in SYSTEM_PROMPT

    def test_contains_output_format_fix_field(self):
        assert "Fix:" in SYSTEM_PROMPT

    def test_instructs_to_cite_line_numbers(self):
        lower = SYSTEM_PROMPT.lower()
        assert "line number" in lower or "cite" in lower

    def test_severity_definitions_present(self):
        assert "critical" in SYSTEM_PROMPT.lower()
        assert "high" in SYSTEM_PROMPT.lower()
        assert "medium" in SYSTEM_PROMPT.lower()
        assert "low" in SYSTEM_PROMPT.lower()


# ===========================================================================
# 2. Prompt Template Eval
# ===========================================================================

class TestReviewPromptTemplateEval:
    """Verify REVIEW_USER_PROMPT placeholders and formatting."""

    EXPECTED_PLACEHOLDERS = [
        "{title}",
        "{author}",
        "{head_branch}",
        "{base_branch}",
        "{changed_files}",
        "{additions}",
        "{deletions}",
        "{body}",
        "{diff_context}",
    ]

    def test_contains_all_placeholders(self):
        for placeholder in self.EXPECTED_PLACEHOLDERS:
            assert placeholder in REVIEW_USER_PROMPT, (
                f"Missing placeholder {placeholder} in REVIEW_USER_PROMPT"
            )

    def test_formats_correctly_with_realistic_values(self):
        result = REVIEW_USER_PROMPT.format(
            title="Add JWT authentication",
            author="alice",
            head_branch="feat/auth",
            base_branch="main",
            changed_files=5,
            additions=120,
            deletions=30,
            body="Implements token-based authentication.",
            diff_context="### src/auth.py [modified] +10/-2\n@@ -1,3 +1,5 @@",
        )
        # No unformatted placeholders left
        assert "{" not in result or "{{" in result  # allow escaped braces
        assert "Add JWT authentication" in result
        assert "alice" in result
        assert "feat/auth" in result

    def test_no_key_error_on_format(self):
        """Formatting with all expected keys should not raise."""
        kwargs = {p.strip("{}"): "test_value" for p in self.EXPECTED_PLACEHOLDERS}
        REVIEW_USER_PROMPT.format(**kwargs)  # should not raise


class TestQAPromptTemplateEval:
    """Verify QA_USER_PROMPT placeholders and formatting."""

    EXPECTED_PLACEHOLDERS = ["{pr_context}", "{selected_code}", "{question}"]

    def test_contains_all_placeholders(self):
        for placeholder in self.EXPECTED_PLACEHOLDERS:
            assert placeholder in QA_USER_PROMPT, (
                f"Missing placeholder {placeholder} in QA_USER_PROMPT"
            )

    def test_formats_correctly(self):
        result = QA_USER_PROMPT.format(
            pr_context="PR #42: Add auth",
            selected_code="token = get_token()",
            question="What does this function do?",
        )
        assert "{" not in result or "{{" in result
        assert "What does this function do?" in result
        assert "token = get_token()" in result

    def test_no_key_error_on_format(self):
        kwargs = {p.strip("{}"): "value" for p in self.EXPECTED_PLACEHOLDERS}
        QA_USER_PROMPT.format(**kwargs)


# ===========================================================================
# 3. Context Building Quality Eval
# ===========================================================================

class TestBuildPRSummaryEval:
    """Evaluate build_pr_summary with various PR metadata combinations."""

    def test_all_fields_populated(self):
        meta = _make_metadata()
        summary = build_pr_summary(meta)
        assert "Add JWT authentication" in summary
        assert "alice" in summary
        assert "feat/auth" in summary
        assert "main" in summary
        assert "30" in summary  # additions
        assert "5" in summary   # deletions

    def test_none_body_shows_placeholder(self):
        meta = _make_metadata(body=None)
        summary = build_pr_summary(meta)
        assert "(none)" in summary

    def test_long_body_not_truncated(self):
        long_body = "A" * 5000
        meta = _make_metadata(body=long_body)
        summary = build_pr_summary(meta)
        # Summary should include full body (build_pr_summary doesn't truncate)
        assert long_body in summary

    def test_zero_changes(self):
        meta = _make_metadata(n_files=0, additions=0, deletions=0)
        summary = build_pr_summary(meta)
        assert "0" in summary

    def test_contains_pr_number(self):
        meta = _make_metadata(number=99)
        summary = build_pr_summary(meta)
        assert "#99" in summary or "99" in summary


class TestBuildDiffContextEval:
    """Evaluate build_diff_context under various scenarios."""

    def test_five_files_all_included(self):
        meta = _make_metadata(n_files=5)
        diffs = [_make_diff(filename=f"src/file_{i}.py") for i in range(5)]
        context = build_diff_context(meta, diffs)
        for i in range(5):
            assert f"src/file_{i}.py" in context

    def test_overflow_files_noted(self):
        n_total = 51
        meta = _make_metadata(n_files=n_total)
        diffs = [_make_diff(filename=f"src/file_{i}.py") for i in range(n_total)]
        context = build_diff_context(meta, diffs)
        # First 50 should be directly included
        for i in range(CONTEXT_WINDOW_DIFF_LIMIT):
            assert f"src/file_{i}.py" in context
        # Overflow message
        assert "1 additional file" in context or "FETCH_FILE" in context

    def test_removed_file_shows_deleted(self):
        diff = FileDiff(
            filename="src/old.py",
            status="removed",
            additions=0,
            deletions=10,
            hunks=[],
        )
        meta = _make_metadata(n_files=1)
        context = build_diff_context(meta, [diff])
        assert "deleted" in context.lower() or "removed" in context.lower()

    def test_binary_file_shows_no_patch(self):
        diff = FileDiff(
            filename="assets/logo.png",
            status="modified",
            additions=0,
            deletions=0,
            hunks=[],  # no hunks for binary files
        )
        meta = _make_metadata(n_files=1)
        context = build_diff_context(meta, [diff])
        assert "binary" in context.lower() or "no patch" in context.lower()

    def test_file_header_format(self):
        diff = _make_diff(filename="src/auth.py", status="modified", additions=3, deletions=1)
        meta = _make_metadata(n_files=1)
        context = build_diff_context(meta, [diff])
        # Should contain filename with status and +/- counts
        assert "src/auth.py" in context
        assert "[modified]" in context
        assert "+3" in context

    def test_hunk_headers_preserved(self):
        diff = _make_diff(
            hunk_header="@@ -10,5 +10,7 @@ def authenticate():",
        )
        meta = _make_metadata(n_files=1)
        context = build_diff_context(meta, [diff])
        assert "@@ -10,5 +10,7 @@" in context

    def test_empty_diffs_list(self):
        meta = _make_metadata(n_files=0)
        context = build_diff_context(meta, [])
        assert context == "" or context.strip() == ""

    def test_exactly_limit_files_no_overflow(self):
        n = CONTEXT_WINDOW_DIFF_LIMIT
        diffs = [_make_diff(filename=f"src/f_{i}.py") for i in range(n)]
        meta = _make_metadata(n_files=n)
        context = build_diff_context(meta, diffs)
        assert "additional file" not in context
        assert "FETCH_FILE" not in context.split("### ")[-1] or "FETCH_FILE" not in context

    def test_multiple_hunks_per_file(self):
        diff = FileDiff(
            filename="src/auth.py",
            status="modified",
            additions=6,
            deletions=2,
            hunks=[
                DiffHunk(
                    header="@@ -10,5 +10,7 @@",
                    old_start=10, old_lines=5, new_start=10, new_lines=7,
                    lines=[" line1", "+added1"],
                ),
                DiffHunk(
                    header="@@ -30,3 +32,5 @@",
                    old_start=30, old_lines=3, new_start=32, new_lines=5,
                    lines=[" line2", "+added2"],
                ),
            ],
        )
        meta = _make_metadata(n_files=1)
        context = build_diff_context(meta, [diff])
        assert "@@ -10,5 +10,7 @@" in context
        assert "@@ -30,3 +32,5 @@" in context

    def test_diff_lines_included(self):
        diff = _make_diff(lines=[" unchanged", "+added_line", "-removed_line"])
        meta = _make_metadata(n_files=1)
        context = build_diff_context(meta, [diff])
        assert "+added_line" in context
        assert "-removed_line" in context


# ===========================================================================
# 4. Limit Sanity Eval
# ===========================================================================

class TestLimitSanityEval:
    """Evaluate that prompt-related limits are reasonable."""

    def test_context_window_diff_limit_positive(self):
        assert CONTEXT_WINDOW_DIFF_LIMIT > 0

    def test_context_window_diff_limit_upper_bound(self):
        assert CONTEXT_WINDOW_DIFF_LIMIT <= 100

    def test_repl_diff_limit_gte_context_window(self):
        assert REPL_DIFF_LIMIT >= CONTEXT_WINDOW_DIFF_LIMIT

    def test_repl_diff_limit_positive(self):
        assert REPL_DIFF_LIMIT > 0


# ===========================================================================
# 5. Determinism Eval
# ===========================================================================

class TestDeterminismEval:
    """Evaluate that context builders produce identical output on repeated calls."""

    def test_build_pr_summary_deterministic(self):
        meta = _make_metadata()
        results = [build_pr_summary(meta) for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_build_diff_context_deterministic(self):
        meta = _make_metadata(n_files=3)
        diffs = [_make_diff(filename=f"src/f_{i}.py") for i in range(3)]
        results = [build_diff_context(meta, diffs) for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_build_pr_summary_with_none_body_deterministic(self):
        meta = _make_metadata(body=None)
        results = [build_pr_summary(meta) for _ in range(3)]
        assert all(r == results[0] for r in results)

    def test_build_diff_context_with_overflow_deterministic(self):
        n = CONTEXT_WINDOW_DIFF_LIMIT + 5
        diffs = [_make_diff(filename=f"src/f_{i}.py") for i in range(n)]
        meta = _make_metadata(n_files=n)
        results = [build_diff_context(meta, diffs) for _ in range(3)]
        assert all(r == results[0] for r in results)


# ===========================================================================
# 6. Format Alignment Eval
# ===========================================================================

class TestFormatAlignmentEval:
    """Verify SYSTEM_PROMPT output format aligns with what parse_findings expects."""

    def test_system_prompt_format_example_parseable(self):
        """Build a finding in the exact format shown in SYSTEM_PROMPT, then parse it."""
        # The SYSTEM_PROMPT specifies this format:
        # [SEVERITY] TYPE: Short title
        # File: path/to/file.py lines X-Y
        # Description: ...
        # Fix: ...
        finding_str = (
            "[P1] security: Missing authentication check\n"
            "File: src/auth.py lines 10-20\n"
            "Description: The endpoint allows unauthenticated access to sensitive data.\n"
            "Fix: Add @require_auth decorator to the route handler."
        )
        findings = parse_findings(finding_str)
        assert len(findings) == 1
        f = findings[0]
        assert f.severity.value == "P1"
        assert f.type.value == "security"
        assert "Missing authentication check" in f.title
        assert f.citation.file == "src/auth.py"
        assert f.citation.line_start == 10
        assert f.citation.line_end == 20

    def test_multiple_findings_parseable(self):
        """Multiple findings in SYSTEM_PROMPT format should all parse."""
        raw = (
            "[P0] bug: SQL injection in login endpoint\n"
            "File: src/db.py lines 45-50\n"
            "Description: User input is interpolated directly into SQL query.\n"
            "Fix: Use parameterized queries.\n"
            "\n"
            "[P2] informational: Consider adding type hints\n"
            "File: src/utils.py lines 1-10\n"
            "Description: Functions lack type annotations.\n"
        )
        findings = parse_findings(raw)
        assert len(findings) == 2
        # Sorted by severity: P0 first
        assert findings[0].severity.value == "P0"
        assert findings[1].severity.value == "P2"

    def test_p0_finding_requires_fix_field(self):
        """A P0 finding with Fix field should parse the fix."""
        raw = (
            "[P0] bug: Crash on null input\n"
            "File: src/handler.py lines 30-35\n"
            "Description: Null pointer dereference.\n"
            "Fix: Add null check before access."
        )
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].fix is not None
        assert "null check" in findings[0].fix.lower()

    def test_severity_field_values_match_system_prompt(self):
        """All severity levels mentioned in SYSTEM_PROMPT should be parseable."""
        for sev in ["P0", "P1", "P2", "P3"]:
            raw = f"[{sev}] bug: Test finding\nFile: src/test.py lines 1-5\nDescription: Test."
            findings = parse_findings(raw)
            assert len(findings) == 1
            assert findings[0].severity.value == sev

    def test_finding_type_values_match_system_prompt(self):
        """Types mentioned in SYSTEM_PROMPT (bug, security, investigation, informational) parse."""
        for ftype in ["bug", "security", "investigation", "informational"]:
            raw = f"[P2] {ftype}: Test finding\nFile: src/t.py lines 1-2\nDescription: Test."
            findings = parse_findings(raw)
            assert len(findings) == 1
            assert findings[0].type.value == ftype

    def test_colon_citation_format_also_works(self):
        """Citation in colon format (file.py:10-20) should also be extracted."""
        raw = (
            "[P2] bug: Off-by-one error\n"
            "File: src/loop.py:10-20\n"
            "Description: Loop iterates one too many times."
        )
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].citation.file == "src/loop.py"
        assert findings[0].citation.line_start == 10
