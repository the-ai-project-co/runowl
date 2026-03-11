"""Interactive Q&A engine for PR diffs."""

from qa.engine import QAEngine
from qa.models import CodeSelection, QAMessage, QASession, SelectionMode
from qa.selection import (
    format_selection_context,
    select_changeset,
    select_file,
    select_hunk,
    select_line,
    select_range,
)

__all__ = [
    "QAEngine",
    "QASession",
    "QAMessage",
    "CodeSelection",
    "SelectionMode",
    "select_line",
    "select_range",
    "select_hunk",
    "select_file",
    "select_changeset",
    "format_selection_context",
]
