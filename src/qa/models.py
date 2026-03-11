"""Data models for the Interactive Q&A engine."""

from dataclasses import dataclass, field
from enum import StrEnum


class SelectionMode(StrEnum):
    LINE = "line"  # single line
    RANGE = "range"  # line range
    HUNK = "hunk"  # full diff hunk
    FILE = "file"  # entire file in diff
    CHANGESET = "changeset"  # all changed files


@dataclass
class CodeSelection:
    """A user-selected code region to ask about."""

    mode: SelectionMode
    file: str
    content: str
    line_start: int | None = None
    line_end: int | None = None
    hunk_header: str | None = None

    def describe(self) -> str:
        """Human-readable description of the selection."""
        match self.mode:
            case SelectionMode.LINE:
                return f"{self.file}:{self.line_start}"
            case SelectionMode.RANGE:
                return f"{self.file}:{self.line_start}-{self.line_end}"
            case SelectionMode.HUNK:
                return f"{self.file} hunk {self.hunk_header}"
            case SelectionMode.FILE:
                return f"{self.file} (full file)"
            case SelectionMode.CHANGESET:
                return "entire changeset"


@dataclass
class QAMessage:
    role: str  # "user" | "assistant"
    question: str
    answer: str
    selection: CodeSelection | None = None
    citations: list[str] = field(default_factory=list)


@dataclass
class QASession:
    """Maintains conversation state for an interactive Q&A session."""

    pr_ref_str: str  # "owner/repo#number"
    messages: list[QAMessage] = field(default_factory=list)

    def add(self, message: QAMessage) -> None:
        self.messages.append(message)

    def last_n(self, n: int) -> list[QAMessage]:
        return self.messages[-n:]

    def reset(self) -> None:
        self.messages.clear()

    @property
    def history_text(self) -> str:
        lines = []
        for msg in self.messages:
            lines.append(f"Q: {msg.question}")
            lines.append(f"A: {msg.answer[:300]}")
        return "\n".join(lines)
