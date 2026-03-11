"""Data models for code review findings and results."""

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    P0 = "P0"  # critical — data loss, security breach, production crash
    P1 = "P1"  # high — significant bug or security risk, should block merge
    P2 = "P2"  # medium — code quality, minor security concern
    P3 = "P3"  # low — style, naming, minor improvement


class FindingType(StrEnum):
    BUG = "bug"
    SECURITY = "security"
    INVESTIGATION = "investigation"
    INFORMATIONAL = "informational"


@dataclass
class Citation:
    """A reference to a specific location in the diff."""

    file: str
    line_start: int
    line_end: int

    def __str__(self) -> str:
        if self.line_start == self.line_end:
            return f"{self.file}:{self.line_start}"
        return f"{self.file}:{self.line_start}-{self.line_end}"


@dataclass
class Finding:
    severity: Severity
    type: FindingType
    title: str
    description: str
    citation: Citation
    fix: str | None = None  # required for P0/P1
    raw: str = ""  # original text block from agent output

    @property
    def blocks_merge(self) -> bool:
        return self.severity in (Severity.P0, Severity.P1)


@dataclass
class ReviewResult:
    findings: list[Finding] = field(default_factory=list)
    raw_output: str = ""
    pr_summary: str = ""
    success: bool = True
    error: str | None = None

    @property
    def critical(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.P0]

    @property
    def high(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.P1]

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocks_merge]

    def by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def by_type(self, finding_type: FindingType) -> list[Finding]:
        return [f for f in self.findings if f.type == finding_type]
