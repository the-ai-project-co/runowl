"""Format review findings into markdown and structured output blocks."""

from review.models import Finding, FindingType, ReviewResult, Severity

_SEVERITY_BADGE = {
    Severity.P0: "🔴 P0 CRITICAL",
    Severity.P1: "🟠 P1 HIGH",
    Severity.P2: "🟡 P2 MEDIUM",
    Severity.P3: "🔵 P3 LOW",
}

_TYPE_EMOJI = {
    FindingType.BUG: "🐛",
    FindingType.SECURITY: "🔒",
    FindingType.INVESTIGATION: "🔍",
    FindingType.INFORMATIONAL: "ℹ️",
}


def format_finding_markdown(finding: Finding) -> str:
    """Render a single finding as a markdown block."""
    badge = _SEVERITY_BADGE[finding.severity]
    emoji = _TYPE_EMOJI[finding.type]
    lines = [
        f"### {badge} — {emoji} {finding.title}",
        f"**Location:** `{finding.citation}`",
        f"**Type:** {finding.type}",
        "",
        finding.description,
    ]
    if finding.fix:
        lines += ["", f"**Fix:** {finding.fix}"]
    return "\n".join(lines)


def format_review_markdown(result: ReviewResult) -> str:
    """Render a full review result as a GitHub PR comment body."""
    if not result.success:
        return f"## RunOwl Review Failed\n\n{result.error}"

    total = len(result.findings)
    blocking = len(result.blocking)

    status = (
        "✅ No blocking issues found."
        if blocking == 0
        else f"🚫 {blocking} blocking issue(s) found."
    )

    counts = {s: len(result.by_severity(s)) for s in Severity}
    summary_line = " · ".join(
        f"{_SEVERITY_BADGE[s]}: {counts[s]}" for s in Severity if counts[s] > 0
    )

    sections = [
        "## RunOwl Code Review",
        "",
        f"{status}",
        f"**{total} finding(s)** — {summary_line}" if summary_line else f"**{total} finding(s)**",
        "",
        "---",
    ]

    if not result.findings:
        sections.append("\n✅ No issues found in this PR.")
    else:
        for finding in result.findings:
            sections.append("")
            sections.append(format_finding_markdown(finding))
            sections.append("")
            sections.append("---")

    sections += [
        "",
        "<sub>Reviewed by [RunOwl](https://runowl.ai) · AI-powered code review</sub>",
    ]
    return "\n".join(sections)


def format_review_json(result: ReviewResult) -> dict[str, object]:
    """Render a full review result as a structured dict (for JSON output / CI)."""
    return {
        "success": result.success,
        "error": result.error,
        "summary": {
            "total": len(result.findings),
            "blocking": len(result.blocking),
            "by_severity": {s.value: len(result.by_severity(s)) for s in Severity},
            "by_type": {t.value: len(result.by_type(t)) for t in FindingType},
        },
        "findings": [
            {
                "severity": f.severity.value,
                "type": f.type.value,
                "title": f.title,
                "description": f.description,
                "citation": {
                    "file": f.citation.file,
                    "line_start": f.citation.line_start,
                    "line_end": f.citation.line_end,
                },
                "fix": f.fix,
                "blocks_merge": f.blocks_merge,
            }
            for f in result.findings
        ],
    }
