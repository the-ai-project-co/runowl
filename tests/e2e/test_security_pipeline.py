"""End-to-end tests for the full security scanning pipeline.

Exercises the complete flow: raw diff input -> run_surface_scan -> SecurityReport output.
Each test builds realistic FileDiff objects with proper DiffHunk structures and verifies
that the pipeline correctly detects (or ignores) vulnerabilities across the full chain.
"""

import pytest

from github.models import DiffHunk, FileDiff
from security.models import SecurityCheckType, SecurityHit, SecurityReport
from security.scanner import run_surface_scan


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_hunk(
    added_lines: list[str],
    new_start: int = 1,
    context_before: list[str] | None = None,
    context_after: list[str] | None = None,
    removed_lines: list[str] | None = None,
) -> DiffHunk:
    """Build a DiffHunk with optional context lines, removed lines, and added lines.

    This produces realistic hunk structures where context lines have a space prefix,
    removed lines have a '-' prefix, and added lines have a '+' prefix.
    """
    raw: list[str] = []
    old_count = 0
    new_count = 0

    for line in context_before or []:
        raw.append(f" {line}")
        old_count += 1
        new_count += 1

    for line in removed_lines or []:
        raw.append(f"-{line}")
        old_count += 1

    for line in added_lines:
        raw.append(f"+{line}")
        new_count += 1

    for line in context_after or []:
        raw.append(f" {line}")
        old_count += 1
        new_count += 1

    old_start = max(1, new_start - len(context_before or []))
    header = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"

    return DiffHunk(
        header=header,
        old_start=old_start,
        old_lines=old_count,
        new_start=new_start,
        new_lines=new_count,
        lines=raw,
    )


def _make_diff(
    filename: str,
    hunks: list[DiffHunk],
    status: str = "modified",
) -> FileDiff:
    """Build a FileDiff from a list of hunks, computing additions/deletions."""
    additions = sum(
        1 for h in hunks for line in h.lines if line.startswith("+")
    )
    deletions = sum(
        1 for h in hunks for line in h.lines if line.startswith("-")
    )
    return FileDiff(
        filename=filename,
        status=status,
        additions=additions,
        deletions=deletions,
        hunks=hunks,
    )


def _simple_diff(
    filename: str,
    added_lines: list[str],
    start: int = 1,
    status: str = "added",
) -> FileDiff:
    """Shorthand for a single-hunk diff containing only added lines."""
    hunk = _make_hunk(added_lines, new_start=start)
    return FileDiff(
        filename=filename,
        status=status,
        additions=len(added_lines),
        deletions=0,
        hunks=[hunk],
    )


# ── 1. Full multi-file PR scan with all vulnerability types ─────────────────


class TestFullMultiVulnerabilityPR:
    """Simulate a realistic multi-file PR that introduces every vulnerability type."""

    @pytest.fixture()
    def multi_vuln_report(self) -> SecurityReport:
        """Build and scan a realistic PR touching 6 files with diverse issues."""
        diffs = [
            # File 1: Python config with hardcoded secrets
            _make_diff(
                "src/settings/database.py",
                [
                    _make_hunk(
                        added_lines=[
                            "import os",
                            "",
                            "class DatabaseConfig:",
                            '    DB_HOST = "prod-db.internal.company.com"',
                            '    DB_PORT = 5432',
                            '    password = "Zk$9vL!mNqR3xW7p"',
                            '    api_key = "sk-live-4f8b2c1d9e7a3f6b5c8d2e1a"',
                        ],
                        new_start=1,
                        context_before=[],
                    ),
                ],
                status="added",
            ),
            # File 2: API route with SQL injection and missing auth
            _make_diff(
                "src/api/users.py",
                [
                    _make_hunk(
                        added_lines=[
                            "from flask import request, jsonify",
                            "from app import app, db",
                            "",
                            "@app.get('/api/v1/users/search')",
                            "def search_users():",
                            '    query = request.args.get("q")',
                            '    cursor.execute(f"SELECT * FROM users WHERE name LIKE \'%{query}%\'")',
                            "    results = cursor.fetchall()",
                            "    return jsonify(results)",
                        ],
                        new_start=1,
                    ),
                    _make_hunk(
                        added_lines=[
                            "@app.post('/api/v1/users/delete')",
                            "def delete_user():",
                            '    user_id = request.json["id"]',
                            '    db.raw("DELETE FROM users WHERE id=" + str(user_id))',
                            "    return jsonify(success=True)",
                        ],
                        new_start=25,
                        context_before=[
                            "",
                            "# User management endpoints",
                        ],
                    ),
                ],
                status="added",
            ),
            # File 3: Frontend JS with XSS vulnerabilities
            _make_diff(
                "src/frontend/components/UserProfile.jsx",
                [
                    _make_hunk(
                        added_lines=[
                            "function UserProfile({ user }) {",
                            "  return (",
                            "    <div>",
                            "      <h1>{user.name}</h1>",
                            '      <div dangerouslySetInnerHTML={{__html: user.bio}} />',
                            "    </div>",
                            "  );",
                            "}",
                        ],
                        new_start=15,
                        context_before=[
                            "import React from 'react';",
                            "",
                        ],
                    ),
                ],
            ),
            # File 4: Debug endpoint exposing env vars
            _make_diff(
                "src/api/debug.py",
                [
                    _make_hunk(
                        added_lines=[
                            "import os",
                            "import logging",
                            "",
                            "logger = logging.getLogger(__name__)",
                            "",
                            "def dump_config():",
                            '    logger.info(os.environ["SECRET_KEY"])',
                            '    print(os.getenv("DATABASE_PASSWORD"))',
                        ],
                        new_start=1,
                    ),
                ],
                status="added",
            ),
            # File 5: requirements.txt with unpinned dependencies
            _simple_diff(
                "requirements.txt",
                [
                    "flask",
                    "sqlalchemy>=1.4",
                    "requests==2.31.0",
                    "pyjwt",
                    "celery~=5.3",
                    "redis==4.6.0",
                    "boto3>=1.28",
                ],
            ),
            # File 6: package.json with caret-range dependencies
            _simple_diff(
                "package.json",
                [
                    "{",
                    '  "dependencies": {',
                    '    "react": "^18.2.0",',
                    '    "axios": "^1.6.2",',
                    '    "lodash": "4.17.21"',
                    "  }",
                    "}",
                ],
            ),
        ]
        return run_surface_scan(diffs)

    def test_report_has_issues(self, multi_vuln_report: SecurityReport) -> None:
        assert multi_vuln_report.has_issues

    def test_all_six_check_types_present(self, multi_vuln_report: SecurityReport) -> None:
        found_types = {h.check for h in multi_vuln_report.hits}
        assert SecurityCheckType.HARDCODED_SECRET in found_types
        assert SecurityCheckType.SQL_INJECTION in found_types
        assert SecurityCheckType.XSS in found_types
        assert SecurityCheckType.MISSING_AUTH in found_types
        assert SecurityCheckType.EXPOSED_ENV in found_types
        assert SecurityCheckType.UNPINNED_DEPENDENCY in found_types

    def test_files_scanned_count(self, multi_vuln_report: SecurityReport) -> None:
        # All 6 files should be scanned (none are lock/binary/removed)
        assert multi_vuln_report.files_scanned == 6

    def test_hardcoded_secrets_found(self, multi_vuln_report: SecurityReport) -> None:
        secrets = multi_vuln_report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert len(secrets) >= 2
        files = {h.file for h in secrets}
        assert "src/settings/database.py" in files

    def test_sql_injection_found(self, multi_vuln_report: SecurityReport) -> None:
        sqli = multi_vuln_report.by_check(SecurityCheckType.SQL_INJECTION)
        assert len(sqli) >= 2
        # Both the SELECT f-string and the DELETE concatenation
        files = {h.file for h in sqli}
        assert "src/api/users.py" in files

    def test_xss_found(self, multi_vuln_report: SecurityReport) -> None:
        xss = multi_vuln_report.by_check(SecurityCheckType.XSS)
        assert len(xss) >= 1
        assert any(h.file == "src/frontend/components/UserProfile.jsx" for h in xss)

    def test_missing_auth_found(self, multi_vuln_report: SecurityReport) -> None:
        auth = multi_vuln_report.by_check(SecurityCheckType.MISSING_AUTH)
        assert len(auth) >= 1
        assert any(h.file == "src/api/users.py" for h in auth)

    def test_exposed_env_found(self, multi_vuln_report: SecurityReport) -> None:
        env = multi_vuln_report.by_check(SecurityCheckType.EXPOSED_ENV)
        assert len(env) >= 2
        assert any(h.file == "src/api/debug.py" for h in env)

    def test_unpinned_deps_found(self, multi_vuln_report: SecurityReport) -> None:
        deps = multi_vuln_report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        # requirements.txt: flask (bare), sqlalchemy>=1.4, pyjwt (bare), celery~=5.3, boto3>=1.28
        # package.json: react ^18, axios ^1.6
        assert len(deps) >= 4

    def test_total_hit_count_is_reasonable(self, multi_vuln_report: SecurityReport) -> None:
        # With 6 files and many patterns, we expect a double-digit hit count
        assert len(multi_vuln_report.hits) >= 10


# ── 2. Clean PR with no issues ──────────────────────────────────────────────


class TestCleanPR:
    """A PR that follows best practices should produce zero hits."""

    def test_clean_pr_has_no_issues(self) -> None:
        diffs = [
            # Well-written Python: env vars for secrets, parameterized queries, auth present
            _simple_diff(
                "src/api/orders.py",
                [
                    "import os",
                    "from flask import request, jsonify",
                    "from app import app, db",
                    "from auth import login_required",
                    "",
                    'DB_URL = os.environ.get("DATABASE_URL")',
                    "",
                    "@login_required",
                    "@app.get('/api/v1/orders')",
                    "def list_orders():",
                    "    user = current_user",
                    '    cursor.execute("SELECT * FROM orders WHERE user_id = ?", (user.id,))',
                    "    return jsonify(cursor.fetchall())",
                ],
            ),
            # Safe frontend: uses textContent, no innerHTML
            _simple_diff(
                "src/frontend/safe_component.js",
                [
                    "function renderName(el, name) {",
                    "  el.textContent = name;",
                    "}",
                ],
            ),
            # Pinned requirements
            _simple_diff(
                "requirements.txt",
                [
                    "flask==3.0.0",
                    "sqlalchemy==2.0.23",
                    "requests==2.31.0",
                ],
            ),
        ]

        report = run_surface_scan(diffs)
        assert not report.has_issues
        assert report.files_scanned == 3
        assert len(report.hits) == 0


# ── 3. Filtering: removed files, lock files, binary files, test files ────────


class TestFileFiltering:
    """Pipeline should skip removed files, lock files, and binary extensions."""

    def test_removed_files_are_excluded(self) -> None:
        """Deleted files should never be scanned (their code is being removed)."""
        diff = _simple_diff(
            "src/old_config.py",
            [
                'password = "leaked_credential_value_123"',
                'api_key = "sk-prod-a1b2c3d4e5f6g7h8"',
            ],
            status="removed",
        )
        report = run_surface_scan([diff])
        assert not report.has_issues
        assert report.files_scanned == 0

    def test_lock_files_are_excluded(self) -> None:
        """Lock files contain dependency version ranges but should not be scanned."""
        lock_diffs = [
            _simple_diff("package-lock.json", ['"axios": "^1.6.0"']),
            _simple_diff("yarn.lock", ['"lodash@^4.17.0":']),
            _simple_diff("poetry.lock", ['name = "requests"', "version = '>= 2.0'"]),
            _simple_diff("uv.lock", ['name = "flask"']),
        ]
        report = run_surface_scan(lock_diffs)
        assert not report.has_issues
        assert report.files_scanned == 0

    def test_binary_extensions_are_excluded(self) -> None:
        """Files with binary extensions (.png, .jpg, .pdf, etc.) should be skipped."""
        binary_diffs = [
            _simple_diff("assets/logo.png", ["binary content placeholder"]),
            _simple_diff("docs/spec.pdf", ["binary content placeholder"]),
            _simple_diff("fonts/inter.woff2", ["binary content placeholder"]),
            _simple_diff("icons/favicon.ico", ["binary content placeholder"]),
            _simple_diff("dist/bundle.min.js", ['password = "not_scanned"']),
            _simple_diff("dist/styles.min.css", ["body { color: red; }"]),
        ]
        report = run_surface_scan(binary_diffs)
        assert not report.has_issues
        assert report.files_scanned == 0

    def test_map_and_generated_files_excluded(self) -> None:
        """Source map files should be skipped."""
        diff = _simple_diff("dist/app.js.map", ['{"sources":["../src/app.js"]}'])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_sum_files_excluded(self) -> None:
        """Go sum files (.sum) should be skipped."""
        diff = _simple_diff("go.sum", ["github.com/pkg/errors v0.9.1 h1:abc123"])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_mixed_scannable_and_skippable(self) -> None:
        """Only non-skippable files should contribute to files_scanned."""
        diffs = [
            _simple_diff("src/app.py", ["x = 1"]),  # scanned
            _simple_diff("package-lock.json", ['"dep": "^1.0"']),  # skipped
            _simple_diff("assets/icon.svg", ["<svg></svg>"]),  # skipped
            _simple_diff("src/main.go", ["func main() {}"]),  # scanned
            _simple_diff("old_file.py", ['secret = "x"'], status="removed"),  # skipped
        ]
        report = run_surface_scan(diffs)
        assert report.files_scanned == 2

    def test_lock_extension_files_excluded(self) -> None:
        """Files ending in .lock extension should be skipped."""
        diff = _simple_diff("Gemfile.lock", ["GEM", "remote: https://rubygems.org/"])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0


# ── 4. Deduplication of hits ────────────────────────────────────────────────


class TestDeduplication:
    """The scanner deduplicates by (file, line, check)."""

    def test_identical_diffs_deduplicated(self) -> None:
        """Passing the same FileDiff object twice should not produce duplicate hits."""
        diff = _simple_diff(
            "src/config.py",
            ['signing_key = "rsa-private-key-prod-9f8e7d6c"'],
        )
        report = run_surface_scan([diff, diff])
        secrets = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert len(secrets) == 1

    def test_same_content_different_files_not_deduplicated(self) -> None:
        """Same vulnerability in two different files should produce two separate hits."""
        diff_a = _simple_diff(
            "src/config_a.py",
            ['client_secret = "cs-live-prod-abcdef123456"'],
        )
        diff_b = _simple_diff(
            "src/config_b.py",
            ['client_secret = "cs-live-prod-abcdef123456"'],
        )
        report = run_surface_scan([diff_a, diff_b])
        secrets = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert len(secrets) == 2
        assert {h.file for h in secrets} == {"src/config_a.py", "src/config_b.py"}

    def test_same_file_different_lines_not_deduplicated(self) -> None:
        """Two different lines in the same file with the same check produce separate hits."""
        diff = _make_diff(
            "src/config.py",
            [
                _make_hunk(
                    added_lines=['password = "alpha-bravo-charlie-123"'],
                    new_start=10,
                ),
                _make_hunk(
                    added_lines=['api_key = "delta-echo-foxtrot-456"'],
                    new_start=50,
                ),
            ],
        )
        report = run_surface_scan([diff])
        secrets = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert len(secrets) == 2
        lines = {h.line for h in secrets}
        assert 10 in lines
        assert 50 in lines

    def test_dedup_across_duplicate_diffs_preserves_other_checks(self) -> None:
        """Deduplication only collapses same (file, line, check) tuples -- not across checks."""
        diff = _simple_diff(
            "src/app.py",
            [
                'password = "hunter2-is-a-real-password"',
                "el.innerHTML = userInput",
            ],
        )
        report = run_surface_scan([diff, diff])
        assert len(report.by_check(SecurityCheckType.HARDCODED_SECRET)) == 1
        assert len(report.by_check(SecurityCheckType.XSS)) == 1


# ── 5. Citation format verification ─────────────────────────────────────────


class TestCitationFormat:
    """Every SecurityHit.citation must follow the file:line format."""

    def test_citation_matches_file_colon_line(self) -> None:
        diff = _simple_diff(
            "src/services/payment.py",
            ['encryption_key = "enc-key-a8b7c6d5e4f3g2h1"'],
            start=42,
        )
        report = run_surface_scan([diff])
        assert report.has_issues
        hit = report.hits[0]
        assert hit.citation == "src/services/payment.py:42"

    def test_all_citations_in_multi_file_scan(self) -> None:
        """Every hit across a multi-file scan should have a valid citation string."""
        diffs = [
            _simple_diff(
                "src/auth.py",
                ['jwt_secret = "jwt-prod-secret-key-xyz789"'],
                start=10,
            ),
            _simple_diff(
                "src/views.py",
                [
                    "@app.get('/admin/panel')",
                    "def admin_panel():",
                    "    return render_template('admin.html')",
                ],
                start=100,
            ),
        ]
        report = run_surface_scan(diffs)
        for hit in report.hits:
            assert ":" in hit.citation
            file_part, line_part = hit.citation.rsplit(":", 1)
            assert file_part == hit.file
            assert line_part.isdigit()
            assert int(line_part) == hit.line

    def test_citation_with_nested_path(self) -> None:
        diff = _simple_diff(
            "src/infrastructure/adapters/database/connection.py",
            ['private_key = "pk-live-9a8b7c6d5e4f3g2h1i0j"'],
            start=7,
        )
        report = run_surface_scan([diff])
        assert report.hits[0].citation == "src/infrastructure/adapters/database/connection.py:7"


# ── 6. All surface hits have is_free=True ────────────────────────────────────


class TestSurfaceHitsAreFree:
    """Surface-level checks are free tier. Every hit from run_surface_scan should be is_free=True."""

    def test_all_hits_are_free_in_multi_vuln_scan(self) -> None:
        diffs = [
            _simple_diff(
                "src/config.py",
                ['access_key = "AKIA-prod-access-key-1234567890"'],
            ),
            _simple_diff(
                "src/db.py",
                ['cursor.execute(f"SELECT * FROM accounts WHERE email = \'{email}\'")'],
            ),
            _simple_diff(
                "src/views.js",
                ["document.write(untrustedData)"],
            ),
            _simple_diff(
                "src/routes.py",
                [
                    "@router.delete('/api/v1/resources/{id}')",
                    "def destroy(id):",
                    "    db.delete(id)",
                ],
            ),
            _simple_diff(
                "src/debug.py",
                ['logger.warning(os.environ["STRIPE_SECRET_KEY"])'],
            ),
            _simple_diff(
                "requirements.txt",
                ["django", "gunicorn>=21.0"],
            ),
        ]
        report = run_surface_scan(diffs)
        assert report.has_issues
        for hit in report.hits:
            assert hit.is_free is True, (
                f"Hit for {hit.check} at {hit.citation} should be is_free=True"
            )

    def test_is_free_default_on_constructed_hit(self) -> None:
        """SecurityHit defaults to is_free=True when not specified."""
        hit = SecurityHit(
            check=SecurityCheckType.HARDCODED_SECRET,
            file="test.py",
            line=1,
            snippet="secret = 'x'",
            message="test",
            fix="test",
        )
        assert hit.is_free is True


# ── 7. Config file commit: secrets + env exposure ────────────────────────────


class TestConfigFileCommitScenario:
    """Simulate committing a configuration module that both hardcodes secrets
    and logs them, as commonly seen in rushed prototyping."""

    @pytest.fixture()
    def config_report(self) -> SecurityReport:
        diffs = [
            _make_diff(
                "src/config/settings.py",
                [
                    _make_hunk(
                        added_lines=[
                            "import os",
                            "import logging",
                            "",
                            "logger = logging.getLogger(__name__)",
                            "",
                            "# Database configuration",
                            'DB_HOST = "prod-rds.us-east-1.amazonaws.com"',
                            'DB_NAME = "app_production"',
                            'password = "Pr0d!P@ssw0rd#2024$Secure"',
                            "",
                            "# External service keys",
                            'api_key = "sk-proj-abcdef1234567890abcdef1234567890"',
                            'auth_token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"',
                            "",
                            "def init_config():",
                            '    logger.info(os.environ["SECRET_KEY"])',
                            '    print(os.getenv("MASTER_PASSWORD"))',
                            '    logger.debug(os.environ["API_TOKEN"])',
                        ],
                        new_start=1,
                    ),
                ],
                status="added",
            ),
            _make_diff(
                "src/config/__init__.py",
                [
                    _make_hunk(
                        added_lines=[
                            "from .settings import DB_HOST, DB_NAME, password, api_key",
                        ],
                        new_start=1,
                    ),
                ],
                status="added",
            ),
        ]
        return run_surface_scan(diffs)

    def test_secrets_detected(self, config_report: SecurityReport) -> None:
        secrets = config_report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert len(secrets) >= 3  # password, api_key, auth_token
        snippets = " ".join(h.snippet for h in secrets)
        assert "password" in snippets.lower() or "api_key" in snippets.lower()

    def test_env_exposure_detected(self, config_report: SecurityReport) -> None:
        env = config_report.by_check(SecurityCheckType.EXPOSED_ENV)
        assert len(env) >= 2  # logger.info + print + logger.debug
        assert all(h.file == "src/config/settings.py" for h in env)

    def test_no_false_positives_on_init_file(self, config_report: SecurityReport) -> None:
        """The __init__.py re-export line should not itself trigger secrets detection."""
        init_hits = [h for h in config_report.hits if h.file == "src/config/__init__.py"]
        assert len(init_hits) == 0

    def test_both_check_types_present(self, config_report: SecurityReport) -> None:
        check_types = {h.check for h in config_report.hits}
        assert SecurityCheckType.HARDCODED_SECRET in check_types
        assert SecurityCheckType.EXPOSED_ENV in check_types

    def test_each_hit_has_remediation(self, config_report: SecurityReport) -> None:
        for hit in config_report.hits:
            assert hit.fix, f"Hit at {hit.citation} is missing a fix string"
            assert len(hit.fix) >= 10, f"Fix at {hit.citation} is too terse: {hit.fix!r}"

    def test_each_hit_has_message(self, config_report: SecurityReport) -> None:
        for hit in config_report.hits:
            assert hit.message, f"Hit at {hit.citation} is missing a message"
            assert len(hit.message) >= 10


# ── 8. New API endpoint: missing auth + SQL injection ────────────────────────


class TestNewAPIEndpointScenario:
    """Simulate adding a new REST API controller with unprotected routes and
    raw SQL queries -- a common pattern in feature branches."""

    @pytest.fixture()
    def api_report(self) -> SecurityReport:
        diffs = [
            _make_diff(
                "src/api/v2/inventory.py",
                [
                    _make_hunk(
                        added_lines=[
                            "from flask import request, jsonify, Blueprint",
                            "from app.db import get_connection",
                            "",
                            "bp = Blueprint('inventory', __name__)",
                            "",
                            "@bp.get('/api/v2/inventory')",
                            "def list_inventory():",
                            '    category = request.args.get("category", "")',
                            "    conn = get_connection()",
                            '    cursor = conn.cursor()',
                            '    cursor.execute(f"SELECT * FROM inventory WHERE category = \'{category}\'")',
                            "    items = cursor.fetchall()",
                            "    return jsonify(items)",
                            "",
                            "@bp.post('/api/v2/inventory')",
                            "def create_item():",
                            "    data = request.json",
                            '    query = "INSERT INTO inventory (name, qty) VALUES (\'%s\', %s)" % (data["name"], data["qty"])',
                            "    conn = get_connection()",
                            "    conn.cursor().execute(query)",
                            "    conn.commit()",
                            '    return jsonify({"status": "created"}), 201',
                            "",
                            "@bp.put('/api/v2/inventory/<int:item_id>')",
                            "def update_item(item_id):",
                            "    data = request.json",
                            '    db.raw("UPDATE inventory SET name=\'" + data["name"] + "\' WHERE id=" + str(item_id))',
                            '    return jsonify({"status": "updated"})',
                        ],
                        new_start=1,
                    ),
                ],
                status="added",
            ),
        ]
        return run_surface_scan(diffs)

    def test_missing_auth_on_all_routes(self, api_report: SecurityReport) -> None:
        auth_hits = api_report.by_check(SecurityCheckType.MISSING_AUTH)
        assert len(auth_hits) >= 2  # GET, POST, PUT routes without auth
        assert all(h.file == "src/api/v2/inventory.py" for h in auth_hits)

    def test_sql_injection_on_query_construction(self, api_report: SecurityReport) -> None:
        sqli_hits = api_report.by_check(SecurityCheckType.SQL_INJECTION)
        assert len(sqli_hits) >= 2  # f-string SELECT + concatenated UPDATE
        snippets_combined = " ".join(h.snippet for h in sqli_hits)
        # Verify the actual vulnerable patterns were caught
        assert "SELECT" in snippets_combined or "cursor.execute" in snippets_combined.lower() or "UPDATE" in snippets_combined

    def test_no_false_xss_on_jsonify(self, api_report: SecurityReport) -> None:
        """jsonify() is safe server-side rendering; it should not trigger XSS."""
        xss_hits = api_report.by_check(SecurityCheckType.XSS)
        assert len(xss_hits) == 0

    def test_single_file_scanned(self, api_report: SecurityReport) -> None:
        assert api_report.files_scanned == 1

    def test_all_hits_reference_correct_file(self, api_report: SecurityReport) -> None:
        for hit in api_report.hits:
            assert hit.file == "src/api/v2/inventory.py"


# ── 9. Dependency update PR: unpinned packages ──────────────────────────────


class TestDependencyUpdateScenario:
    """Simulate a PR that updates requirements.txt and package.json with a mix
    of properly pinned and loosely specified dependencies."""

    @pytest.fixture()
    def deps_report(self) -> SecurityReport:
        diffs = [
            # Python requirements with a mix of pinned and unpinned
            _make_diff(
                "requirements.txt",
                [
                    _make_hunk(
                        removed_lines=[
                            "flask==2.3.0",
                            "sqlalchemy==2.0.20",
                        ],
                        added_lines=[
                            "flask>=3.0",
                            "sqlalchemy",
                            "pydantic==2.5.2",
                            "celery~=5.3.0",
                            "redis==4.6.0",
                            "boto3",
                            "cryptography>=41.0",
                        ],
                        new_start=1,
                        context_before=[
                            "# Production dependencies",
                        ],
                    ),
                ],
            ),
            # Development requirements
            _simple_diff(
                "requirements-dev.txt",
                [
                    "pytest==7.4.3",
                    "black==23.11.0",
                    "mypy",
                    "ruff>=0.1.0",
                    "coverage",
                ],
            ),
            # package.json with semver ranges
            _make_diff(
                "package.json",
                [
                    _make_hunk(
                        added_lines=[
                            '    "react": "^18.2.0",',
                            '    "next": "^14.0.3",',
                            '    "typescript": "5.3.2",',
                            '    "tailwindcss": "^3.3.6",',
                        ],
                        new_start=5,
                        context_before=[
                            '  "dependencies": {',
                        ],
                    ),
                ],
            ),
        ]
        return run_surface_scan(diffs)

    def test_unpinned_python_deps_detected(self, deps_report: SecurityReport) -> None:
        """Bare package names and lower-bound-only constraints should be flagged."""
        unpinned = deps_report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        unpinned_in_req = [h for h in unpinned if h.file == "requirements.txt"]
        # flask>=3.0, sqlalchemy (bare), celery~=5.3.0, boto3 (bare), cryptography>=41.0
        assert len(unpinned_in_req) >= 3

    def test_pinned_python_deps_not_flagged(self, deps_report: SecurityReport) -> None:
        """Exact pins (==) should not be flagged."""
        unpinned = deps_report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        snippets = [h.snippet for h in unpinned]
        assert not any("pydantic==2.5.2" in s for s in snippets)
        assert not any("redis==4.6.0" in s for s in snippets)

    def test_unpinned_dev_deps_detected(self, deps_report: SecurityReport) -> None:
        """Dev requirements are also checked for unpinned packages."""
        unpinned = deps_report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        dev_hits = [h for h in unpinned if h.file == "requirements-dev.txt"]
        # mypy (bare), ruff>=0.1.0, coverage (bare)
        assert len(dev_hits) >= 2

    def test_package_json_caret_ranges_detected(self, deps_report: SecurityReport) -> None:
        """Caret ranges (^) in package.json should be flagged."""
        unpinned = deps_report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        pkg_hits = [h for h in unpinned if h.file == "package.json"]
        assert len(pkg_hits) >= 2
        snippets = " ".join(h.snippet for h in pkg_hits)
        assert "^" in snippets

    def test_exact_npm_version_not_flagged(self, deps_report: SecurityReport) -> None:
        """Exact versions in package.json (no ^ or ~) should not be flagged."""
        unpinned = deps_report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        snippets = [h.snippet for h in unpinned]
        assert not any("5.3.2" in s and "typescript" in s for s in snippets)

    def test_no_non_dependency_checks_triggered(self, deps_report: SecurityReport) -> None:
        """A deps-only PR should not trigger secrets, SQLi, XSS, auth, or env checks."""
        assert len(deps_report.by_check(SecurityCheckType.HARDCODED_SECRET)) == 0
        assert len(deps_report.by_check(SecurityCheckType.SQL_INJECTION)) == 0
        assert len(deps_report.by_check(SecurityCheckType.XSS)) == 0
        assert len(deps_report.by_check(SecurityCheckType.MISSING_AUTH)) == 0
        assert len(deps_report.by_check(SecurityCheckType.EXPOSED_ENV)) == 0

    def test_three_files_scanned(self, deps_report: SecurityReport) -> None:
        assert deps_report.files_scanned == 3


# ── 10. Multi-hunk diff with context lines ───────────────────────────────────


class TestMultiHunkWithContext:
    """Verify that the pipeline correctly handles hunks with context and removed
    lines, scanning only added lines and computing line numbers accurately."""

    def test_line_numbers_with_context_and_removals(self) -> None:
        """Added lines after context and removals should have correct line numbers."""
        diff = _make_diff(
            "src/services/auth_service.py",
            [
                _make_hunk(
                    context_before=[
                        "import hashlib",
                        "import os",
                    ],
                    removed_lines=[
                        'SECRET = os.environ.get("SECRET_KEY")',
                    ],
                    added_lines=[
                        'secret_key = "HMAC-SHA256-prod-key-very-secret-12345"',
                    ],
                    new_start=1,
                ),
                _make_hunk(
                    context_before=[
                        "def authenticate(username, password):",
                    ],
                    added_lines=[
                        '    cursor.execute(f"SELECT * FROM users WHERE username = \'{username}\'")',
                    ],
                    new_start=20,
                ),
            ],
        )
        report = run_surface_scan([diff])

        # Hardcoded secret on the added line
        secrets = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert len(secrets) == 1
        assert secrets[0].line == 3  # context(1,2) + added at 3

        # SQL injection in the second hunk
        sqli = report.by_check(SecurityCheckType.SQL_INJECTION)
        assert len(sqli) == 1
        assert sqli[0].line == 21  # context(20) + added at 21

    def test_removed_lines_not_scanned(self) -> None:
        """Removed lines (- prefix) should never produce hits."""
        diff = _make_diff(
            "src/config.py",
            [
                _make_hunk(
                    removed_lines=[
                        'password = "old-insecure-password-that-is-gone"',
                        'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")',
                    ],
                    added_lines=[
                        'password = os.environ.get("DB_PASSWORD")',
                        'cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))',
                    ],
                    new_start=5,
                ),
            ],
        )
        report = run_surface_scan([diff])
        # The added lines are safe: env lookup + parameterized query
        assert not report.has_issues


# ── 11. Hit attribute completeness ──────────────────────────────────────────


class TestHitAttributeCompleteness:
    """Every hit returned by the pipeline should have all required attributes
    populated with meaningful (non-empty) values."""

    def test_every_hit_field_is_populated(self) -> None:
        diffs = [
            _simple_diff(
                "src/core.py",
                [
                    'token = "ghp_realGithubTokenValue1234567890abc"',
                ],
            ),
            _simple_diff(
                "requirements.txt",
                ["numpy"],
            ),
        ]
        report = run_surface_scan(diffs)
        assert report.has_issues

        for hit in report.hits:
            assert isinstance(hit.check, SecurityCheckType), "check must be a SecurityCheckType"
            assert isinstance(hit.file, str) and hit.file, "file must be a non-empty string"
            assert isinstance(hit.line, int) and hit.line > 0, "line must be a positive int"
            assert isinstance(hit.snippet, str) and hit.snippet, "snippet must be non-empty"
            assert isinstance(hit.message, str) and len(hit.message) > 10, "message must be descriptive"
            assert isinstance(hit.fix, str) and len(hit.fix) > 10, "fix must be descriptive"
            assert isinstance(hit.is_free, bool), "is_free must be a bool"

    def test_snippet_is_truncated_to_120_chars(self) -> None:
        """Snippets should never exceed 120 characters."""
        long_line = 'password = "' + "A" * 200 + '"'
        diff = _simple_diff("src/config.py", [long_line])
        report = run_surface_scan([diff])
        for hit in report.hits:
            assert len(hit.snippet) <= 120


# ── 12. Empty and edge-case inputs ──────────────────────────────────────────


class TestEdgeCases:
    """Verify the pipeline handles degenerate inputs gracefully."""

    def test_empty_diff_list(self) -> None:
        report = run_surface_scan([])
        assert not report.has_issues
        assert report.files_scanned == 0
        assert len(report.hits) == 0

    def test_file_with_no_hunks(self) -> None:
        diff = FileDiff(
            filename="src/empty.py",
            status="modified",
            additions=0,
            deletions=0,
            hunks=[],
        )
        report = run_surface_scan([diff])
        assert not report.has_issues
        assert report.files_scanned == 1

    def test_hunk_with_only_context_lines(self) -> None:
        """A hunk with no added lines (only context) should produce zero hits."""
        hunk = DiffHunk(
            header="@@ -1,3 +1,3 @@",
            old_start=1,
            old_lines=3,
            new_start=1,
            new_lines=3,
            lines=[
                " import os",
                " import sys",
                " import json",
            ],
        )
        diff = FileDiff(
            filename="src/imports.py",
            status="modified",
            additions=0,
            deletions=0,
            hunks=[hunk],
        )
        report = run_surface_scan([diff])
        assert not report.has_issues

    def test_single_character_filename(self) -> None:
        """Filenames that are unusual but valid should still be scanned."""
        diff = _simple_diff("a", ['secret = "production-secret-key-val123"'])
        report = run_surface_scan([diff])
        assert report.has_issues
        assert report.hits[0].file == "a"

    def test_deeply_nested_path(self) -> None:
        path = "src/modules/auth/v2/internal/adapters/postgres/queries.py"
        diff = _simple_diff(
            path,
            ['cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'],
        )
        report = run_surface_scan([diff])
        assert report.has_issues
        assert report.hits[0].file == path
