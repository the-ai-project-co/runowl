"""Build diff context strings for injection into the LLM prompt."""

from github.models import FileDiff, PRMetadata
from reasoning.prompts import CONTEXT_WINDOW_DIFF_LIMIT


def build_diff_context(metadata: PRMetadata, diffs: list[FileDiff]) -> str:
    """Build a compact diff context string for the prompt.

    - Includes up to CONTEXT_WINDOW_DIFF_LIMIT files directly in the prompt.
    - Remaining files are noted as available via FETCH_FILE tool.
    - Binary and deleted files are summarised without patch content.
    """
    lines: list[str] = []
    direct = diffs[:CONTEXT_WINDOW_DIFF_LIMIT]
    overflow = diffs[CONTEXT_WINDOW_DIFF_LIMIT:]

    for diff in direct:
        lines.append(f"### {diff.filename} [{diff.status}] +{diff.additions}/−{diff.deletions}")
        if diff.status == "removed":
            lines.append("*(file deleted)*\n")
            continue
        if not diff.hunks:
            lines.append("*(binary or no patch available)*\n")
            continue
        for hunk in diff.hunks:
            lines.append(hunk.header)
            lines.extend(hunk.lines)
        lines.append("")

    if overflow:
        lines.append(
            f"*{len(overflow)} additional files not shown. "
            "Use FETCH_FILE(path) to inspect them:*"
        )
        for diff in overflow:
            lines.append(f"  - {diff.filename} [{diff.status}]")

    return "\n".join(lines)


def build_pr_summary(metadata: PRMetadata) -> str:
    """Build a short PR summary string for Q&A context."""
    return (
        f"PR #{metadata.number}: {metadata.title}\n"
        f"Author: {metadata.author} | {metadata.head_branch} → {metadata.base_branch}\n"
        f"Changes: {metadata.changed_files} files, +{metadata.additions}/−{metadata.deletions}\n"
        f"Description: {metadata.body or '(none)'}"
    )
