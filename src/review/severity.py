"""Severity assignment and classification logic for code review findings.

Rules are applied in priority order. The first matching rule wins.
Each rule inspects the finding's title, description, and type to assign
or confirm a severity level.
"""

from __future__ import annotations

import re

from review.models import Finding, FindingType, Severity

# ── Keyword signal tables ──────────────────────────────────────────────────────

_P0_SIGNALS = [
    # Security — immediate exploitation risk
    r"sql\s+injection",
    r"remote\s+code\s+execution",
    r"rce\b",
    r"command\s+injection",
    r"arbitrary\s+code",
    r"authentication\s+bypass",
    r"auth\s+bypass",
    r"privilege\s+escalation",
    r"path\s+traversal",
    r"directory\s+traversal",
    r"xxe\b",
    r"server[- ]side\s+request\s+forgery",
    r"\bssrf\b",
    r"deserialization",
    r"hardcoded\s+(password|secret|token|key|credential)",
    # Data integrity
    r"data\s+loss",
    r"data\s+corruption",
    r"missing\s+transaction",
    # Crashes
    r"null\s+pointer\s+dereference",
    r"none\s+dereference",
    r"unhandled\s+exception.*production",
    r"index\s+out\s+of\s+(bounds|range)",
    r"stack\s+overflow",
    r"infinite\s+loop.*production",
]

_P1_SIGNALS = [
    # Security — significant risk
    r"\bxss\b",
    r"cross[- ]site\s+scripting",
    r"csrf\b",
    r"cross[- ]site\s+request\s+forgery",
    r"open\s+redirect",
    r"insecure\s+(direct\s+object|deserialization)",
    r"broken\s+access\s+control",
    r"missing\s+auth(entication|orization)",
    r"jwt.*weak|weak.*jwt",
    r"weak\s+(hash|cipher|algorithm|crypto)",
    r"md5|sha1\b",
    r"hardcoded\s+(api\s+key|secret)",
    r"exposed\s+(secret|credential|token)",
    r"race\s+condition",
    r"toctou\b",
    # Bugs — high impact
    r"memory\s+leak",
    r"resource\s+leak",
    r"deadlock",
    r"unbounded\s+(loop|recursion)",
    r"missing\s+timeout",
    r"unhandled\s+(error|exception|rejection)",
]

_P2_SIGNALS = [
    # Security — medium risk
    r"cors\b",
    r"missing\s+(csp|x-frame|security\s+header)",
    r"unpinned\s+depend",
    r"dependency\s+confusion",
    r"verbose\s+error",
    r"stack\s+trace\s+exposed",
    r"information\s+disclosure",
    # Code quality
    r"god\s+object",
    r"large\s+(class|function|method)",
    r"deep\s+nest",
    r"code\s+smell",
    r"duplicat",
    r"magic\s+(number|string)",
    r"missing\s+test",
    r"n\+1\s+query",
    r"performance",
]

_P3_SIGNALS = [
    r"naming",
    r"variable\s+name",
    r"unused\s+import",
    r"unused\s+variable",
    r"style",
    r"formatting",
    r"typo",
    r"comment",
    r"documentation",
    r"whitespace",
    r"minor",
    r"nit\b",
    r"suggestion",
]


def _matches(text: str, patterns: list[str]) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


def classify_severity(finding: Finding) -> Severity:
    """Assign or confirm severity for a finding based on content signals.

    If the existing severity already matches signals at a higher level,
    it is promoted. This prevents under-classification by the LLM.
    If no signal matches, the existing severity is kept.
    """
    text = f"{finding.title} {finding.description}"

    # Security findings get special treatment — never downgrade below P1
    if finding.type == FindingType.SECURITY:
        if _matches(text, _P0_SIGNALS):
            return Severity.P0
        if _matches(text, _P1_SIGNALS):
            return Severity.P1
        # Security findings are always at least P2
        return max_severity(finding.severity, Severity.P2)

    # Bug findings are always at least P2
    if finding.type == FindingType.BUG:
        if _matches(text, _P0_SIGNALS):
            return Severity.P0
        if _matches(text, _P1_SIGNALS):
            return Severity.P1
        return max_severity(finding.severity, Severity.P2)

    # General signal matching for all types
    if _matches(text, _P0_SIGNALS):
        return Severity.P0
    if _matches(text, _P1_SIGNALS):
        return Severity.P1
    if _matches(text, _P2_SIGNALS):
        return max_severity(finding.severity, Severity.P2)
    if _matches(text, _P3_SIGNALS):
        return Severity.P3

    return finding.severity


def max_severity(a: Severity, b: Severity) -> Severity:
    """Return the higher (more severe) of two severity levels."""
    order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
    return a if order[a] <= order[b] else b


def reclassify_findings(findings: list[Finding]) -> list[Finding]:
    """Apply severity reclassification to all findings in place.

    Returns the same list with updated severity values.
    """
    for finding in findings:
        finding.severity = classify_severity(finding)

    # Re-sort after reclassification
    order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
    findings.sort(key=lambda f: order[f.severity])
    return findings


def ensure_fix_for_blocking(findings: list[Finding]) -> list[Finding]:
    """Ensure P0 and P1 findings have a fix suggestion.

    If fix is missing, inserts a placeholder to prompt the reviewer.
    """
    for finding in findings:
        if finding.blocks_merge and not finding.fix:
            finding.fix = (
                "Fix required — this issue blocks merge. "
                "Please investigate and add a concrete resolution."
            )
    return findings
