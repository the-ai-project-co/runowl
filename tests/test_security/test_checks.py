"""Tests for surface-level security checks."""

from github.models import DiffHunk, FileDiff
from security.checks import (
    check_exposed_env,
    check_hardcoded_secrets,
    check_missing_auth,
    check_sql_injection,
    check_unpinned_dependencies,
    check_xss,
)
from security.models import SecurityCheckType


def _diff(filename: str, added_lines: list[str], start: int = 1) -> FileDiff:
    """Build a minimal FileDiff with the given added lines."""
    raw = [f"+{line}" for line in added_lines]
    hunk = DiffHunk(
        header=f"@@ -0,0 +{start},{len(added_lines)} @@",
        old_start=0,
        old_lines=0,
        new_start=start,
        new_lines=len(added_lines),
        lines=raw,
    )
    return FileDiff(
        filename=filename,
        status="added",
        additions=len(added_lines),
        deletions=0,
        hunks=[hunk],
    )


# ── Hardcoded secrets ─────────────────────────────────────────────────────────


class TestHardcodedSecrets:
    def test_detects_password_assignment(self) -> None:
        diff = _diff("src/config.py", ['password = "super_secret_123"'])
        assert check_hardcoded_secrets(diff)

    def test_detects_api_key(self) -> None:
        diff = _diff("src/config.py", ['API_KEY = "sk-abc123xyz"'])
        assert check_hardcoded_secrets(diff)

    def test_detects_jwt_secret(self) -> None:
        diff = _diff("src/auth.py", ['jwt_secret = "my-hard-coded-secret"'])
        assert check_hardcoded_secrets(diff)

    def test_ignores_env_var_lookup(self) -> None:
        diff = _diff("src/config.py", ['password = os.environ.get("PASSWORD")'])
        assert not check_hardcoded_secrets(diff)

    def test_ignores_placeholder(self) -> None:
        diff = _diff("src/config.py", ['password = "your_password_here"'])
        assert not check_hardcoded_secrets(diff)

    def test_ignores_test_file_mock(self) -> None:
        diff = _diff("tests/test_auth.py", ['password = "test_password"'])
        assert not check_hardcoded_secrets(diff)

    def test_ignores_short_value(self) -> None:
        # Values under 4 chars are too short to be real secrets
        diff = _diff("src/config.py", ['secret = "ab"'])
        assert not check_hardcoded_secrets(diff)

    def test_check_type_correct(self) -> None:
        diff = _diff("src/config.py", ['api_key = "real-api-key-here"'])
        hits = check_hardcoded_secrets(diff)
        assert hits[0].check == SecurityCheckType.HARDCODED_SECRET


# ── SQL injection ─────────────────────────────────────────────────────────────


class TestSQLInjection:
    def test_detects_f_string_query(self) -> None:
        diff = _diff("src/db.py", ['cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'])
        assert check_sql_injection(diff)

    def test_detects_string_concat(self) -> None:
        diff = _diff("src/db.py", ['query = "SELECT * FROM users WHERE name = \'" + name + "\'"'])
        assert check_sql_injection(diff)

    def test_detects_percent_format(self) -> None:
        diff = _diff("src/db.py", ['db.execute("SELECT * FROM t WHERE id = %s" % user_id)'])
        assert check_sql_injection(diff)

    def test_safe_parameterized_query_not_flagged(self) -> None:
        diff = _diff(
            "src/db.py", ['cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))']
        )
        assert not check_sql_injection(diff)

    def test_check_type_correct(self) -> None:
        diff = _diff("src/db.py", ['db.raw("DELETE FROM t WHERE id=" + uid)'])
        hits = check_sql_injection(diff)
        assert hits[0].check == SecurityCheckType.SQL_INJECTION


# ── XSS ───────────────────────────────────────────────────────────────────────


class TestXSS:
    def test_detects_inner_html(self) -> None:
        diff = _diff("src/app.js", ["el.innerHTML = userInput"])
        assert check_xss(diff)

    def test_detects_document_write(self) -> None:
        diff = _diff("src/app.js", ["document.write(data)"])
        assert check_xss(diff)

    def test_detects_dangerous_set_inner_html(self) -> None:
        diff = _diff("src/App.jsx", ["<div dangerouslySetInnerHTML={{__html: content}} />"])
        assert check_xss(diff)

    def test_detects_render_template_string(self) -> None:
        diff = _diff("src/views.py", ["return render_template_string(user_template)"])
        assert check_xss(diff)

    def test_safe_with_dompurify(self) -> None:
        diff = _diff("src/app.js", ["el.innerHTML = DOMPurify.sanitize(userInput)"])
        assert not check_xss(diff)

    def test_check_type_correct(self) -> None:
        diff = _diff("src/app.js", ["div.innerHTML = val"])
        hits = check_xss(diff)
        assert hits[0].check == SecurityCheckType.XSS


# ── Missing auth ──────────────────────────────────────────────────────────────


class TestMissingAuth:
    def test_detects_unprotected_route(self) -> None:
        diff = _diff(
            "src/routes.py",
            [
                "@app.post('/admin/delete')",
                "def delete_user():",
                "    user_id = request.json['id']",
                "    db.delete(user_id)",
            ],
        )
        assert check_missing_auth(diff)

    def test_protected_route_not_flagged(self) -> None:
        diff = _diff(
            "src/routes.py",
            [
                "@login_required",
                "@app.post('/admin/delete')",
                "def delete_user():",
                "    user_id = request.json['id']",
            ],
        )
        assert not check_missing_auth(diff)

    def test_route_with_current_user_not_flagged(self) -> None:
        diff = _diff(
            "src/routes.py",
            [
                "@app.get('/profile')",
                "def profile():",
                "    user = current_user",
                "    return user.data",
            ],
        )
        assert not check_missing_auth(diff)

    def test_check_type_correct(self) -> None:
        diff = _diff(
            "src/routes.py",
            ["@router.get('/secret')", "def secret(): pass"],
        )
        hits = check_missing_auth(diff)
        assert hits[0].check == SecurityCheckType.MISSING_AUTH


# ── Exposed env ───────────────────────────────────────────────────────────────


class TestExposedEnv:
    def test_detects_logged_secret(self) -> None:
        diff = _diff("src/app.py", ['logger.info(os.environ["SECRET_KEY"])'])
        assert check_exposed_env(diff)

    def test_detects_printed_token(self) -> None:
        diff = _diff("src/debug.py", ['print(os.getenv("API_TOKEN"))'])
        assert check_exposed_env(diff)

    def test_safe_assignment_not_flagged(self) -> None:
        diff = _diff("src/config.py", ['SECRET = os.environ.get("SECRET_KEY")'])
        assert not check_exposed_env(diff)

    def test_check_type_correct(self) -> None:
        diff = _diff("src/app.py", ['print(os.environ["PASSWORD"])'])
        hits = check_exposed_env(diff)
        assert hits[0].check == SecurityCheckType.EXPOSED_ENV


# ── Unpinned dependencies ─────────────────────────────────────────────────────


class TestUnpinnedDependencies:
    def test_detects_bare_package(self) -> None:
        diff = _diff("requirements.txt", ["requests"])
        assert check_unpinned_dependencies(diff)

    def test_detects_lower_bound_only(self) -> None:
        diff = _diff("requirements.txt", ["requests>=2.0.0"])
        assert check_unpinned_dependencies(diff)

    def test_pinned_version_not_flagged(self) -> None:
        diff = _diff("requirements.txt", ["requests==2.31.0"])
        assert not check_unpinned_dependencies(diff)

    def test_non_requirements_file_not_checked(self) -> None:
        diff = _diff("src/app.py", ["requests>=2.0.0"])
        assert not check_unpinned_dependencies(diff)

    def test_package_json_caret_version_flagged(self) -> None:
        diff = _diff("package.json", ['"axios": "^1.4.0"'])
        assert check_unpinned_dependencies(diff)

    def test_comments_ignored(self) -> None:
        diff = _diff("requirements.txt", ["# requests>=2.0.0"])
        assert not check_unpinned_dependencies(diff)

    def test_check_type_correct(self) -> None:
        diff = _diff("requirements.txt", ["flask"])
        hits = check_unpinned_dependencies(diff)
        assert hits[0].check == SecurityCheckType.UNPINNED_DEPENDENCY
