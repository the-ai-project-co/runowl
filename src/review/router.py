"""HTTP API router for on-demand PR code review."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from config import get_settings
from github.client import GitHubClient
from github.models import PRRef
from reasoning.engine import ReasoningEngine
from review.agent import ReviewAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"])

_PR_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


class ReviewRequest(BaseModel):
    url: str
    model: str | None = None


class FindingOut(BaseModel):
    id: str
    severity: str
    type: str
    title: str
    description: str
    file: str
    line_start: int
    line_end: int
    suggestion: str | None


class ReviewResponse(BaseModel):
    findings: list[FindingOut]
    pr_summary: str
    success: bool
    error: str | None = None


@router.post("", response_model=ReviewResponse, summary="Run AI code review on a PR")
async def run_review(body: ReviewRequest) -> ReviewResponse:
    """Trigger a full AI code review for a GitHub PR URL."""
    match = _PR_URL_RE.match(body.url)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub PR URL. Expected: https://github.com/owner/repo/pull/123",
        )

    owner = match.group("owner")
    repo = match.group("repo")
    number = int(match.group("number"))
    ref = PRRef(owner=owner, repo=repo, number=number)

    settings = get_settings()

    async with GitHubClient(token=settings.github_token) as gh:
        engine = ReasoningEngine(github_client=gh, api_key=settings.gemini_api_key)
        agent = ReviewAgent(github_client=gh, reasoning_engine=engine)

        try:
            result = await agent.review(ref)
        except Exception as exc:
            logger.exception("Review failed for %s/%s#%d", owner, repo, number)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Review failed: {exc}",
            ) from exc

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error or "Review failed",
        )

    findings_out = [
        FindingOut(
            id=f"{f.citation.file}:{f.citation.line_start}:{i}",
            severity=f.severity.value,
            type=f.type.value,
            title=f.title,
            description=f.description,
            file=f.citation.file,
            line_start=f.citation.line_start,
            line_end=f.citation.line_end,
            suggestion=f.fix,
        )
        for i, f in enumerate(result.findings)
    ]

    return ReviewResponse(
        findings=findings_out,
        pr_summary=result.pr_summary,
        success=True,
    )
