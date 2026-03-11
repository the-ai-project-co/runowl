"""Code Review Agent — orchestrates GitHub fetch, RLM, parsing, and citation validation."""

from __future__ import annotations

import logging

from github.client import GitHubClient
from github.diff import parse_patch
from github.models import FileDiff, PRRef
from reasoning.context import build_diff_context, build_pr_summary
from reasoning.engine import ReasoningEngine, StepCallback
from reasoning.models import ConversationMessage
from review.citations import validate_citations
from review.models import ReviewResult
from review.parser import parse_findings
from review.severity import ensure_fix_for_blocking, reclassify_findings

logger = logging.getLogger(__name__)


class ReviewAgent:
    """Orchestrates a full PR code review end-to-end.

    Flow:
    1. Fetch PR metadata and diffs from GitHub.
    2. Build diff context string (up to 50 files inline, rest via tools).
    3. Run the RLM reasoning loop with Gemini.
    4. Parse structured findings from the agent output.
    5. Validate citations against visible diff hunks.
    6. Return a ReviewResult.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        self._gh = github_client
        self._engine = reasoning_engine

    async def review(
        self,
        ref: PRRef,
        step_callback: StepCallback | None = None,
    ) -> ReviewResult:
        """Run a full review of a PR and return structured findings."""
        if step_callback:
            self._engine._step_cb = step_callback

        try:
            # 1. Fetch PR data
            metadata = await self._gh.get_pr_metadata(ref)

            # 2. Build diffs
            diffs: list[FileDiff] = [parse_patch(f) for f in metadata.files]

            # 3. Build diff context for prompt
            diff_context = build_diff_context(metadata, diffs)

            # 4. Run reasoning loop
            rlm_result = await self._engine.review_pr(metadata, diff_context, ref)

            if not rlm_result.success:
                return ReviewResult(
                    success=False,
                    error=rlm_result.error or "Reasoning engine returned no output",
                    raw_output=rlm_result.output,
                )

            # 5. Parse findings
            findings = parse_findings(rlm_result.output)

            # 6. Reclassify severity based on content signals
            reclassify_findings(findings)

            # 7. Ensure blocking findings have fix suggestions
            ensure_fix_for_blocking(findings)

            # 8. Validate citations against diff hunks
            for finding in findings:
                validated = validate_citations([finding.citation], diffs)
                if not validated:
                    logger.debug("Citation not in diff, keeping with warning: %s", finding.citation)

            return ReviewResult(
                findings=findings,
                raw_output=rlm_result.output,
                pr_summary=build_pr_summary(metadata),
                success=True,
            )

        except Exception as exc:
            logger.exception("Review failed: %s", exc)
            return ReviewResult(success=False, error=str(exc))

    async def ask(
        self,
        ref: PRRef,
        question: str,
        selected_code: str = "",
        conversation: list[ConversationMessage] | None = None,
    ) -> tuple[str, list[ConversationMessage]]:
        """Answer a question about a PR, maintaining conversation history.

        Returns (answer_text, updated_conversation).
        """
        metadata = await self._gh.get_pr_metadata(ref)
        pr_context = build_pr_summary(metadata)

        result = await self._engine.ask(
            question=question,
            pr_context=pr_context,
            selected_code=selected_code,
            ref=ref,
            head_sha=metadata.head_sha,
            conversation=conversation,
        )
        return result.output, result.conversation
