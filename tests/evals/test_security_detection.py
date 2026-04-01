"""Comprehensive AI evaluation suite for RunOwl's security scanner.

Measures precision and recall of all six surface-level security checks against
a golden vulnerability dataset.  Every parametrised case carries a human-readable
ID so CI failures immediately point to the offending sample.

Sections
--------
1. True-positive dataset   (60+ cases, parametrised)
2. True-negative dataset   (40+ cases, parametrised)
3. Precision / recall metrics per check and overall
4. Multi-vulnerability single-file eval
5. False-positive resistance eval (20+ tricky safe samples)
6. Edge cases (empty files, long lines, binary, lock, etc.)
7. Scanner integration eval (multi-file PR simulation)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pytest

from github.models import DiffHunk, FileDiff
from security.checks import (
    check_exposed_env,
    check_hardcoded_secrets,
    check_missing_auth,
    check_sql_injection,
    check_unpinned_dependencies,
    check_xss,
)
from security.models import SecurityCheckType, SecurityHit
from security.scanner import run_surface_scan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _diff_with_status(
    filename: str, added_lines: list[str], status: str = "added"
) -> FileDiff:
    """Build a FileDiff with a custom status (e.g. 'removed')."""
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


@dataclass
class _Sample:
    """A single evaluation sample: code snippet + expected check type."""

    id: str
    filename: str
    lines: list[str]
    check_type: SecurityCheckType

    @property
    def diff(self) -> FileDiff:
        return _diff(self.filename, self.lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TRUE-POSITIVE GOLDEN DATASET  (should be detected)
# ═══════════════════════════════════════════════════════════════════════════════

_TRUE_POSITIVES: list[_Sample] = [
    # ── Hardcoded secrets (12 cases) ─────────────────────────────────────────
    _Sample(
        "secret-password-double-quotes",
        "src/config.py",
        ['password = "SuperSecretP@ss123!"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-jwt-secret",
        "src/auth.py",
        ['JWT_SECRET = "my-jwt-secret-key-2024"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-aws-access-key",
        "src/aws.py",
        ['access_key = "AKIAIOSFODNN7REALACC"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-openai-api-key",
        "src/llm.py",
        ["api_key = 'sk-proj-abc123def456ghi789'"],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-signing-key-rsa",
        "src/crypto.py",
        ['SIGNING_KEY = "-----BEGIN RSA PRIVATE KEY-----MIIBogIBAAJ"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-db-password",
        "src/database.py",
        ['DB_PASSWORD = "p0stgr3s_pr0d_p@ssw0rd"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-client-secret",
        "src/oauth.py",
        ['client_secret = "dGhpcyBpcyBhIHNlY3JldCBrZXk="'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-auth-token",
        "src/api_client.py",
        ['AUTH_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-encryption-key",
        "src/encryption.py",
        ['encryption_key = "AES256-ENCRYPTION-KEY-VALUE-2024"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-private-key",
        "src/keys.py",
        ['PRIVATE_KEY = "MIGfMA0GCSqGSIb3DQEBAQUAA4GN..."'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-password-single-quotes",
        "src/settings.py",
        ["passwd = 'N0t-A-Pl@ceh0lder-P@ss!'"],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "secret-colon-assignment",
        "src/config.py",
        ['secret_key: "production-secret-key-12345"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    # ── SQL injection (11 cases) ─────────────────────────────────────────────
    _Sample(
        "sqli-fstring-select",
        "src/db.py",
        ['cursor.execute(f"SELECT * FROM users WHERE email = \'{email}\'")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-concat-delete",
        "src/db.py",
        ['db.query("DELETE FROM orders WHERE id = " + order_id)'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-percent-format",
        "src/db.py",
        ['cursor.execute("SELECT * FROM t WHERE name = \'%s\'" % name)'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-objects-raw",
        "src/models.py",
        ['Model.objects.raw("SELECT * FROM t WHERE name = \'%s\'" % name)'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-fstring-insert",
        "src/db.py",
        ['cursor.execute(f"INSERT INTO logs (msg) VALUES (\'{message}\')")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-fstring-update",
        "src/db.py",
        ['cursor.execute(f"UPDATE users SET role = \'{role}\' WHERE id = {uid}")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-concat-where",
        "src/db.py",
        ['query("SELECT email FROM accounts WHERE username = \'" + uname + "\'")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-format-call",
        "src/db.py",
        ['cursor.execute("SELECT * FROM items WHERE id = {}".format(item_id))'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-fstring-drop",
        "src/db.py",
        ['cursor.execute(f"DROP TABLE IF EXISTS {table_name}")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-raw-fstring",
        "src/db.py",
        ['raw(f"SELECT COUNT(*) FROM {schema}.users WHERE active = {status}")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "sqli-concat-create",
        "src/db.py",
        ['"CREATE TABLE " + table_name + " (id INT PRIMARY KEY)"'],
        SecurityCheckType.SQL_INJECTION,
    ),
    # ── XSS (11 cases) ──────────────────────────────────────────────────────
    _Sample(
        "xss-innerHTML",
        "src/app.js",
        ["el.innerHTML = userInput;"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-outerHTML",
        "src/app.js",
        ["container.outerHTML = response.data;"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-document-write",
        "src/legacy.js",
        ["document.write(urlParams.get('name'));"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-dangerouslySetInnerHTML",
        "src/Component.jsx",
        ['<div dangerouslySetInnerHTML={{__html: props.content}} />'],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-render-template-string",
        "src/views.py",
        ["return render_template_string(user_template)"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-Markup",
        "src/helpers.py",
        ["return Markup(user_html)"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-Markup-format",
        "src/views.py",
        ["return Markup('<b>{}</b>'.format(user_input))"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-innerHTML-template-literal",
        "src/render.js",
        ["div.innerHTML = `<h1>${title}</h1><p>${body}</p>`;"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-innerHTML-concatenation",
        "src/display.js",
        ['element.innerHTML = "<span>" + name + "</span>";'],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-document-write-variable",
        "src/widget.js",
        ["document.write('<div>' + widgetContent + '</div>');"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "xss-render-template-string-format",
        "src/api.py",
        ['return render_template_string("<p>%s</p>" % comment)'],
        SecurityCheckType.XSS,
    ),
    # ── Missing auth (10 cases) ──────────────────────────────────────────────
    _Sample(
        "auth-bare-post",
        "src/routes.py",
        [
            "@app.post('/admin/delete-user')",
            "def delete_user():",
            "    db.execute('DELETE FROM users WHERE id = ?', (request.json['id'],))",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-bare-get",
        "src/api.py",
        [
            "@app.get('/api/internal/config')",
            "def internal_config():",
            "    return jsonify(app.config)",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-router-put",
        "src/endpoints.py",
        [
            "@router.put('/users/{user_id}/role')",
            "def update_role(user_id: int):",
            "    pass",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-router-delete",
        "src/endpoints.py",
        [
            "@router.delete('/items/{item_id}')",
            "def remove_item(item_id: int):",
            "    Item.objects.filter(id=item_id).delete()",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-blueprint-post",
        "src/views.py",
        [
            "@blueprint.post('/payments/refund')",
            "def refund_payment():",
            "    stripe.Refund.create(charge=request.json['charge_id'])",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-bp-route",
        "src/admin.py",
        [
            "@bp.route('/admin/settings', methods=['POST'])",
            "def update_settings():",
            "    Settings.update(request.form)",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-router-patch",
        "src/users.py",
        [
            "@router.patch('/users/{uid}')",
            "async def patch_user(uid: str):",
            "    await db.users.update_one({'_id': uid}, request.json)",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-app-get-sensitive",
        "src/health.py",
        [
            "@app.get('/debug/env')",
            "def show_env():",
            "    return dict(os.environ)",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-post-upload",
        "src/upload.py",
        [
            "@app.post('/upload')",
            "def upload_file():",
            "    f = request.files['file']",
            "    f.save('/var/uploads/' + f.filename)",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "auth-app-delete",
        "src/resources.py",
        [
            "@app.delete('/resources/{rid}')",
            "def delete_resource(rid):",
            "    Resource.query.get_or_404(rid).delete()",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    # ── Exposed env (10 cases) ───────────────────────────────────────────────
    _Sample(
        "env-print-environ",
        "src/debug.py",
        ['print(os.environ["DATABASE_URL"])'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-logger-info-secret",
        "src/app.py",
        ['logger.info(os.environ["SECRET_KEY"])'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-print-getenv",
        "src/startup.py",
        ['print(os.getenv("API_TOKEN"))'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-logger-debug-password",
        "src/init.py",
        ['logger.debug(os.environ.get("DB_PASSWORD"))'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-console-log-token",
        "src/utils.js",
        ["console.log(process.env.SECRET_TOKEN)"],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-log-api-key",
        "src/bootstrap.py",
        ['log(os.environ["API_KEY"])'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-logger-warning-password",
        "src/checks.py",
        ['logger.warning("DB creds: " + os.environ["PASSWORD"])'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-print-private-key",
        "src/keys.py",
        ['print(os.environ["PRIVATE_KEY"])'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-jsonify-secret",
        "src/api.py",
        ['return jsonify({"key": os.environ["SECRET_KEY"]})'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "env-logger-error-token",
        "src/middleware.py",
        ['logger.error("Token value: " + os.getenv("TOKEN"))'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    # ── Unpinned dependencies (10 cases) ─────────────────────────────────────
    _Sample(
        "dep-bare-requests",
        "requirements.txt",
        ["requests"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-bare-flask",
        "requirements.txt",
        ["flask"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-geq-django",
        "requirements.txt",
        ["django>=4.0"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-compat-release",
        "requirements.txt",
        ["sqlalchemy~=2.0"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-caret-axios",
        "package.json",
        ['"axios": "^1.6.0"'],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-tilde-lodash",
        "package.json",
        ['"lodash": "~4.17.21"'],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-bare-numpy",
        "requirements.txt",
        ["numpy"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-geq-pandas",
        "requirements-dev.txt",
        ["pandas>=1.5.0"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-bare-celery",
        "requirements.txt",
        ["celery"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "dep-caret-react",
        "package.json",
        ['"react": "^18.2.0"'],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
]

# Map check type -> individual check function
_CHECK_FN = {
    SecurityCheckType.HARDCODED_SECRET: check_hardcoded_secrets,
    SecurityCheckType.SQL_INJECTION: check_sql_injection,
    SecurityCheckType.XSS: check_xss,
    SecurityCheckType.MISSING_AUTH: check_missing_auth,
    SecurityCheckType.EXPOSED_ENV: check_exposed_env,
    SecurityCheckType.UNPINNED_DEPENDENCY: check_unpinned_dependencies,
}


class TestTruePositiveDataset:
    """Every sample in the true-positive golden set must produce at least one hit
    of the expected SecurityCheckType."""

    @pytest.mark.parametrize(
        "sample",
        _TRUE_POSITIVES,
        ids=[s.id for s in _TRUE_POSITIVES],
    )
    def test_detected(self, sample: _Sample) -> None:
        fn = _CHECK_FN[sample.check_type]
        hits = fn(sample.diff)
        assert len(hits) >= 1, (
            f"Expected at least one {sample.check_type.value} hit for "
            f"sample '{sample.id}', got 0"
        )

    @pytest.mark.parametrize(
        "sample",
        _TRUE_POSITIVES,
        ids=[s.id for s in _TRUE_POSITIVES],
    )
    def test_correct_check_type(self, sample: _Sample) -> None:
        fn = _CHECK_FN[sample.check_type]
        hits = fn(sample.diff)
        for hit in hits:
            assert hit.check == sample.check_type, (
                f"Hit check type {hit.check} != expected {sample.check_type} "
                f"for sample '{sample.id}'"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TRUE-NEGATIVE GOLDEN DATASET  (should NOT be detected)
# ═══════════════════════════════════════════════════════════════════════════════

_TRUE_NEGATIVES: list[_Sample] = [
    # ── Safe secret patterns (8 cases) ───────────────────────────────────────
    _Sample(
        "safe-secret-env-get",
        "src/config.py",
        ['password = os.environ.get("PASSWORD")'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "safe-secret-config-get",
        "src/config.py",
        ['secret_key = config.get("secret_key")'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "safe-secret-placeholder",
        "src/config.py",
        ['api_key = "your_api_key_here"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "safe-secret-test-file",
        "tests/test_auth.py",
        ['password = "test_password_value"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "safe-secret-short-value",
        "src/config.py",
        ['secret = "ab"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "safe-secret-getenv",
        "src/app.py",
        ['token = os.getenv("AUTH_TOKEN")'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "safe-secret-settings-dot",
        "src/app.py",
        ['api_key = settings.API_KEY'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    _Sample(
        "safe-secret-example-marker",
        "src/config.py",
        ['secret = "example-secret-for-docs"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    # ── Safe SQL patterns (7 cases) ──────────────────────────────────────────
    _Sample(
        "safe-sql-parameterized-qmark",
        "src/db.py",
        ['cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "safe-sql-parameterized-named",
        "src/db.py",
        ['cursor.execute("SELECT * FROM users WHERE id = :id", {"id": uid})'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "safe-sql-orm-filter",
        "src/models.py",
        ["User.objects.filter(email=email).first()"],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "safe-sql-static-query",
        "src/db.py",
        ['cursor.execute("SELECT COUNT(*) FROM users")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "safe-sql-sqlalchemy-text",
        "src/db.py",
        ['session.execute(text("SELECT 1"))'],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "safe-sql-orm-create",
        "src/models.py",
        ["User.objects.create(name=name, email=email)"],
        SecurityCheckType.SQL_INJECTION,
    ),
    _Sample(
        "safe-sql-select-constant",
        "src/db.py",
        ['cursor.execute("SELECT 1")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    # ── Safe XSS patterns (7 cases) ──────────────────────────────────────────
    _Sample(
        "safe-xss-dompurify",
        "src/app.js",
        ["el.innerHTML = DOMPurify.sanitize(userInput);"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "safe-xss-bleach-clean",
        "src/views.py",
        ["return bleach.clean(user_html)"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "safe-xss-escape-fn",
        "src/render.js",
        ["el.innerHTML = escape(rawInput);"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "safe-xss-textContent",
        "src/app.js",
        ["el.textContent = userInput;"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "safe-xss-jinja-template",
        "src/views.py",
        ['return render_template("page.html", data=data)'],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "safe-xss-sanitize-call",
        "src/display.js",
        ["div.innerHTML = sanitize(content);"],
        SecurityCheckType.XSS,
    ),
    _Sample(
        "safe-xss-markupsafe",
        "src/helpers.py",
        ["return markupsafe.escape(user_input)"],
        SecurityCheckType.XSS,
    ),
    # ── Safe auth patterns (7 cases) ─────────────────────────────────────────
    _Sample(
        "safe-auth-login-required",
        "src/routes.py",
        [
            "@login_required",
            "@app.post('/admin/delete')",
            "def delete_user():",
            "    pass",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "safe-auth-current-user",
        "src/routes.py",
        [
            "@app.get('/profile')",
            "def profile():",
            "    user = current_user",
            "    return jsonify(user.to_dict())",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "safe-auth-request-user",
        "src/routes.py",
        [
            "@app.get('/dashboard')",
            "def dashboard():",
            "    if not request.user.is_authenticated:",
            "        abort(401)",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "safe-auth-jwt-required",
        "src/api.py",
        [
            "@jwt_required",
            "@router.get('/api/data')",
            "def get_data():",
            "    return data",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "safe-auth-requires-auth",
        "src/views.py",
        [
            "@requires_auth",
            "@app.post('/transfer')",
            "def transfer():",
            "    pass",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "safe-auth-permission-required",
        "src/admin.py",
        [
            "@permission_required('admin')",
            "@app.delete('/admin/purge')",
            "def purge():",
            "    pass",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    _Sample(
        "safe-auth-get-current-user",
        "src/endpoints.py",
        [
            "@router.get('/me')",
            "def me():",
            "    user = get_current_user()",
            "    return user",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    # ── Safe env patterns (5 cases) ──────────────────────────────────────────
    _Sample(
        "safe-env-assignment",
        "src/config.py",
        ['SECRET_KEY = os.environ.get("SECRET_KEY")'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "safe-env-getenv-assign",
        "src/config.py",
        ['TOKEN = os.getenv("AUTH_TOKEN")'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "safe-env-dict-lookup",
        "src/config.py",
        ['PASSWORD = os.environ["DB_PASSWORD"]'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "safe-env-variable-usage",
        "src/db.py",
        ["conn = psycopg2.connect(password=os.environ['DB_PASSWORD'])"],
        SecurityCheckType.EXPOSED_ENV,
    ),
    _Sample(
        "safe-env-dotenv-load",
        "src/config.py",
        ["load_dotenv()"],
        SecurityCheckType.EXPOSED_ENV,
    ),
    # ── Safe dependency patterns (7 cases) ───────────────────────────────────
    _Sample(
        "safe-dep-pinned-requests",
        "requirements.txt",
        ["requests==2.31.0"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "safe-dep-pinned-flask",
        "requirements.txt",
        ["flask==3.0.0"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "safe-dep-pinned-django",
        "requirements.txt",
        ["django==4.2.7"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "safe-dep-comment",
        "requirements.txt",
        ["# This is a comment"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "safe-dep-blank-line",
        "requirements.txt",
        [""],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "safe-dep-not-req-file",
        "src/deps.py",
        ["requests>=2.0"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    _Sample(
        "safe-dep-pinned-numpy",
        "requirements.txt",
        ["numpy==1.26.2"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
]


class TestTrueNegativeDataset:
    """Every sample in the true-negative set must produce zero hits for its
    associated check type."""

    @pytest.mark.parametrize(
        "sample",
        _TRUE_NEGATIVES,
        ids=[s.id for s in _TRUE_NEGATIVES],
    )
    def test_not_detected(self, sample: _Sample) -> None:
        fn = _CHECK_FN[sample.check_type]
        hits = fn(sample.diff)
        assert len(hits) == 0, (
            f"Expected 0 hits for safe sample '{sample.id}', "
            f"got {len(hits)}: {[h.snippet for h in hits]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PRECISION / RECALL METRICS
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrecisionRecall:
    """Run every golden sample through run_surface_scan and compute per-check
    precision, recall, and overall accuracy.  Assert minimum thresholds."""

    PRECISION_THRESHOLD = 0.85
    RECALL_THRESHOLD = 0.85

    @staticmethod
    def _evaluate() -> (
        tuple[
            dict[SecurityCheckType, dict[str, int]],
            dict[SecurityCheckType, float],
            dict[SecurityCheckType, float],
        ]
    ):
        """Compute TP, FP, FN, precision, and recall per check type."""
        counts: dict[SecurityCheckType, dict[str, int]] = {
            ct: {"tp": 0, "fp": 0, "fn": 0} for ct in SecurityCheckType
        }

        # True positives / false negatives
        for sample in _TRUE_POSITIVES:
            report = run_surface_scan([sample.diff])
            matched = any(h.check == sample.check_type for h in report.hits)
            if matched:
                counts[sample.check_type]["tp"] += 1
            else:
                counts[sample.check_type]["fn"] += 1

        # True negatives / false positives
        for sample in _TRUE_NEGATIVES:
            report = run_surface_scan([sample.diff])
            falsely_flagged = any(h.check == sample.check_type for h in report.hits)
            if falsely_flagged:
                counts[sample.check_type]["fp"] += 1

        precision: dict[SecurityCheckType, float] = {}
        recall: dict[SecurityCheckType, float] = {}
        for ct in SecurityCheckType:
            tp = counts[ct]["tp"]
            fp = counts[ct]["fp"]
            fn = counts[ct]["fn"]
            precision[ct] = tp / (tp + fp) if (tp + fp) > 0 else 1.0
            recall[ct] = tp / (tp + fn) if (tp + fn) > 0 else 1.0

        return counts, precision, recall

    def test_per_check_precision(self) -> None:
        _, precision, _ = self._evaluate()
        for ct, p in precision.items():
            assert p >= self.PRECISION_THRESHOLD, (
                f"Precision for {ct.value} = {p:.2f} < {self.PRECISION_THRESHOLD}"
            )

    def test_per_check_recall(self) -> None:
        _, _, recall = self._evaluate()
        for ct, r in recall.items():
            assert r >= self.RECALL_THRESHOLD, (
                f"Recall for {ct.value} = {r:.2f} < {self.RECALL_THRESHOLD}"
            )

    def test_overall_accuracy(self) -> None:
        counts, _, _ = self._evaluate()
        total_tp = sum(c["tp"] for c in counts.values())
        total_fp = sum(c["fp"] for c in counts.values())
        total_fn = sum(c["fn"] for c in counts.values())
        total_correct = total_tp
        total_samples = total_tp + total_fp + total_fn
        accuracy = total_correct / total_samples if total_samples > 0 else 1.0
        assert accuracy >= 0.85, f"Overall accuracy = {accuracy:.2f} < 0.85"

    def test_combined_f1(self) -> None:
        """Micro-averaged F1 across all check types."""
        counts, _, _ = self._evaluate()
        total_tp = sum(c["tp"] for c in counts.values())
        total_fp = sum(c["fp"] for c in counts.values())
        total_fn = sum(c["fn"] for c in counts.values())
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        assert f1 >= 0.85, f"Micro-F1 = {f1:.2f} < 0.85"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MULTI-VULNERABILITY SINGLE-FILE EVAL
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiVulnerabilityFile:
    """A single realistic file containing 5+ different vulnerability types.
    Verify all are detected with correct line numbers."""

    MULTI_VULN_LINES = [
        "import os",                                                    # line 1
        "from flask import Flask, request, jsonify, render_template_string",  # line 2
        "",                                                             # line 3
        "app = Flask(__name__)",                                        # line 4
        'DB_PASSWORD = "pr0duction_p@ssw0rd_2024!"',                    # line 5 - SECRET
        "",                                                             # line 6
        "@app.get('/api/users')",                                       # line 7 - MISSING_AUTH
        "def list_users():",                                            # line 8
        '    cursor.execute(f"SELECT * FROM users WHERE role = {user_role}")',  # line 9 - SQL_INJECTION
        "    return jsonify(cursor.fetchall())",                        # line 10
        "",                                                             # line 11
        "@app.post('/render')",                                         # line 12 - MISSING_AUTH (also)
        "def render_page():",                                           # line 13
        "    template = request.form['template']",                      # line 14
        "    return render_template_string(template)",                   # line 15 - XSS
        "",                                                             # line 16
        "if __name__ == '__main__':",                                   # line 17
        '    logger.info(os.environ["SECRET_KEY"])',                    # line 18 - EXPOSED_ENV
        "    app.run(debug=True)",                                      # line 19
    ]

    @pytest.fixture()
    def report(self) -> "from security.models import SecurityReport":
        diff = _diff("src/app.py", self.MULTI_VULN_LINES)
        return run_surface_scan([diff])

    def test_all_five_check_types_found(self, report) -> None:
        check_types = {h.check for h in report.hits}
        assert SecurityCheckType.HARDCODED_SECRET in check_types
        assert SecurityCheckType.SQL_INJECTION in check_types
        assert SecurityCheckType.XSS in check_types
        assert SecurityCheckType.MISSING_AUTH in check_types
        assert SecurityCheckType.EXPOSED_ENV in check_types

    def test_secret_on_correct_line(self, report) -> None:
        secrets = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert any(h.line == 5 for h in secrets), (
            f"Expected secret on line 5, got lines {[h.line for h in secrets]}"
        )

    def test_sql_injection_on_correct_line(self, report) -> None:
        sqli = report.by_check(SecurityCheckType.SQL_INJECTION)
        assert any(h.line == 9 for h in sqli), (
            f"Expected SQLi on line 9, got lines {[h.line for h in sqli]}"
        )

    def test_xss_on_correct_line(self, report) -> None:
        xss = report.by_check(SecurityCheckType.XSS)
        assert any(h.line == 15 for h in xss), (
            f"Expected XSS on line 15, got lines {[h.line for h in xss]}"
        )

    def test_missing_auth_on_correct_line(self, report) -> None:
        auth = report.by_check(SecurityCheckType.MISSING_AUTH)
        assert any(h.line == 7 for h in auth), (
            f"Expected missing auth on line 7, got lines {[h.line for h in auth]}"
        )

    def test_exposed_env_on_correct_line(self, report) -> None:
        env = report.by_check(SecurityCheckType.EXPOSED_ENV)
        assert any(h.line == 18 for h in env), (
            f"Expected exposed env on line 18, got lines {[h.line for h in env]}"
        )

    def test_no_false_negatives_in_multi_vuln(self, report) -> None:
        """At least 5 distinct check types should appear in the report."""
        assert len({h.check for h in report.hits}) >= 5

    def test_files_scanned_is_one(self, report) -> None:
        assert report.files_scanned == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FALSE-POSITIVE RESISTANCE EVAL
# ═══════════════════════════════════════════════════════════════════════════════

_FALSE_POSITIVE_SAMPLES: list[tuple[str, str, list[str], SecurityCheckType]] = [
    # ── Looks like a secret, but is not ──────────────────────────────────────
    (
        "fp-resist-bcrypt-hash",
        "src/auth.py",
        ["password_hash = bcrypt.generate_password_hash(password)"],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    (
        "fp-resist-password-variable-no-string",
        "src/auth.py",
        ["password = get_password_from_vault()"],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    (
        "fp-resist-env-lookup-token",
        "src/config.py",
        ['token = os.environ["AUTH_TOKEN"]'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    (
        "fp-resist-mock-secret",
        "tests/conftest.py",
        ['mock_api_key = "fake_key_for_testing"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    (
        "fp-resist-placeholder-angle-bracket",
        "src/config.py",
        ['api_key = "<your-api-key>"'],
        SecurityCheckType.HARDCODED_SECRET,
    ),
    # ── Looks like SQL injection, but is not ─────────────────────────────────
    (
        "fp-resist-sql-comment",
        "src/db.py",
        ["# TODO: fix potential sql injection vulnerability here"],
        SecurityCheckType.SQL_INJECTION,
    ),
    (
        "fp-resist-sql-static",
        "src/db.py",
        ['cursor.execute("SELECT 1")'],
        SecurityCheckType.SQL_INJECTION,
    ),
    (
        "fp-resist-sql-parameterized-tuple",
        "src/db.py",
        ['cursor.execute("INSERT INTO log (msg) VALUES (?)", (msg,))'],
        SecurityCheckType.SQL_INJECTION,
    ),
    (
        "fp-resist-sql-orm-query",
        "src/models.py",
        ['User.query.filter_by(email=email).first()'],
        SecurityCheckType.SQL_INJECTION,
    ),
    (
        "fp-resist-sql-string-variable-name",
        "src/utils.py",
        ['sql_injection_protection = True'],
        SecurityCheckType.SQL_INJECTION,
    ),
    # ── Looks like XSS, but is not ──────────────────────────────────────────
    (
        "fp-resist-xss-escape-helper",
        "src/app.js",
        ["el.innerHTML = escapeHTML(userContent);"],
        SecurityCheckType.XSS,
    ),
    (
        "fp-resist-xss-sanitize-wrapper",
        "src/render.js",
        ["output.innerHTML = sanitize(userContent);"],
        SecurityCheckType.XSS,
    ),
    (
        "fp-resist-xss-bleach-markup",
        "src/views.py",
        ["safe_html = bleach.clean(Markup(raw_html))"],
        SecurityCheckType.XSS,
    ),
    (
        "fp-resist-xss-dompurify-outer",
        "src/app.js",
        ["el.outerHTML = DOMPurify.sanitize(data);"],
        SecurityCheckType.XSS,
    ),
    # ── Looks like missing auth, but is not ──────────────────────────────────
    (
        "fp-resist-auth-with-decorator",
        "src/api.py",
        [
            "@login_required",
            "@app.get('/admin/panel')",
            "def admin_panel():",
            "    return render_template('admin.html')",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    (
        "fp-resist-auth-verify-token",
        "src/api.py",
        [
            "@verify_token",
            "@router.post('/api/submit')",
            "def submit():",
            "    pass",
        ],
        SecurityCheckType.MISSING_AUTH,
    ),
    # ── Looks like exposed env, but is not ───────────────────────────────────
    (
        "fp-resist-env-assignment-only",
        "src/config.py",
        ['SECRET_KEY = os.environ.get("SECRET_KEY")'],
        SecurityCheckType.EXPOSED_ENV,
    ),
    (
        "fp-resist-env-password-connect",
        "src/db.py",
        ["engine = create_engine(f'postgresql://user:{os.environ[\"PASSWORD\"]}@host/db')"],
        SecurityCheckType.EXPOSED_ENV,
    ),
    # ── Looks like unpinned dep, but is not ──────────────────────────────────
    (
        "fp-resist-dep-pinned-exact",
        "requirements.txt",
        ["cryptography==41.0.4"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    (
        "fp-resist-dep-not-requirements-file",
        "src/install.py",
        ["flask"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
    (
        "fp-resist-dep-comment-line",
        "requirements.txt",
        ["# flask>=2.0"],
        SecurityCheckType.UNPINNED_DEPENDENCY,
    ),
]


class TestFalsePositiveResistance:
    """Tricky code that looks suspicious but should NOT be flagged."""

    @pytest.mark.parametrize(
        "sample_id, filename, lines, check_type",
        _FALSE_POSITIVE_SAMPLES,
        ids=[s[0] for s in _FALSE_POSITIVE_SAMPLES],
    )
    def test_not_flagged(
        self,
        sample_id: str,
        filename: str,
        lines: list[str],
        check_type: SecurityCheckType,
    ) -> None:
        diff = _diff(filename, lines)
        fn = _CHECK_FN[check_type]
        hits = fn(diff)
        assert len(hits) == 0, (
            f"False positive for '{sample_id}': expected 0 hits, "
            f"got {len(hits)} — {[h.snippet for h in hits]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Unusual inputs that should not crash or produce incorrect results."""

    def test_empty_file(self) -> None:
        diff = _diff("src/empty.py", [])
        report = run_surface_scan([diff])
        assert report.files_scanned == 1
        assert not report.has_issues

    def test_file_with_only_removed_lines(self) -> None:
        """A file whose status is 'removed' should be entirely skipped."""
        diff = _diff_with_status(
            "src/old.py",
            ['password = "leaked_secret_value"'],
            status="removed",
        )
        report = run_surface_scan([diff])
        assert report.files_scanned == 0
        assert not report.has_issues

    def test_binary_file_skipped(self) -> None:
        diff = _diff("assets/logo.png", ['password = "hidden_in_binary"'])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_lock_file_skipped(self) -> None:
        diff = _diff("poetry.lock", ['"requests": "^2.0"'])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_min_js_skipped(self) -> None:
        diff = _diff("dist/bundle.min.js", ["el.innerHTML = x"])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_very_long_line(self) -> None:
        """Lines exceeding 1000 characters should still be scanned and snippet truncated."""
        long_val = "A" * 1000
        line = f'api_key = "{long_val}"'
        diff = _diff("src/config.py", [line])
        hits = check_hardcoded_secrets(diff)
        assert len(hits) >= 1
        assert len(hits[0].snippet) <= 120  # truncation works

    def test_multiple_vulnerabilities_on_same_line(self) -> None:
        """A single line may trigger two different check types."""
        # This line contains both a hardcoded secret AND an exposed env pattern
        # We craft a line that matches at least one clearly:
        line = 'logger.info(os.environ["SECRET_KEY"]); password = "hardcoded_value!"'
        diff = _diff("src/app.py", [line])
        report = run_surface_scan([diff])
        check_types = {h.check for h in report.hits}
        # At minimum the exposed env should be detected
        assert SecurityCheckType.EXPOSED_ENV in check_types

    def test_nested_quotes_in_secret(self) -> None:
        """Secrets containing nested/escaped quotes."""
        diff = _diff("src/config.py", [r"password = \"real\\\"pass\\\"word\""])
        # Should not crash; detection is best-effort
        hits = check_hardcoded_secrets(diff)
        # Just assert no exception; detection is a bonus
        assert isinstance(hits, list)

    def test_multiline_sql_fstring_first_line(self) -> None:
        """First line of a multi-line f-string SQL query."""
        diff = _diff(
            "src/db.py",
            [
                'cursor.execute(f"SELECT *',
                "    FROM users",
                "    WHERE email = '{email}'",
                '")',
            ],
        )
        # The first line has cursor.execute(f" — some patterns may match
        hits = check_sql_injection(diff)
        # Just assert no crash
        assert isinstance(hits, list)

    def test_empty_hunks(self) -> None:
        """A diff with an empty hunk list should not crash."""
        diff = FileDiff(
            filename="src/nothing.py",
            status="modified",
            additions=0,
            deletions=0,
            hunks=[],
        )
        report = run_surface_scan([diff])
        assert report.files_scanned == 1
        assert not report.has_issues

    def test_hunk_with_context_lines(self) -> None:
        """Hunks containing context lines (no +/- prefix) should be ignored."""
        hunk = DiffHunk(
            header="@@ -1,3 +1,4 @@",
            old_start=1,
            old_lines=3,
            new_start=1,
            new_lines=4,
            lines=[
                " import os",
                "+password = \"new_secret_value!\"",
                " x = 1",
                " y = 2",
            ],
        )
        diff = FileDiff(
            filename="src/config.py",
            status="modified",
            additions=1,
            deletions=0,
            hunks=[hunk],
        )
        hits = check_hardcoded_secrets(diff)
        assert len(hits) == 1
        # Context lines (without +) should not produce hits
        assert hits[0].line == 2

    def test_removed_diff_lines_not_scanned(self) -> None:
        """Lines starting with '-' in a hunk should be ignored."""
        hunk = DiffHunk(
            header="@@ -1,2 +1,2 @@",
            old_start=1,
            old_lines=2,
            new_start=1,
            new_lines=2,
            lines=[
                '-password = "old_secret"',
                '+password = os.environ["PASSWORD"]',
            ],
        )
        diff = FileDiff(
            filename="src/config.py",
            status="modified",
            additions=1,
            deletions=1,
            hunks=[hunk],
        )
        hits = check_hardcoded_secrets(diff)
        assert len(hits) == 0  # Old secret was removed, new line is safe

    def test_map_file_skipped(self) -> None:
        diff = _diff("dist/app.js.map", ['password = "leaked"'])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_package_lock_json_skipped(self) -> None:
        diff = _diff("package-lock.json", ['"lodash": "^4.17.21"'])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_yarn_lock_skipped(self) -> None:
        diff = _diff("yarn.lock", ["some-package@^1.0.0:"])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_uv_lock_skipped(self) -> None:
        diff = _diff("uv.lock", ["requests>=2.0"])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_svg_file_skipped(self) -> None:
        diff = _diff("icons/logo.svg", ['<script>document.write("xss")</script>'])
        report = run_surface_scan([diff])
        assert report.files_scanned == 0

    def test_diff_start_at_high_line_number(self) -> None:
        """Ensure line numbers are correct when the hunk starts mid-file."""
        diff = _diff("src/config.py", ['api_key = "real-api-key-1234"'], start=500)
        hits = check_hardcoded_secrets(diff)
        assert len(hits) == 1
        assert hits[0].line == 500

    def test_hit_snippet_never_exceeds_120_chars(self) -> None:
        """Regardless of line length, snippet is capped at 120."""
        long_secret = "X" * 200
        diff = _diff("src/config.py", [f'secret_key = "{long_secret}"'])
        hits = check_hardcoded_secrets(diff)
        assert len(hits) >= 1
        assert len(hits[0].snippet) <= 120


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SCANNER INTEGRATION EVAL  (multi-file PR simulation)
# ═══════════════════════════════════════════════════════════════════════════════


class TestScannerIntegration:
    """Simulate a realistic multi-file PR and verify scanner behaviour end-to-end."""

    @pytest.fixture()
    def multi_file_pr(self) -> list[FileDiff]:
        """A 9-file PR: 5 scanned, 4 skipped."""
        return [
            # File 1: Python config with a secret
            _diff("src/config.py", [
                'DB_PASSWORD = "pr0d_p@ss_2024!"',
                'REDIS_URL = os.environ.get("REDIS_URL")',
            ]),
            # File 2: Python routes with missing auth + SQL injection
            _diff("src/routes.py", [
                "from flask import Flask, request",
                "app = Flask(__name__)",
                "@app.get('/api/search')",
                "def search():",
                '    q = request.args.get("q")',
                '    cursor.execute(f"SELECT * FROM products WHERE name LIKE \'%{q}%\'")',
                "    return jsonify(cursor.fetchall())",
            ]),
            # File 3: JavaScript with XSS
            _diff("src/components/Display.jsx", [
                "function Display({ html }) {",
                "    return <div dangerouslySetInnerHTML={{__html: html}} />;",
                "}",
            ]),
            # File 4: requirements.txt with unpinned deps
            _diff("requirements.txt", [
                "flask==3.0.0",
                "requests",
                "sqlalchemy>=2.0",
                "pytest==7.4.3",
            ]),
            # File 5: Debug module exposing env
            _diff("src/debug.py", [
                "import os, logging",
                "logger = logging.getLogger(__name__)",
                'logger.info(os.environ["SECRET_KEY"])',
            ]),
            # ── Skipped files ────────────────────────────────────────────────
            # File 6: Removed file
            _diff_with_status(
                "src/old_config.py",
                ['password = "old_leaked_secret"'],
                status="removed",
            ),
            # File 7: Binary image
            _diff("assets/hero.png", ["binary content here"]),
            # File 8: Lock file
            _diff("package-lock.json", ['"express": "^4.18.0"']),
            # File 9: Source map
            _diff("dist/bundle.js.map", ['password = "minified_leak"']),
        ]

    @pytest.fixture()
    def report(self, multi_file_pr) -> "from security.models import SecurityReport":
        return run_surface_scan(multi_file_pr)

    def test_files_scanned_count(self, report) -> None:
        """Only non-skipped, non-removed files should be counted."""
        assert report.files_scanned == 5

    def test_skipped_files_produce_no_hits(self, report) -> None:
        skipped_files = {
            "src/old_config.py",
            "assets/hero.png",
            "package-lock.json",
            "dist/bundle.js.map",
        }
        for hit in report.hits:
            assert hit.file not in skipped_files, (
                f"Hit found in skipped file: {hit.file}"
            )

    def test_secret_detected_in_config(self, report) -> None:
        secrets = report.by_check(SecurityCheckType.HARDCODED_SECRET)
        assert any(h.file == "src/config.py" for h in secrets)

    def test_sqli_detected_in_routes(self, report) -> None:
        sqli = report.by_check(SecurityCheckType.SQL_INJECTION)
        assert any(h.file == "src/routes.py" for h in sqli)

    def test_missing_auth_detected_in_routes(self, report) -> None:
        auth = report.by_check(SecurityCheckType.MISSING_AUTH)
        assert any(h.file == "src/routes.py" for h in auth)

    def test_xss_detected_in_jsx(self, report) -> None:
        xss = report.by_check(SecurityCheckType.XSS)
        assert any(h.file == "src/components/Display.jsx" for h in xss)

    def test_unpinned_deps_detected(self, report) -> None:
        deps = report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        snippets = {h.snippet for h in deps}
        assert any("requests" in s for s in snippets)

    def test_pinned_dep_not_flagged(self, report) -> None:
        deps = report.by_check(SecurityCheckType.UNPINNED_DEPENDENCY)
        for h in deps:
            assert "flask==3.0.0" not in h.snippet
            assert "pytest==7.4.3" not in h.snippet

    def test_exposed_env_detected(self, report) -> None:
        env = report.by_check(SecurityCheckType.EXPOSED_ENV)
        assert any(h.file == "src/debug.py" for h in env)

    def test_deduplication(self, report, multi_file_pr) -> None:
        """Passing the same PR twice should still deduplicate."""
        double_report = run_surface_scan(multi_file_pr + multi_file_pr)
        unique_keys = {(h.file, h.line, h.check) for h in double_report.hits}
        assert len(double_report.hits) == len(unique_keys)

    def test_all_hit_attributes_populated(self, report) -> None:
        """Every hit must have all required attributes fully populated."""
        for hit in report.hits:
            assert isinstance(hit.check, SecurityCheckType), "check must be a SecurityCheckType"
            assert hit.file, "file must be non-empty"
            assert isinstance(hit.line, int) and hit.line >= 1, "line must be a positive int"
            assert hit.snippet, "snippet must be non-empty"
            assert hit.message, "message must be non-empty"
            assert hit.fix, "fix must be non-empty"
            assert isinstance(hit.is_free, bool), "is_free must be a bool"
            assert hit.citation == f"{hit.file}:{hit.line}", "citation format must be file:line"

    def test_hit_citation_format(self, report) -> None:
        for hit in report.hits:
            assert ":" in hit.citation
            parts = hit.citation.split(":")
            assert len(parts) == 2
            assert parts[1].isdigit()

    def test_report_by_check_covers_all_types(self, report) -> None:
        """The PR was designed so every check type fires at least once."""
        found_types = {h.check for h in report.hits}
        assert SecurityCheckType.HARDCODED_SECRET in found_types
        assert SecurityCheckType.SQL_INJECTION in found_types
        assert SecurityCheckType.XSS in found_types
        assert SecurityCheckType.MISSING_AUTH in found_types
        assert SecurityCheckType.EXPOSED_ENV in found_types
        assert SecurityCheckType.UNPINNED_DEPENDENCY in found_types

    def test_report_has_issues_flag(self, report) -> None:
        assert report.has_issues is True

    def test_empty_pr(self) -> None:
        report = run_surface_scan([])
        assert report.files_scanned == 0
        assert not report.has_issues
        assert report.hits == []
