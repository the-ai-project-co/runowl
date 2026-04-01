"""Tests for the surface security scanner."""

from github.models import DiffHunk, FileDiff
from security.models import SecurityCheckType
from security.scanner import run_surface_scan


def _diff(filename: str, added_lines: list[str], status: str = "added") -> FileDiff:
    raw = [f"+{line}" for line in added_lines]
    hunk = DiffHunk(
        header=f"@@ -0,0 +1,{len(added_lines)} @@",
        old_start=0,
        old_lines=0,
        new_start=1,
        new_lines=len(added_lines),
        lines=raw,
    )
    return FileDiff(
        filename=filename,
        status=status,
        additions=len(added_lines),
        deletions=0,
        hunks=[hunk],
    )


class TestRunSurfaceScan:
    def test_empty_diffs_returns_empty_report(self) -> None:
        report = run_surface_scan([])
        assert not report.has_issues
        assert report.files_scanned == 0

    def test_detects_secret_in_py_file(self) -> None:
        diff = _diff("src/config.py", ['secret_key = "abc-very-secret-123"'])
        report = run_surface_scan([diff])
        assert report.has_issues
        assert any(h.check == SecurityCheckType.HARDCODED_SECRET for h in report.hits)

    def test_counts_files_scanned(self) -> None:
        diffs = [
            _diff("src/a.py", ["x = 1"]),
            _diff("src/b.py", ["y = 2"]),
        ]
        report = run_surface_scan(diffs)
        assert report.files_scanned == 2

    def test_skips_removed_files(self) -> None:
        diff = _diff("src/config.py", ['password = "secret"'], status="removed")
        report = run_surface_scan([diff])
        assert not report.has_issues

    def test_skips_lock_files(self) -> None:
        diff = _diff("package-lock.json", ['"axios": "^1.0.0"'])
        report = run_surface_scan([diff])
        assert not report.has_issues

    def test_skips_binary_extensions(self) -> None:
        diff = _diff("assets/image.png", ["fake binary content"])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_deduplicates_hits(self) -> None:
        # Two diffs with the same file/line/check should produce one hit
        diff = _diff("src/a.py", ['api_key = "real-key-value-here"'])
        report = run_surface_scan([diff, diff])
        hits = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        # Should deduplicate — same file+line+check
        assert len(hits) == len(set((h.file, h.line, h.check) for h in hits))

    def test_multiple_checks_on_same_file(self) -> None:
        diff = _diff(
            "src/app.py",
            [
                'password = "hardcoded_pass_123"',
                'cursor.execute("SELECT * FROM users WHERE id=" + uid)',
                "el.innerHTML = userData",
            ],
        )
        report = run_surface_scan([diff])
        check_types = {h.check for h in report.hits}
        assert SecurityCheckType.HARDCODED_SECRET in check_types
        assert SecurityCheckType.SQL_INJECTION in check_types
        assert SecurityCheckType.XSS in check_types

    def test_by_check_filter(self) -> None:
        diff = _diff("src/config.py", ['jwt_secret = "my-jwt-secret-value"'])
        report = run_surface_scan([diff])
        secrets = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert len(secrets) >= 1
        assert all(h.check == SecurityCheckType.HARDCODED_SECRET for h in secrets)

    def test_hit_citation_format(self) -> None:
        diff = _diff("src/config.py", ['api_key = "leaked-api-key"'])
        report = run_surface_scan([diff])
        assert report.hits[0].citation == "src/config.py:1"

    def test_requirements_unpinned_flagged(self) -> None:
        diff = _diff("requirements.txt", ["flask", "requests==2.31.0"])
        report = run_surface_scan([diff])
        unpinned = report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        assert len(unpinned) == 1  # only "flask" is bare
