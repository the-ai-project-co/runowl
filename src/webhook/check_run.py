"""GitHub Check Runs API helpers — create and update check run status."""

from __future__ import annotations

import logging
from typing import Any

from github.client import GitHubClient
from review.models import ReviewResult

logger = logging.getLogger(__name__)

_CHECK_NAME = "RunOwl Code Review"


async def start_check_run(
    gh: GitHubClient,
    owner: str,
    repo: str,
    head_sha: str,
) -> int:
    """Create an in-progress Check Run and return its id."""
    try:
        data = await gh.create_check_run(
            owner=owner,
            repo=repo,
            name=_CHECK_NAME,
            head_sha=head_sha,
            status="in_progress",
        )
        check_run_id: int = data["id"]
        logger.info("Created check run %d for %s/%s@%s", check_run_id, owner, repo, head_sha[:7])
        return check_run_id
    except Exception:
        logger.exception("Failed to create check run for %s/%s@%s", owner, repo, head_sha[:7])
        return -1


async def finish_check_run(
    gh: GitHubClient,
    owner: str,
    repo: str,
    check_run_id: int,
    result: ReviewResult,
) -> None:
    """Mark the Check Run as completed based on review findings."""
    if check_run_id < 0:
        return

    blocking = result.blocking
    conclusion = "failure" if blocking else "success"

    summary_lines = [
        f"**RunOwl** reviewed this PR and found **{len(result.findings)} issue(s)**.",
        "",
    ]
    if blocking:
        summary_lines.append(
            f"⛔ **{len(blocking)} blocking issue(s)** — merge is not recommended until resolved."
        )
    else:
        summary_lines.append("✅ No blocking issues found.")

    # Add P0/P1 findings as details
    text_lines: list[str] = []
    for finding in result.critical + result.high:
        text_lines.append(f"### {finding.severity.upper()}: {finding.title}")
        text_lines.append(f"> `{finding.citation}`")
        text_lines.append("")
        text_lines.append(finding.description)
        if finding.fix:
            text_lines.append(f"\n**Fix:** {finding.fix}")
        text_lines.append("")

    output: dict[str, Any] = {
        "title": _CHECK_NAME,
        "summary": "\n".join(summary_lines),
    }
    if text_lines:
        output["text"] = "\n".join(text_lines)

    try:
        await gh.update_check_run(
            owner=owner,
            repo=repo,
            check_run_id=check_run_id,
            conclusion=conclusion,
            output=output,
        )
        logger.info(
            "Updated check run %d → %s (%d findings)",
            check_run_id,
            conclusion,
            len(result.findings),
        )
    except Exception:
        logger.exception("Failed to update check run %d", check_run_id)
