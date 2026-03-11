"""Surface-level security checks (free tier).

Each check scans diff lines for a specific vulnerability pattern.
Checks operate on the raw diff lines (+ lines only — new code introduced by the PR).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from github.models import FileDiff
from security.models import SecurityCheckType, SecurityHit

# ── Helpers ───────────────────────────────────────────────────────────────────


def _added_lines(diff: FileDiff) -> list[tuple[int, str]]:
    """Return (line_number, content) for all added lines in a diff."""
    result = []
    for hunk in diff.hunks:
        current = hunk.new_start
        for line in hunk.lines:
            if line.startswith("+"):
                result.append((current, line[1:]))  # strip leading +
            if not line.startswith("-"):
                current += 1
    return result


def _match_lines(
    diff: FileDiff,
    pattern: re.Pattern[str],
    check: SecurityCheckType,
    message_fn: Callable[[str], str],
    fix: str,
) -> list[SecurityHit]:
    hits = []
    for lineno, content in _added_lines(diff):
        if pattern.search(content):
            hits.append(
                SecurityHit(
                    check=check,
                    file=diff.filename,
                    line=lineno,
                    snippet=content.strip()[:120],
                    message=message_fn(content),
                    fix=fix,
                )
            )
    return hits


# ── Check 1: Hardcoded secrets ────────────────────────────────────────────────

# Matches common secret assignment patterns:
#   password = "abc123"
#   API_KEY = 'xyz'
#   secret_key: "..."
#   token = "..."
_SECRET_PATTERN = re.compile(
    r"""(?xi)
    (?:password|passwd|secret[_\-]?key|secret|api[_\-]?key|token|
       auth[_\-]?token|private[_\-]?key|access[_\-]?key|
       client[_\-]?secret|jwt[_\-]?secret|signing[_\-]?key|
       encryption[_\-]?key)
    \s*[:=]\s*
    (?P<quote>['\"]).{4,}(?P=quote)
    """,
    re.IGNORECASE,
)

# Exclusions — test files and placeholder values are likely false positives
_SECRET_EXCLUSIONS = re.compile(
    r"""(?xi)
    (?:test|mock|fake|placeholder|example|dummy|your[_\-]|<|os\.environ|
       getenv|environ\.get|config\.get|settings\.)
    """,
    re.IGNORECASE,
)


def check_hardcoded_secrets(diff: FileDiff) -> list[SecurityHit]:
    hits = []
    for lineno, content in _added_lines(diff):
        if _SECRET_PATTERN.search(content) and not _SECRET_EXCLUSIONS.search(content):
            hits.append(
                SecurityHit(
                    check=SecurityCheckType.HARDCODED_SECRET,
                    file=diff.filename,
                    line=lineno,
                    snippet=content.strip()[:120],
                    message="Hardcoded secret detected. Secrets in source code are exposed to anyone with repo access.",
                    fix="Move this value to an environment variable and load it with os.environ or a secrets manager.",
                )
            )
    return hits


# ── Check 2: SQL injection patterns ──────────────────────────────────────────

_SQL_CONCAT_PATTERN = re.compile(
    r"""(?xi)
    (?:execute|query|raw|cursor\.execute)\s*\(
    \s*[f\"'].*?
    (?:\+\s*\w+|\{[\w.]+\}|%\s*\w+|format\s*\()
    """,
    re.IGNORECASE,
)

_SQL_FORMAT_PATTERN = re.compile(
    r"""(?xi)
    (?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE)\b.*?
    (?:['\"]\s*\+\s*\w+|f['\"]\s*.*?\{|%s|%\(\w+\)s)
    """,
    re.IGNORECASE,
)


def check_sql_injection(diff: FileDiff) -> list[SecurityHit]:
    hits = []
    for lineno, content in _added_lines(diff):
        if _SQL_CONCAT_PATTERN.search(content) or _SQL_FORMAT_PATTERN.search(content):
            hits.append(
                SecurityHit(
                    check=SecurityCheckType.SQL_INJECTION,
                    file=diff.filename,
                    line=lineno,
                    snippet=content.strip()[:120],
                    message="Possible SQL injection: user input may be concatenated into a SQL query.",
                    fix="Use parameterized queries (e.g. cursor.execute(sql, params)) or an ORM.",
                )
            )
    return hits


# ── Check 3: Basic XSS patterns ───────────────────────────────────────────────

_XSS_PATTERN = re.compile(
    r"""(?xi)
    (?:innerHTML|outerHTML|document\.write|\.html\(|dangerouslySetInnerHTML)\s*[=\(]
    |render_template_string\s*\(
    |Markup\s*\(
    """,
    re.IGNORECASE,
)

_XSS_SAFE = re.compile(
    r"(?:escape|sanitize|DOMPurify|bleach|markupsafe)",
    re.IGNORECASE,
)


def check_xss(diff: FileDiff) -> list[SecurityHit]:
    hits = []
    for lineno, content in _added_lines(diff):
        if _XSS_PATTERN.search(content) and not _XSS_SAFE.search(content):
            hits.append(
                SecurityHit(
                    check=SecurityCheckType.XSS,
                    file=diff.filename,
                    line=lineno,
                    snippet=content.strip()[:120],
                    message="Potential XSS: unsanitized content written directly to HTML.",
                    fix="Escape or sanitize user-controlled input before rendering. Use a library like DOMPurify or bleach.",
                )
            )
    return hits


# ── Check 4: Missing auth on new endpoints ────────────────────────────────────

# Detects new route definitions without obvious auth decorators nearby
_ROUTE_PATTERN = re.compile(
    r"""(?xi)
    @(?:app|router|blueprint|bp)\.\s*
    (?:route|get|post|put|patch|delete)\s*\(
    """,
    re.IGNORECASE,
)

_AUTH_PATTERN = re.compile(
    r"""(?xi)
    @(?:login_required|require_auth|auth\.login_required|
       jwt_required|permission_required|requires_auth|
       authenticate|authorized|verify_token)
    |current_user|request\.user|get_current_user
    """,
    re.IGNORECASE,
)


def check_missing_auth(diff: FileDiff) -> list[SecurityHit]:
    """Flag new route definitions that don't have an auth decorator within 5 lines."""
    hits = []
    added = _added_lines(diff)
    lines_content = [c for _, c in added]
    lines_nos = [n for n, _ in added]

    for i, content in enumerate(lines_content):
        if _ROUTE_PATTERN.search(content):
            # Look at the surrounding 5 lines for any auth indicator
            window_start = max(0, i - 2)
            window_end = min(len(lines_content), i + 8)
            window = "\n".join(lines_content[window_start:window_end])
            if not _AUTH_PATTERN.search(window):
                hits.append(
                    SecurityHit(
                        check=SecurityCheckType.MISSING_AUTH,
                        file=diff.filename,
                        line=lines_nos[i],
                        snippet=content.strip()[:120],
                        message="New route defined without a visible authentication decorator or check.",
                        fix="Add an auth decorator (e.g. @login_required, @jwt_required) or verify authentication at the start of the handler.",
                    )
                )
    return hits


# ── Check 5: Exposed environment variables / config ───────────────────────────

_EXPOSED_ENV_PATTERN = re.compile(
    r"""(?xi)
    (?:print|log|logger\.\w+|console\.log|response\.json|jsonify)\s*\(
    [^)]*
    (?:os\.environ|getenv|SECRET|PASSWORD|TOKEN|API_KEY|PRIVATE_KEY)
    """,
    re.IGNORECASE,
)


def check_exposed_env(diff: FileDiff) -> list[SecurityHit]:
    hits = []
    for lineno, content in _added_lines(diff):
        if _EXPOSED_ENV_PATTERN.search(content):
            hits.append(
                SecurityHit(
                    check=SecurityCheckType.EXPOSED_ENV,
                    file=diff.filename,
                    line=lineno,
                    snippet=content.strip()[:120],
                    message="Environment variable or secret may be logged or exposed in a response.",
                    fix="Remove secrets from logs and API responses. Never return raw env vars to clients.",
                )
            )
    return hits


# ── Check 6: Unpinned dependency versions ────────────────────────────────────

_UNPINNED_PY_PATTERN = re.compile(
    r"""(?x)
    ^[\w\-\[\]]+\s*$          # bare package name with no version
    |^[\w\-\[\]]+\s*>=        # only lower bound
    |^[\w\-\[\]]+\s*~=        # compatible release — still allows major changes
    """,
    re.MULTILINE,
)

_REQUIREMENTS_FILES = {
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "Pipfile",
    "setup.cfg",
}

_PACKAGE_JSON_RANGE = re.compile(
    r'"[\w\-@/]+":\s*"\^[\d.]+"|"~[\d.]+"',
)


def check_unpinned_dependencies(diff: FileDiff) -> list[SecurityHit]:
    hits = []
    fname = diff.filename.lower()
    is_requirements = any(fname.endswith(r) for r in _REQUIREMENTS_FILES)
    is_package_json = fname.endswith("package.json")

    if not (is_requirements or is_package_json):
        return []

    for lineno, content in _added_lines(diff):
        stripped = content.strip()
        if not stripped or stripped.startswith("#"):
            continue

        flagged = False
        if is_requirements and _UNPINNED_PY_PATTERN.match(stripped):
            flagged = True
        if is_package_json and _PACKAGE_JSON_RANGE.search(stripped):
            flagged = True

        if flagged:
            hits.append(
                SecurityHit(
                    check=SecurityCheckType.UNPINNED_DEPENDENCY,
                    file=diff.filename,
                    line=lineno,
                    snippet=stripped[:120],
                    message="Dependency without a pinned version. Unpinned dependencies can pull in breaking or malicious updates.",
                    fix="Pin the dependency to an exact version (e.g. requests==2.31.0) or use a lockfile.",
                )
            )
    return hits
