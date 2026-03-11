"""Surface-level security scanner — runs all free-tier checks over PR diffs."""

from __future__ import annotations

import logging

from github.models import FileDiff
from security.checks import (
    check_exposed_env,
    check_hardcoded_secrets,
    check_missing_auth,
    check_sql_injection,
    check_unpinned_dependencies,
    check_xss,
)
from security.models import SecurityHit, SecurityReport

logger = logging.getLogger(__name__)

# File extensions to skip (binary, generated, lock files, etc.)
_SKIP_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".lock",
    ".sum",
    ".min.js",
    ".min.css",
    ".map",
}

_SKIP_FILENAMES = {"package-lock.json", "yarn.lock", "poetry.lock", "uv.lock"}


def _should_skip(filename: str) -> bool:
    lower = filename.lower()
    if any(lower.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return True
    if lower.split("/")[-1] in _SKIP_FILENAMES:
        return True
    return False


def run_surface_scan(diffs: list[FileDiff]) -> SecurityReport:
    """Run all free-tier surface security checks over a list of file diffs.

    Returns a SecurityReport with all hits found.
    """
    report = SecurityReport()
    all_hits: list[SecurityHit] = []

    for diff in diffs:
        if _should_skip(diff.filename):
            continue
        if diff.status == "removed":
            continue

        report.files_scanned += 1

        all_hits.extend(check_hardcoded_secrets(diff))
        all_hits.extend(check_sql_injection(diff))
        all_hits.extend(check_xss(diff))
        all_hits.extend(check_missing_auth(diff))
        all_hits.extend(check_exposed_env(diff))
        all_hits.extend(check_unpinned_dependencies(diff))

    # Deduplicate by (file, line, check)
    seen: set[tuple[str, int, str]] = set()
    for hit in all_hits:
        key = (hit.file, hit.line, hit.check)
        if key not in seen:
            seen.add(key)
            report.hits.append(hit)

    return report
