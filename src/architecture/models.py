"""Architecture analysis models — stub in the public distribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ArchCheckType(StrEnum):
    SINGLE_RESPONSIBILITY = "single_responsibility"
    OPEN_CLOSED = "open_closed"
    LISKOV_SUBSTITUTION = "liskov_substitution"
    INTERFACE_SEGREGATION = "interface_segregation"
    DEPENDENCY_INVERSION = "dependency_inversion"
    LONG_METHOD = "long_method"
    DEEP_NESTING = "deep_nesting"
    FEATURE_ENVY = "feature_envy"


@dataclass
class ArchFinding:
    check_type: ArchCheckType
    file: str
    line: int
    message: str
    severity: str = "medium"


@dataclass
class ArchReport:
    findings: list[ArchFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.findings) == 0
