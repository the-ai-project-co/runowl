"""Interactive Q&A engine — answers questions about PR diffs with conversation history."""

from __future__ import annotations

import logging

from github.client import GitHubClient
from github.diff import parse_patch
from github.models import FileDiff, PRRef
from qa.models import CodeSelection, QAMessage, QASession
from qa.selection import format_selection_context
from reasoning.context import build_pr_summary
from reasoning.engine import ReasoningEngine
from reasoning.models import ConversationMessage
from review.citations import extract_citations

logger = logging.getLogger(__name__)

# Commands available in interactive mode
QA_COMMANDS = {
    "quit",
    "exit",
    "q",  # end session
    "help",  # show commands
    "reset",  # clear history
    "history",  # show previous Q&A
    "files",  # list changed files
    "info",  # show PR metadata summary
}


class QAEngine:
    """Interactive Q&A over a PR diff.

    Maintains a QASession with full conversation history.
    Each question is answered using the ReasoningEngine with prior
    conversation context injected so the model has continuity.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        self._gh = github_client
        self._engine = reasoning_engine
        self._sessions: dict[str, QASession] = {}
        self._diffs_cache: dict[str, list[FileDiff]] = {}
        self._pr_summary_cache: dict[str, str] = {}

    def _session_key(self, ref: PRRef) -> str:
        return f"{ref.owner}/{ref.repo}#{ref.number}"

    def get_session(self, ref: PRRef) -> QASession:
        key = self._session_key(ref)
        if key not in self._sessions:
            self._sessions[key] = QASession(pr_ref_str=key)
        return self._sessions[key]

    def reset_session(self, ref: PRRef) -> None:
        self.get_session(ref).reset()

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _ensure_loaded(self, ref: PRRef) -> tuple[list[FileDiff], str]:
        """Load and cache PR diffs and summary for a ref."""
        key = self._session_key(ref)
        if key not in self._diffs_cache:
            metadata = await self._gh.get_pr_metadata(ref)
            self._diffs_cache[key] = [parse_patch(f) for f in metadata.files]
            self._pr_summary_cache[key] = build_pr_summary(metadata)
        return self._diffs_cache[key], self._pr_summary_cache[key]

    def _build_conversation(self, session: QASession) -> list[ConversationMessage]:
        """Convert QASession messages into ConversationMessage history."""
        history: list[ConversationMessage] = []
        for msg in session.last_n(6):  # keep last 6 exchanges for context
            history.append(ConversationMessage(role="user", content=msg.question))
            history.append(ConversationMessage(role="model", content=msg.answer))
        return history

    # ── Main ask method ───────────────────────────────────────────────────────

    async def ask(
        self,
        ref: PRRef,
        question: str,
        selection: CodeSelection | None = None,
    ) -> QAMessage:
        """Ask a question about a PR, with optional code selection context.

        Maintains conversation history within the session.
        Returns a QAMessage with the answer and extracted citations.
        """
        diffs, pr_summary = await self._ensure_loaded(ref)
        session = self.get_session(ref)
        history = self._build_conversation(session)

        selection_context = format_selection_context(selection)

        result = await self._engine.ask(
            question=question,
            pr_context=pr_summary,
            selected_code=selection_context,
            ref=ref,
            head_sha=self._get_head_sha(ref),
            conversation=history,
        )

        answer = result.output or "(no answer returned)"
        citations = [str(c) for c in extract_citations(answer)]

        message = QAMessage(
            role="assistant",
            question=question,
            answer=answer,
            selection=selection,
            citations=citations,
        )
        session.add(message)
        return message

    def _get_head_sha(self, ref: PRRef) -> str:
        """Return empty string — head SHA is resolved inside the reasoning engine."""
        return ""

    # ── Command handling ──────────────────────────────────────────────────────

    def handle_command(self, ref: PRRef, command: str) -> str | None:
        """Handle a special command. Returns output string or None if not a command."""
        cmd = command.strip().lower()

        if cmd in ("quit", "exit", "q"):
            return "SESSION_END"

        if cmd == "help":
            return (
                "Available commands:\n"
                "  quit / exit / q  — end session\n"
                "  reset            — clear conversation history\n"
                "  history          — show previous Q&A\n"
                "  files            — list changed files\n"
                "  info             — show PR summary\n"
            )

        if cmd == "reset":
            self.reset_session(ref)
            return "Conversation history cleared."

        if cmd == "history":
            session = self.get_session(ref)
            if not session.messages:
                return "No conversation history yet."
            lines = []
            for i, msg in enumerate(session.messages, 1):
                lines.append(f"[{i}] Q: {msg.question}")
                lines.append(f"    A: {msg.answer[:200]}{'...' if len(msg.answer) > 200 else ''}")
            return "\n".join(lines)

        if cmd == "files":
            key = self._session_key(ref)
            diffs = self._diffs_cache.get(key, [])
            if not diffs:
                return "PR not yet loaded. Ask a question first."
            lines = [f"  {d.filename} [{d.status}] +{d.additions}/−{d.deletions}" for d in diffs]
            return "Changed files:\n" + "\n".join(lines)

        if cmd == "info":
            key = self._session_key(ref)
            summary = self._pr_summary_cache.get(key)
            return summary or "PR not yet loaded. Ask a question first."

        return None  # not a command
