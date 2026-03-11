"""Background review job triggered by webhook events."""

from __future__ import annotations

import logging

from config import Settings
from github.client import GitHubClient
from github.models import PRRef
from reasoning.engine import ReasoningEngine
from review.agent import ReviewAgent
from review.formatter import format_review_markdown
from testing.executor import execute_suite
from testing.generator import TestGenerationAgent
from testing.results import format_results_markdown
from webhook.check_run import finish_check_run, start_check_run
from webhook.models import PullRequestEvent

logger = logging.getLogger(__name__)


async def run_review_job(event: PullRequestEvent, settings: Settings) -> None:
    """Execute the full review pipeline for a PR event.

    Steps:
    1. Create an in-progress GitHub Check Run.
    2. Run ReviewAgent (fetch PR → RLM → parse findings).
    3. Post the review as a PR comment.
    4. Update the Check Run to pass/fail based on blocking findings.
    """
    owner = event.owner
    repo = event.repo
    pr_number = event.pr_number
    head_sha = event.head_sha

    logger.info("Starting review job: %s/%s#%d", owner, repo, pr_number)

    async with GitHubClient(token=settings.github_token) as gh:
        # 1. Start Check Run
        check_run_id = await start_check_run(gh, owner, repo, head_sha)

        try:
            ref = PRRef(owner=owner, repo=repo, number=pr_number)
            engine = ReasoningEngine(github_client=gh, api_key=settings.gemini_api_key)
            agent = ReviewAgent(github_client=gh, reasoning_engine=engine)

            # 2. Run review
            result = await agent.review(ref)

            if not result.success:
                logger.error("Review failed for %s/%s#%d: %s", owner, repo, pr_number, result.error)
                await _fail_check_run(
                    gh, owner, repo, check_run_id, result.error or "Review failed"
                )
                return

            # 3. Post PR comment
            comment_body = format_review_markdown(result)
            try:
                await gh.post_pr_comment(ref, comment_body)
                logger.info("Posted review comment on %s/%s#%d", owner, repo, pr_number)
            except Exception:
                logger.exception("Failed to post PR comment on %s/%s#%d", owner, repo, pr_number)

            # 4. Finish Check Run
            await finish_check_run(gh, owner, repo, check_run_id, result)

            # 5. Generate + run tests (if Anthropic key configured)
            if settings.anthropic_api_key:
                try:
                    metadata = await gh.get_pr_metadata(ref)
                    test_agent = TestGenerationAgent(gh, settings.anthropic_api_key)
                    gen = await test_agent.generate(ref, metadata)
                    if gen.success:
                        suite = await execute_suite(gen.suite, metadata.body or "")
                        test_comment = format_results_markdown(suite)
                        await gh.post_pr_comment(ref, test_comment)
                        logger.info(
                            "Posted test results (%d/%d passed) on %s/%s#%d",
                            suite.passed, suite.total, owner, repo, pr_number,
                        )
                except Exception:
                    logger.exception("Test generation/execution failed for %s/%s#%d", owner, repo, pr_number)

        except Exception:
            logger.exception("Unhandled error in review job for %s/%s#%d", owner, repo, pr_number)
            await _fail_check_run(gh, owner, repo, check_run_id, "Internal error during review")


async def _fail_check_run(
    gh: GitHubClient,
    owner: str,
    repo: str,
    check_run_id: int,
    message: str,
) -> None:
    """Mark the check run as failed with an error message."""
    if check_run_id < 0:
        return
    try:
        await gh.update_check_run(
            owner=owner,
            repo=repo,
            check_run_id=check_run_id,
            conclusion="failure",
            output={
                "title": "RunOwl Code Review",
                "summary": f"Review could not complete: {message}",
            },
        )
    except Exception:
        logger.exception("Failed to mark check run %d as failed", check_run_id)
