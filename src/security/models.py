"""Data models for security analysis."""

from dataclasses import dataclass, field
from enum import StrEnum


class SecurityCheckType(StrEnum):
    HARDCODED_SECRET = "hardcoded_secret"
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    MISSING_AUTH = "missing_auth"
    EXPOSED_ENV = "exposed_env"
    UNPINNED_DEPENDENCY = "unpinned_dependency"


@dataclass
class SecurityHit:
    check: SecurityCheckType
    file: str
    line: int
    snippet: str  # the offending line (truncated)
    message: str  # human-readable description
    fix: str  # concrete remediation
    is_free: bool = True  # True = surface check (free), False = deep check (paid)

    @property
    def citation(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass
class SecurityReport:
    hits: list[SecurityHit] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def has_issues(self) -> bool:
        return len(self.hits) > 0

    def by_check(self, check: SecurityCheckType) -> list[SecurityHit]:
        return [h for h in self.hits if h.check == check]
