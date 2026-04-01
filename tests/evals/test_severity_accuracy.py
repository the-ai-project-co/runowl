"""AI evals for severity classification precision/recall across a comprehensive golden dataset.

Evaluates whether ``classify_severity`` from ``review.severity`` correctly
classifies findings based on content signals, respects type-based severity
floors, and handles reclassification and fix enforcement correctly.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from review.models import Citation, Finding, FindingType, Severity
from review.severity import (
    classify_severity,
    ensure_fix_for_blocking,
    max_severity,
    reclassify_findings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CITATION = Citation(file="src/app.py", line_start=1, line_end=10)


def _make_finding(
    title: str,
    description: str,
    finding_type: FindingType = FindingType.BUG,
    severity: Severity = Severity.P3,
    fix: str | None = None,
) -> Finding:
    """Build a Finding with sensible defaults for testing classification."""
    return Finding(
        severity=severity,
        type=finding_type,
        title=title,
        description=description,
        citation=_DEFAULT_CITATION,
        fix=fix,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Golden Dataset — P0 Classification (30 test cases)
# ═══════════════════════════════════════════════════════════════════════════════

GOLDEN_P0 = [
    # SQL injection
    {
        "title": "User input passed to raw query",
        "description": "The login endpoint is vulnerable to sql injection via the username field",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Remote code execution
    {
        "title": "Eval on user input",
        "description": "Calling eval() on untrusted data enables remote code execution",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # RCE abbreviation
    {
        "title": "Dangerous deserialization path",
        "description": "Unpickling user-supplied data can lead to rce on the server",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Command injection
    {
        "title": "Shell call with user data",
        "description": "os.system() is called with user-controlled input, allowing command injection",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Arbitrary code
    {
        "title": "Untrusted module import",
        "description": "Loading plugins from user paths permits arbitrary code execution on the host",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Authentication bypass
    {
        "title": "JWT validation skipped",
        "description": "The admin endpoint does not verify the token, resulting in authentication bypass",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Auth bypass (short form)
    {
        "title": "Missing token check",
        "description": "Endpoints under /internal are reachable without credentials — this is an auth bypass",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Privilege escalation
    {
        "title": "Role check missing",
        "description": "Non-admin users can modify other users' roles, causing privilege escalation",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Path traversal
    {
        "title": "File download endpoint",
        "description": "User-supplied file names are passed directly to open(), enabling path traversal",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Directory traversal
    {
        "title": "Archive extraction",
        "description": "Zip entries with ../ prefixes allow directory traversal during extraction",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # XXE
    {
        "title": "XML parser misconfiguration",
        "description": "The parser resolves external entities, making it susceptible to xxe attacks",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # SSRF
    {
        "title": "Webhook proxy",
        "description": "The webhook forwarding service does not filter internal IPs — ssrf is possible",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Server-side request forgery (long form)
    {
        "title": "URL fetch endpoint",
        "description": "Users can trigger server-side request forgery by supplying internal URLs",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Deserialization
    {
        "title": "Pickle load from request",
        "description": "Using pickle.loads on untrusted bytes introduces insecure deserialization risks",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Hardcoded password
    {
        "title": "DB credentials in source",
        "description": "Found a hardcoded password in the database connection string",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Hardcoded secret
    {
        "title": "Secrets in config file",
        "description": "There is a hardcoded secret in config.py that grants API access",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Hardcoded token
    {
        "title": "Auth token committed",
        "description": "A hardcoded token for the payment provider is checked into the repository",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Hardcoded key
    {
        "title": "Encryption key in code",
        "description": "The AES encryption uses a hardcoded key instead of a key vault",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Hardcoded credential
    {
        "title": "Service account credentials",
        "description": "A hardcoded credential for the cloud service account is embedded in the source",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Data loss
    {
        "title": "Missing WHERE in DELETE",
        "description": "The cleanup job issues DELETE without a WHERE clause, risking data loss",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Data corruption
    {
        "title": "Concurrent write without lock",
        "description": "Two processes can write the same row simultaneously, causing data corruption",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Missing transaction
    {
        "title": "Multi-table update not atomic",
        "description": "Updates to orders and inventory are not wrapped — missing transaction boundary",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Null pointer dereference
    {
        "title": "Crash on empty response",
        "description": "Accessing .data on a None response leads to a null pointer dereference",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # None dereference
    {
        "title": "Optional not checked",
        "description": "get_user() may return None; calling .name causes a none dereference",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Index out of bounds
    {
        "title": "Array access unchecked",
        "description": "Accessing items[idx] without length check can trigger index out of bounds",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Index out of range
    {
        "title": "List slicing error",
        "description": "The loop termination condition is wrong, leading to index out of range",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Stack overflow
    {
        "title": "Recursive call unbounded",
        "description": "The tree traversal lacks a base case and will cause a stack overflow",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Infinite loop in production
    {
        "title": "Worker loop never exits",
        "description": "The retry loop has no exit condition and will cause an infinite loop in production",
        "type": FindingType.BUG,
        "expected": Severity.P0,
    },
    # Keyword in middle of sentence
    {
        "title": "Critical flaw",
        "description": "Due to missing input sanitization, an attacker could achieve remote code execution on the API server",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
    # Multiple keywords present
    {
        "title": "Multiple vulnerabilities",
        "description": "This endpoint has sql injection and also allows path traversal via the filename param",
        "type": FindingType.SECURITY,
        "expected": Severity.P0,
    },
]


@pytest.mark.parametrize(
    "case",
    GOLDEN_P0,
    ids=[c["title"] for c in GOLDEN_P0],
)
def test_golden_p0_classification(case: dict) -> None:
    finding = _make_finding(
        title=case["title"],
        description=case["description"],
        finding_type=case["type"],
    )
    result = classify_severity(finding)
    assert result == case["expected"], (
        f"Expected {case['expected']} for '{case['title']}', got {result}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Golden Dataset — P1 Classification (25 test cases)
# ═══════════════════════════════════════════════════════════════════════════════

GOLDEN_P1 = [
    {
        "title": "Script injection in comments",
        "description": "User-generated comments are rendered without escaping, causing xss",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Rendered HTML unsafe",
        "description": "Profile bios can contain cross-site scripting payloads that execute on view",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Form lacks anti-forgery token",
        "description": "The settings form is missing csrf protection",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Request forgery risk",
        "description": "State-changing actions lack cross-site request forgery tokens",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Login redirect flaw",
        "description": "The return_url parameter is not validated, enabling an open redirect after login",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "IDOR on user profiles",
        "description": "Changing the user ID in the URL reveals other users' data — insecure direct object reference",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "No role check on admin panel",
        "description": "The admin panel has broken access control — any logged-in user can reach it",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Endpoint lacks authN",
        "description": "The /api/internal/data endpoint has no missing authentication check for callers",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "JWT signing weakness",
        "description": "Tokens are signed with jwt using a weak HS256 key that can be brute-forced",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Password hashing insecure",
        "description": "Passwords are hashed with a weak hash algorithm (MD5) instead of bcrypt",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Deprecated digest used",
        "description": "Checksum verification relies on md5 which is considered broken",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Hardcoded API key found",
        "description": "A hardcoded api key for Stripe is committed in payment.py",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Token visible in logs",
        "description": "The debug logger writes the full OAuth exposed token to stdout",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
    {
        "title": "Counter increment not atomic",
        "description": "The visit counter has a race condition under concurrent requests",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "File handle check-then-act",
        "description": "Checking existence then opening introduces a toctou vulnerability",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Connection pool exhaustion",
        "description": "DB connections are never returned to the pool, causing a memory leak",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Unclosed file handles accumulate",
        "description": "Opened files are never closed on the error path, leading to a memory leak over time",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Mutex ordering wrong",
        "description": "Acquiring lock_a then lock_b in one thread and vice versa creates a deadlock",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Retry loop without cap",
        "description": "The retry loop has no maximum iteration count — unbounded loop on failure",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Recursive descent unlimited",
        "description": "Deeply nested JSON triggers unbounded recursion in the parser",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "HTTP client no deadline",
        "description": "External API calls have no missing timeout and can hang indefinitely",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Swallowed exception",
        "description": "The except clause catches BaseException and passes — unhandled error path",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Promise rejection ignored",
        "description": "The async call has no .catch(), leaving an unhandled rejection",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Exception swallowed silently",
        "description": "IOError is caught but neither logged nor reraised — unhandled exception in payment flow",
        "type": FindingType.BUG,
        "expected": Severity.P1,
    },
    {
        "title": "Weak cipher suite",
        "description": "TLS config uses a weak cipher suite (RC4) that is known to be broken",
        "type": FindingType.SECURITY,
        "expected": Severity.P1,
    },
]


@pytest.mark.parametrize(
    "case",
    GOLDEN_P1,
    ids=[c["title"] for c in GOLDEN_P1],
)
def test_golden_p1_classification(case: dict) -> None:
    finding = _make_finding(
        title=case["title"],
        description=case["description"],
        finding_type=case["type"],
    )
    result = classify_severity(finding)
    assert result == case["expected"], (
        f"Expected {case['expected']} for '{case['title']}', got {result}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Golden Dataset — P2 Classification (16 test cases)
# ═══════════════════════════════════════════════════════════════════════════════

GOLDEN_P2 = [
    {
        "title": "Wildcard CORS origin",
        "description": "The API sets Access-Control-Allow-Origin to *, loosening cors policy",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "No Content-Security-Policy",
        "description": "The response headers are missing csp, allowing inline script execution",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Clickjacking possible",
        "description": "Pages can be framed because the missing x-frame options header is absent",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Lockfile not checked in",
        "description": "The project has unpinned dependencies in requirements.txt with no lock file",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Internal package confusion",
        "description": "The private package name collides with a public one — dependency confusion risk",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Error messages expose internals",
        "description": "The 500 handler returns a verbose error message that includes the SQL query",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Debug page in production",
        "description": "The Django debug page shows the full stack trace exposed to users in production",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Version header leaks info",
        "description": "The Server header discloses the framework version — information disclosure risk",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Manager class does too much",
        "description": "OrderManager handles creation, payment, and shipping — a classic god object",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Method exceeds 200 lines",
        "description": "process_order() is a large function that is hard to test and maintain",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Callback pyramid",
        "description": "The handler has five levels of deep nesting making it unreadable",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Obvious code smell",
        "description": "Multiple code smell indicators: long parameter list, feature envy, data clumps",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Copy-pasted validation",
        "description": "The input validation logic is duplicated across three controllers",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Unexplained constants",
        "description": "The fee calculation uses a magic number 0.0275 without any documentation",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "No unit tests for payment",
        "description": "The payment module has zero coverage — missing test for refund logic",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
    {
        "title": "Slow dashboard query",
        "description": "Loading the dashboard issues one query per widget — n+1 query pattern degrades performance",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P2,
    },
]


@pytest.mark.parametrize(
    "case",
    GOLDEN_P2,
    ids=[c["title"] for c in GOLDEN_P2],
)
def test_golden_p2_classification(case: dict) -> None:
    finding = _make_finding(
        title=case["title"],
        description=case["description"],
        finding_type=case["type"],
    )
    result = classify_severity(finding)
    assert result == case["expected"], (
        f"Expected {case['expected']} for '{case['title']}', got {result}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Golden Dataset — P3 Classification (13 test cases)
# ═══════════════════════════════════════════════════════════════════════════════

GOLDEN_P3 = [
    {
        "title": "Inconsistent naming convention",
        "description": "The function uses camelCase while the rest of the codebase uses snake_case — naming inconsistency",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Unclear identifier",
        "description": "The variable name 'x' is too short and does not convey intent",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Leftover import",
        "description": "The os module is imported but never referenced — unused import",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Dead code detected",
        "description": "The counter variable is assigned but never read — unused variable",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Code style violation",
        "description": "The function body is not separated by a blank line per style guide",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Inconsistent indentation",
        "description": "Mixed tabs and spaces cause formatting issues in the template file",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Spelling mistake",
        "description": "The error message contains a typo: 'recieved' should be 'received'",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Outdated inline note",
        "description": "The TODO comment references a ticket that was completed two sprints ago",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Missing docstring",
        "description": "Public API function lacks documentation explaining its parameters",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Trailing spaces",
        "description": "Several lines have trailing whitespace that should be stripped",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Trivial improvement",
        "description": "This is a minor issue — the else branch could be simplified",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Small nitpick",
        "description": "Nit: prefer using f-strings over .format() for readability",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
    {
        "title": "Optional enhancement",
        "description": "Suggestion: extract this block into a helper function for clarity",
        "type": FindingType.INFORMATIONAL,
        "expected": Severity.P3,
    },
]


@pytest.mark.parametrize(
    "case",
    GOLDEN_P3,
    ids=[c["title"] for c in GOLDEN_P3],
)
def test_golden_p3_classification(case: dict) -> None:
    finding = _make_finding(
        title=case["title"],
        description=case["description"],
        finding_type=case["type"],
    )
    result = classify_severity(finding)
    assert result == case["expected"], (
        f"Expected {case['expected']} for '{case['title']}', got {result}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Precision Eval — No False Promotions
# ═══════════════════════════════════════════════════════════════════════════════

FALSE_POSITIVE_CASES = [
    {
        "title": "Add null check for optional parameter",
        "description": "The function should guard against None before accessing attributes",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "Contains 'null' but not 'null pointer dereference'",
    },
    {
        "title": "Remove unused CSS class",
        "description": "The .header-old class is defined but never used in any template",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P1,
        "reason": "'missing' does not match 'missing auth'",
    },
    {
        "title": "Use pathlib instead of os.path",
        "description": "The path manipulation could use pathlib for better readability",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "'path' does not match 'path traversal'",
    },
    {
        "title": "Simplify conditional",
        "description": "The nested if-else can be replaced with a single expression",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "No P0 signals present",
    },
    {
        "title": "Extract constant",
        "description": "The string 'application/json' appears six times",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "No P0 signals present",
    },
    {
        "title": "Rename handler function",
        "description": "The function name 'do_stuff' is not descriptive",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "No P0 signals present",
    },
    {
        "title": "Add type hints to parameters",
        "description": "The public API lacks type annotations for its arguments",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P1,
        "reason": "No P1 signals present",
    },
    {
        "title": "Prefer early return",
        "description": "The function has a deep else block that can be flattened with an early return",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "No P0 signals present",
    },
    {
        "title": "Update log level",
        "description": "The info log should be changed to debug for high-frequency calls",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "No P0 signals present",
    },
    {
        "title": "Consider using dataclass",
        "description": "This plain class with only __init__ and fields would be cleaner as a dataclass",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P1,
        "reason": "No P1 signals present",
    },
    {
        "title": "Refactor loop to comprehension",
        "description": "The for-loop that builds a list can be rewritten as a list comprehension",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "No P0 signals present",
    },
    {
        "title": "Add logging to error branch",
        "description": "The except block should log the error before continuing",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "'error' alone does not match 'unhandled error'",
    },
    {
        "title": "Move config to environment variable",
        "description": "The database URL should not be hard-coded in settings.py",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "'hard-coded' does not match 'hardcoded password'",
    },
    {
        "title": "Add index on foreign key",
        "description": "The orders.user_id column lacks an index, slowing joins",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "'index' does not match 'index out of bounds'",
    },
    {
        "title": "Improve test coverage",
        "description": "Branch coverage for the auth module is below 70%",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P0,
        "reason": "'auth' alone does not match 'auth bypass'",
    },
    {
        "title": "Replace print with logger",
        "description": "Using print() for debugging should be replaced with structured logging",
        "type": FindingType.INFORMATIONAL,
        "not_expected": Severity.P1,
        "reason": "No P1 signals present",
    },
]


@pytest.mark.parametrize(
    "case",
    FALSE_POSITIVE_CASES,
    ids=[c["title"] for c in FALSE_POSITIVE_CASES],
)
def test_no_false_promotions(case: dict) -> None:
    finding = _make_finding(
        title=case["title"],
        description=case["description"],
        finding_type=case["type"],
    )
    result = classify_severity(finding)
    assert result != case["not_expected"], (
        f"False promotion: '{case['title']}' should NOT be {case['not_expected']} "
        f"(got {result}). Reason: {case['reason']}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Security / Bug Floor Eval
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityFloor:
    """SECURITY type findings must never be classified below P2."""

    def test_security_with_p3_keywords_gets_floor_p2(self) -> None:
        finding = _make_finding(
            title="Minor naming issue in auth module",
            description="Variable naming in the security middleware is inconsistent",
            finding_type=FindingType.SECURITY,
            severity=Severity.P3,
        )
        result = classify_severity(finding)
        assert result.value <= "P2", (
            f"SECURITY finding with P3 keywords should be at least P2, got {result}"
        )

    def test_security_with_no_signals_gets_floor_p2(self) -> None:
        finding = _make_finding(
            title="Refactor authentication flow",
            description="The login handler mixes validation and persistence concerns",
            finding_type=FindingType.SECURITY,
            severity=Severity.P3,
        )
        result = classify_severity(finding)
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert order[result] <= order[Severity.P2], (
            f"SECURITY finding must be at least P2, got {result}"
        )

    def test_security_with_p0_signal_stays_p0(self) -> None:
        finding = _make_finding(
            title="SQL injection in search",
            description="User input is concatenated into the sql injection vulnerable query",
            finding_type=FindingType.SECURITY,
        )
        assert classify_severity(finding) == Severity.P0

    def test_security_with_p1_signal_stays_p1(self) -> None:
        finding = _make_finding(
            title="XSS in profile page",
            description="HTML is not escaped, enabling xss in the profile bio",
            finding_type=FindingType.SECURITY,
        )
        assert classify_severity(finding) == Severity.P1

    def test_security_floor_when_existing_severity_is_p3(self) -> None:
        finding = _make_finding(
            title="Generic security concern",
            description="The handler does not validate caller identity",
            finding_type=FindingType.SECURITY,
            severity=Severity.P3,
        )
        result = classify_severity(finding)
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert order[result] <= order[Severity.P2]

    def test_security_preserves_higher_existing_severity(self) -> None:
        finding = _make_finding(
            title="Generic security concern",
            description="The handler does not validate caller identity",
            finding_type=FindingType.SECURITY,
            severity=Severity.P1,
        )
        result = classify_severity(finding)
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert order[result] <= order[Severity.P1]


class TestBugFloor:
    """BUG type findings must never be classified below P2."""

    def test_bug_with_p3_keywords_gets_floor_p2(self) -> None:
        finding = _make_finding(
            title="Minor naming issue in utils",
            description="Variable naming in the helper function is inconsistent",
            finding_type=FindingType.BUG,
            severity=Severity.P3,
        )
        result = classify_severity(finding)
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert order[result] <= order[Severity.P2], (
            f"BUG finding must be at least P2, got {result}"
        )

    def test_bug_with_no_signals_gets_floor_p2(self) -> None:
        finding = _make_finding(
            title="Off-by-one in pagination",
            description="The page calculation can skip the last item",
            finding_type=FindingType.BUG,
            severity=Severity.P3,
        )
        result = classify_severity(finding)
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert order[result] <= order[Severity.P2]

    def test_bug_with_p0_signal_stays_p0(self) -> None:
        finding = _make_finding(
            title="Null pointer crash",
            description="Accessing .value causes a null pointer dereference on empty input",
            finding_type=FindingType.BUG,
        )
        assert classify_severity(finding) == Severity.P0

    def test_bug_with_p1_signal_stays_p1(self) -> None:
        finding = _make_finding(
            title="Connection pool exhaustion",
            description="Database connections are never closed — memory leak under load",
            finding_type=FindingType.BUG,
        )
        assert classify_severity(finding) == Severity.P1

    def test_bug_preserves_higher_existing_severity(self) -> None:
        finding = _make_finding(
            title="Off-by-one error",
            description="The counter is incremented one too many times",
            finding_type=FindingType.BUG,
            severity=Severity.P0,
        )
        result = classify_severity(finding)
        order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        assert order[result] <= order[Severity.P0]


class TestInformationalCanBeP3:
    """INFORMATIONAL type findings CAN be P3 — no floor applies."""

    def test_informational_with_p3_keywords_stays_p3(self) -> None:
        finding = _make_finding(
            title="Fix typo in readme",
            description="The word 'configuration' is misspelled as 'configuraion' — typo",
            finding_type=FindingType.INFORMATIONAL,
        )
        assert classify_severity(finding) == Severity.P3

    def test_informational_with_no_signals_keeps_existing(self) -> None:
        finding = _make_finding(
            title="Consider refactoring",
            description="This block could be cleaner",
            finding_type=FindingType.INFORMATIONAL,
            severity=Severity.P3,
        )
        assert classify_severity(finding) == Severity.P3

    def test_informational_with_p0_signal_gets_promoted(self) -> None:
        finding = _make_finding(
            title="Potential security issue",
            description="This could allow sql injection through the search field",
            finding_type=FindingType.INFORMATIONAL,
        )
        assert classify_severity(finding) == Severity.P0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Reclassification Eval
# ═══════════════════════════════════════════════════════════════════════════════


class TestReclassifyFindings:
    """Test that reclassify_findings promotes under-classified findings and sorts."""

    def test_promotes_under_classified_findings(self) -> None:
        findings = [
            _make_finding(
                title="SQL injection in login",
                description="Raw user input concatenated into sql injection vulnerable query",
                finding_type=FindingType.SECURITY,
                severity=Severity.P2,
            ),
            _make_finding(
                title="XSS in comment box",
                description="User HTML is rendered unescaped — xss is possible",
                finding_type=FindingType.SECURITY,
                severity=Severity.P3,
            ),
        ]
        result = reclassify_findings(findings)
        assert result[0].severity == Severity.P0, "SQL injection should be promoted to P0"
        assert result[1].severity == Severity.P1, "XSS should be promoted to P1"

    def test_sorts_by_severity_after_reclassification(self) -> None:
        findings = [
            _make_finding(
                title="Style issue",
                description="Naming convention not followed — naming inconsistency",
                finding_type=FindingType.INFORMATIONAL,
                severity=Severity.P3,
            ),
            _make_finding(
                title="Critical vulnerability",
                description="Endpoint allows remote code execution via eval",
                finding_type=FindingType.SECURITY,
                severity=Severity.P3,
            ),
            _make_finding(
                title="Missing tests",
                description="The module has no missing test coverage at all",
                finding_type=FindingType.INFORMATIONAL,
                severity=Severity.P3,
            ),
        ]
        result = reclassify_findings(findings)
        severities = [f.severity for f in result]
        expected_order = sorted(
            severities,
            key=lambda s: {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}[s],
        )
        assert severities == expected_order, f"Expected sorted order, got {severities}"

    def test_does_not_downgrade(self) -> None:
        findings = [
            _make_finding(
                title="Already P0 finding",
                description="This is a critical finding flagged by the LLM as P0",
                finding_type=FindingType.BUG,
                severity=Severity.P0,
            ),
        ]
        result = reclassify_findings(findings)
        assert result[0].severity in (Severity.P0, Severity.P1, Severity.P2), (
            "BUG finding at P0 should not be downgraded"
        )

    def test_mixed_types_reclassified_correctly(self) -> None:
        findings = [
            _make_finding(
                title="Hardcoded password in config",
                description="The database uses a hardcoded password in settings.py",
                finding_type=FindingType.SECURITY,
                severity=Severity.P3,
            ),
            _make_finding(
                title="Deadlock in worker",
                description="The job processor can deadlock when two tasks compete for the same lock",
                finding_type=FindingType.BUG,
                severity=Severity.P3,
            ),
            _make_finding(
                title="Typo in variable",
                description="The variable 'accont' should be 'account' — typo",
                finding_type=FindingType.INFORMATIONAL,
                severity=Severity.P3,
            ),
        ]
        result = reclassify_findings(findings)
        assert result[0].severity == Severity.P0, "Hardcoded password → P0"
        assert result[1].severity == Severity.P1, "Deadlock → P1"
        assert result[2].severity == Severity.P3, "Typo → P3"

    def test_returns_same_list(self) -> None:
        findings = [
            _make_finding(
                title="Some finding",
                description="Something about a typo in a log message",
                finding_type=FindingType.INFORMATIONAL,
                severity=Severity.P3,
            ),
        ]
        result = reclassify_findings(findings)
        assert result is findings, "Should return the same list object"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Fix Enforcement Eval
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnsureFixForBlocking:
    """Test that P0/P1 findings get placeholder fixes; P2/P3 and existing fixes are untouched."""

    def test_p0_without_fix_gets_placeholder(self) -> None:
        findings = [
            _make_finding(
                title="SQL injection",
                description="SQL injection in login endpoint",
                finding_type=FindingType.SECURITY,
                severity=Severity.P0,
                fix=None,
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix is not None
        assert "Fix required" in result[0].fix

    def test_p1_without_fix_gets_placeholder(self) -> None:
        findings = [
            _make_finding(
                title="XSS vulnerability",
                description="Cross-site scripting in search",
                finding_type=FindingType.SECURITY,
                severity=Severity.P1,
                fix=None,
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix is not None
        assert "Fix required" in result[0].fix

    def test_p2_without_fix_not_modified(self) -> None:
        findings = [
            _make_finding(
                title="Code smell",
                description="Large function should be refactored",
                finding_type=FindingType.INFORMATIONAL,
                severity=Severity.P2,
                fix=None,
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix is None

    def test_p3_without_fix_not_modified(self) -> None:
        findings = [
            _make_finding(
                title="Typo",
                description="Spelling mistake in comment",
                finding_type=FindingType.INFORMATIONAL,
                severity=Severity.P3,
                fix=None,
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix is None

    def test_existing_fix_preserved_on_p0(self) -> None:
        findings = [
            _make_finding(
                title="Command injection",
                description="User input passed to shell",
                finding_type=FindingType.SECURITY,
                severity=Severity.P0,
                fix="Use subprocess with shell=False and pass args as list",
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix == "Use subprocess with shell=False and pass args as list"

    def test_existing_fix_preserved_on_p1(self) -> None:
        findings = [
            _make_finding(
                title="Memory leak",
                description="Connection pool never releases connections",
                finding_type=FindingType.BUG,
                severity=Severity.P1,
                fix="Add a finally block to close the connection",
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix == "Add a finally block to close the connection"

    def test_mixed_list(self) -> None:
        findings = [
            _make_finding(
                title="RCE via eval",
                description="Remote code execution through eval()",
                finding_type=FindingType.SECURITY,
                severity=Severity.P0,
                fix=None,
            ),
            _make_finding(
                title="Race condition",
                description="Counter not atomic",
                finding_type=FindingType.BUG,
                severity=Severity.P1,
                fix="Use atomic increment",
            ),
            _make_finding(
                title="Naming issue",
                description="Bad variable name",
                finding_type=FindingType.INFORMATIONAL,
                severity=Severity.P3,
                fix=None,
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix is not None and "Fix required" in result[0].fix
        assert result[1].fix == "Use atomic increment"
        assert result[2].fix is None

    def test_returns_same_list(self) -> None:
        findings = [
            _make_finding(
                title="Deadlock",
                description="Lock ordering issue causes deadlock",
                finding_type=FindingType.BUG,
                severity=Severity.P1,
                fix=None,
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result is findings

    def test_empty_string_fix_on_p0_gets_placeholder(self) -> None:
        findings = [
            _make_finding(
                title="Path traversal",
                description="File path allows path traversal",
                finding_type=FindingType.SECURITY,
                severity=Severity.P0,
                fix="",
            ),
        ]
        result = ensure_fix_for_blocking(findings)
        assert result[0].fix is not None
        assert "Fix required" in result[0].fix


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Aggregate Metrics — Precision/Recall Summary
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class _SeverityMetrics:
    """Tracks correct/total counts for a single severity level."""

    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0


class TestAggregateMetrics:
    """Run all golden datasets and report precision/recall per severity level."""

    _metrics: dict[Severity, _SeverityMetrics] = {}

    @classmethod
    def _ensure_metrics(cls) -> dict[Severity, _SeverityMetrics]:
        if not cls._metrics:
            cls._metrics = {sev: _SeverityMetrics() for sev in Severity}
        return cls._metrics

    @pytest.mark.parametrize(
        "case",
        GOLDEN_P0 + GOLDEN_P1 + GOLDEN_P2 + GOLDEN_P3,
        ids=[
            f"{c['expected'].value}-{c['title']}"
            for c in GOLDEN_P0 + GOLDEN_P1 + GOLDEN_P2 + GOLDEN_P3
        ],
    )
    def test_aggregate_classification(self, case: dict) -> None:
        metrics = self._ensure_metrics()
        finding = _make_finding(
            title=case["title"],
            description=case["description"],
            finding_type=case["type"],
        )
        result = classify_severity(finding)
        expected: Severity = case["expected"]
        metrics[expected].total += 1
        if result == expected:
            metrics[expected].correct += 1
        assert result == expected, (
            f"[{expected.value}] '{case['title']}' classified as {result}"
        )

    @classmethod
    def teardown_class(cls) -> None:
        """Print precision/recall summary after all aggregate tests run."""
        metrics = cls._metrics
        if not metrics:
            return
        print("\n\n══════ Severity Classification Metrics ══════")
        total_correct = 0
        total_count = 0
        for sev in (Severity.P0, Severity.P1, Severity.P2, Severity.P3):
            m = metrics.get(sev, _SeverityMetrics())
            total_correct += m.correct
            total_count += m.total
            pct = f"{m.accuracy:.1%}" if m.total else "N/A"
            print(f"  {sev.value}: {m.correct}/{m.total} correct ({pct})")
        overall = total_correct / total_count if total_count else 0.0
        print(f"  OVERALL: {total_correct}/{total_count} ({overall:.1%})")
        print("══════════════════════════════════════════════\n")


# ═══════════════════════════════════════════════════════════════════════════════
# max_severity helper
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaxSeverity:
    """Verify the max_severity helper returns the more severe level."""

    def test_p0_vs_p3(self) -> None:
        assert max_severity(Severity.P0, Severity.P3) == Severity.P0

    def test_p3_vs_p0(self) -> None:
        assert max_severity(Severity.P3, Severity.P0) == Severity.P0

    def test_same_severity(self) -> None:
        assert max_severity(Severity.P2, Severity.P2) == Severity.P2

    def test_p1_vs_p2(self) -> None:
        assert max_severity(Severity.P1, Severity.P2) == Severity.P1

    def test_p2_vs_p1(self) -> None:
        assert max_severity(Severity.P2, Severity.P1) == Severity.P1
