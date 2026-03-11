"""Parse structured findings from raw agent output text."""

from __future__ import annotations

import re

from review.citations import extract_citations
from review.models import Citation, Finding, FindingType, Severity

# Matches the finding header line:
#   [P0] bug: SQL injection in login endpoint
#   [P1] security: Missing auth check
_FINDING_HEADER_RE = re.compile(
    r"\[(?P<severity>P[0-3])\]\s+(?P<type>\w+):\s+(?P<title>.+)",
    re.IGNORECASE,
)

# Maps common type strings to FindingType enum values
_TYPE_MAP: dict[str, FindingType] = {
    "bug": FindingType.BUG,
    "security": FindingType.SECURITY,
    "investigation": FindingType.INVESTIGATION,
    "informational": FindingType.INFORMATIONAL,
    "info": FindingType.INFORMATIONAL,
    "investigate": FindingType.INVESTIGATION,
}

_SEVERITY_MAP: dict[str, Severity] = {
    "P0": Severity.P0,
    "P1": Severity.P1,
    "P2": Severity.P2,
    "P3": Severity.P3,
}


def _parse_block(block: str) -> Finding | None:
    """Parse a single finding block into a Finding dataclass."""
    lines = block.strip().splitlines()
    if not lines:
        return None

    header_match = _FINDING_HEADER_RE.match(lines[0].strip())
    if not header_match:
        return None

    severity = _SEVERITY_MAP.get(header_match.group("severity").upper(), Severity.P3)
    type_str = header_match.group("type").lower()
    finding_type = _TYPE_MAP.get(type_str, FindingType.INFORMATIONAL)
    title = header_match.group("title").strip()

    description = ""
    fix = None
    file_ref = ""

    for line in lines[1:]:
        stripped = line.strip()
        if stripped.lower().startswith("file:"):
            file_ref = stripped[5:].strip()
        elif stripped.lower().startswith("description:"):
            description = stripped[12:].strip()
        elif stripped.lower().startswith("fix:"):
            fix = stripped[4:].strip()
        elif description and not stripped.lower().startswith(("file:", "fix:")):
            # Multi-line description
            description += " " + stripped

    # Extract citation from the File: line
    citation: Citation | None = None
    if file_ref:
        found = extract_citations(file_ref)
        if found:
            citation = found[0]

    # Fallback: scan entire block for citation
    if citation is None:
        found = extract_citations(block)
        if found:
            citation = found[0]

    if citation is None:
        citation = Citation(file=file_ref or "unknown", line_start=0, line_end=0)

    return Finding(
        severity=severity,
        type=finding_type,
        title=title,
        description=description,
        citation=citation,
        fix=fix,
        raw=block,
    )


def parse_findings(raw_output: str) -> list[Finding]:
    """Extract all structured findings from agent output.

    Splits on finding header lines and parses each block.
    """
    # Split on lines that look like finding headers
    blocks = re.split(r"(?=\[P[0-3]\])", raw_output, flags=re.IGNORECASE)
    findings = []
    for block in blocks:
        finding = _parse_block(block)
        if finding:
            findings.append(finding)

    # Sort by severity: P0 first
    severity_order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
    findings.sort(key=lambda f: severity_order[f.severity])
    return findings
