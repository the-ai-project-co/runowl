"""Tests for severity classification logic."""

from review.models import Citation, Finding, FindingType, Severity
from review.severity import (
    classify_severity,
    ensure_fix_for_blocking,
    max_severity,
    reclassify_findings,
)


def _finding(
    title: str = "",
    description: str = "",
    severity: Severity = Severity.P3,
    ftype: FindingType = FindingType.INFORMATIONAL,
    fix: str | None = None,
) -> Finding:
    return Finding(
        severity=severity,
        type=ftype,
        title=title,
        description=description,
        citation=Citation(file="src/a.py", line_start=1, line_end=1),
        fix=fix,
    )


# ── max_severity ───────────────────────────────────────────────────────────────


class TestMaxSeverity:
    def test_p0_beats_p1(self) -> None:
        assert max_severity(Severity.P0, Severity.P1) == Severity.P0

    def test_p1_beats_p2(self) -> None:
        assert max_severity(Severity.P1, Severity.P2) == Severity.P1

    def test_equal_returns_same(self) -> None:
        assert max_severity(Severity.P2, Severity.P2) == Severity.P2

    def test_p3_loses_to_p0(self) -> None:
        assert max_severity(Severity.P3, Severity.P0) == Severity.P0


# ── classify_severity — P0 signals ────────────────────────────────────────────


class TestClassifyP0:
    def test_sql_injection_is_p0(self) -> None:
        f = _finding(title="SQL injection in login", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P0

    def test_rce_is_p0(self) -> None:
        f = _finding(description="This allows remote code execution", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P0

    def test_hardcoded_password_is_p0(self) -> None:
        f = _finding(title="Hardcoded password in config", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P0

    def test_path_traversal_is_p0(self) -> None:
        f = _finding(description="User input enables path traversal attack", ftype=FindingType.BUG)
        assert classify_severity(f) == Severity.P0

    def test_data_loss_is_p0(self) -> None:
        f = _finding(title="Missing transaction causes data loss", ftype=FindingType.BUG)
        assert classify_severity(f) == Severity.P0

    def test_auth_bypass_is_p0(self) -> None:
        f = _finding(title="Authentication bypass via token replay", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P0

    def test_ssrf_is_p0(self) -> None:
        f = _finding(description="SSRF via unvalidated URL parameter", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P0


# ── classify_severity — P1 signals ────────────────────────────────────────────


class TestClassifyP1:
    def test_xss_is_p1(self) -> None:
        f = _finding(title="XSS in comment field", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P1

    def test_weak_hash_is_p1(self) -> None:
        f = _finding(description="Password hashed with MD5", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P1

    def test_sha1_is_p1(self) -> None:
        f = _finding(description="Uses SHA1 for signature verification", ftype=FindingType.SECURITY)
        assert classify_severity(f) == Severity.P1

    def test_race_condition_is_p1(self) -> None:
        f = _finding(title="Race condition in file write", ftype=FindingType.BUG)
        assert classify_severity(f) == Severity.P1

    def test_memory_leak_is_p1(self) -> None:
        f = _finding(title="Memory leak in connection pool", ftype=FindingType.BUG)
        assert classify_severity(f) == Severity.P1

    def test_missing_timeout_is_p1(self) -> None:
        f = _finding(description="HTTP client has no missing timeout set", ftype=FindingType.BUG)
        assert classify_severity(f) == Severity.P1

    def test_unhandled_exception_is_p1(self) -> None:
        f = _finding(title="Unhandled exception in payment handler", ftype=FindingType.BUG)
        assert classify_severity(f) == Severity.P1


# ── classify_severity — P2 signals ────────────────────────────────────────────


class TestClassifyP2:
    def test_cors_is_at_least_p2(self) -> None:
        f = _finding(title="CORS misconfiguration allows all origins", ftype=FindingType.SECURITY)
        result = classify_severity(f)
        assert result in (Severity.P1, Severity.P2)

    def test_information_disclosure_is_p2(self) -> None:
        f = _finding(
            title="Verbose error causes information disclosure",
            ftype=FindingType.INVESTIGATION,
        )
        result = classify_severity(f)
        assert result in (Severity.P1, Severity.P2)

    def test_n_plus_1_query_is_p2(self) -> None:
        f = _finding(description="N+1 query in user list endpoint", ftype=FindingType.BUG)
        result = classify_severity(f)
        assert result in (Severity.P1, Severity.P2)

    def test_god_object_is_p2(self) -> None:
        f = _finding(title="God object with 40 methods", ftype=FindingType.INFORMATIONAL)
        result = classify_severity(f)
        assert result in (Severity.P2, Severity.P3)


# ── classify_severity — P3 signals ────────────────────────────────────────────


class TestClassifyP3:
    def test_unused_import_is_p3(self) -> None:
        f = _finding(title="Unused import: os", ftype=FindingType.INFORMATIONAL)
        assert classify_severity(f) == Severity.P3

    def test_typo_is_p3(self) -> None:
        f = _finding(description="Typo in variable name", ftype=FindingType.INFORMATIONAL)
        assert classify_severity(f) == Severity.P3

    def test_naming_is_p3(self) -> None:
        f = _finding(title="Variable naming is ambiguous", ftype=FindingType.INFORMATIONAL)
        assert classify_severity(f) == Severity.P3


# ── Security type floor ────────────────────────────────────────────────────────


class TestSecurityFloor:
    def test_security_type_never_below_p2(self) -> None:
        f = _finding(
            title="Minor security style note",
            ftype=FindingType.SECURITY,
            severity=Severity.P3,
        )
        result = classify_severity(f)
        assert result in (Severity.P0, Severity.P1, Severity.P2)

    def test_bug_type_never_below_p2(self) -> None:
        f = _finding(
            title="Unused variable in test helper",
            ftype=FindingType.BUG,
            severity=Severity.P3,
        )
        result = classify_severity(f)
        assert result in (Severity.P0, Severity.P1, Severity.P2)


# ── reclassify_findings ────────────────────────────────────────────────────────


class TestReclassifyFindings:
    def test_promotes_under_classified_finding(self) -> None:
        findings = [
            _finding(
                title="SQL injection in search", ftype=FindingType.SECURITY, severity=Severity.P2
            )
        ]
        reclassify_findings(findings)
        assert findings[0].severity == Severity.P0

    def test_sorted_after_reclassification(self) -> None:
        findings = [
            _finding(title="Typo", severity=Severity.P3),
            _finding(title="SQL injection", ftype=FindingType.SECURITY, severity=Severity.P3),
        ]
        reclassify_findings(findings)
        assert findings[0].severity == Severity.P0
        assert findings[1].severity == Severity.P3

    def test_no_findings_ok(self) -> None:
        assert reclassify_findings([]) == []


# ── ensure_fix_for_blocking ───────────────────────────────────────────────────


class TestEnsureFixForBlocking:
    def test_p0_without_fix_gets_placeholder(self) -> None:
        findings = [_finding(severity=Severity.P0, ftype=FindingType.BUG, fix=None)]
        ensure_fix_for_blocking(findings)
        assert findings[0].fix is not None
        assert "blocks merge" in findings[0].fix

    def test_p1_without_fix_gets_placeholder(self) -> None:
        findings = [_finding(severity=Severity.P1, ftype=FindingType.SECURITY, fix=None)]
        ensure_fix_for_blocking(findings)
        assert findings[0].fix is not None

    def test_p0_with_fix_not_overwritten(self) -> None:
        findings = [
            _finding(severity=Severity.P0, ftype=FindingType.BUG, fix="Use parameterized queries.")
        ]
        ensure_fix_for_blocking(findings)
        assert findings[0].fix == "Use parameterized queries."

    def test_p2_without_fix_not_touched(self) -> None:
        findings = [_finding(severity=Severity.P2, fix=None)]
        ensure_fix_for_blocking(findings)
        assert findings[0].fix is None

    def test_p3_without_fix_not_touched(self) -> None:
        findings = [_finding(severity=Severity.P3, fix=None)]
        ensure_fix_for_blocking(findings)
        assert findings[0].fix is None
