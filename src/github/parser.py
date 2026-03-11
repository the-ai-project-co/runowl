"""Parse GitHub URLs into structured references."""

import re

from github.models import PRRef

# Matches:
#   https://github.com/owner/repo/pull/123
#   https://github.com/owner/repo/pull/123/files
#   https://github.com/owner/repo/pull/123#issuecomment-456
_PR_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)

# Prevent path traversal — only safe path chars allowed
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_\-./]+$")


def parse_pr_url(url: str) -> PRRef:
    """Extract owner, repo, and PR number from a GitHub PR URL.

    Raises ValueError for invalid or non-PR URLs.
    """
    url = url.strip()
    match = _PR_URL_RE.match(url)
    if not match:
        raise ValueError(
            f"Invalid GitHub PR URL: {url!r}\n"
            "Expected format: https://github.com/owner/repo/pull/123"
        )
    return PRRef(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=int(match.group("number")),
    )


def sanitize_path(path: str) -> str:
    """Sanitize a file path to prevent directory traversal attacks.

    Raises ValueError if the path contains unsafe characters or traversal sequences.
    """
    # Normalize and reject traversal attempts
    normalized = path.strip().lstrip("/")
    if ".." in normalized.split("/"):
        raise ValueError(f"Path traversal detected in: {path!r}")
    if not _SAFE_PATH_RE.match(normalized):
        raise ValueError(f"Unsafe characters in path: {path!r}")
    return normalized
