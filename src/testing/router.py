"""FastAPI router for the Testing Engine (Phase 2a).

Endpoints:
  POST /tests/generate        — generate tests for a PR (no execution)
  POST /tests/run             — generate + execute tests for a PR
  GET  /tests/{suite_id}      — retrieve results for a previous suite
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from config import get_settings
from github.client import GitHubClient
from github.models import PRRef
from testing.executor import execute_suite
from testing.generator import TestGenerationAgent
from testing.models import TestSuite
from testing.results import format_results_json, load_suite

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tests", tags=["tests"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TestRequest(BaseModel):
    owner: str
    repo: str
    pr_number: int


class TestResponse(BaseModel):
    suite_id: str
    pr_ref: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=TestResponse)
async def generate_tests(req: TestRequest) -> TestResponse:
    """Generate (but do not execute) tests for a PR."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=501, detail="ANTHROPIC_API_KEY not configured")

    ref = PRRef(owner=req.owner, repo=req.repo, number=req.pr_number)
    client = GitHubClient(token=settings.github_token)

    try:
        metadata = await client.get_pr_metadata(ref)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"PR not found: {exc}") from exc

    agent = TestGenerationAgent(client, settings.anthropic_api_key)
    gen_result = await agent.generate(ref, metadata)

    return TestResponse(
        suite_id=gen_result.suite.id,
        pr_ref=gen_result.suite.pr_ref,
        status="generated" if gen_result.success else "failed",
        message=(
            f"Generated {len(gen_result.suite.cases)} test cases"
            if gen_result.success
            else gen_result.error or "Generation failed"
        ),
    )


@router.post("/run", response_model=TestResponse)
async def run_tests(req: TestRequest, background_tasks: BackgroundTasks) -> TestResponse:
    """Generate and execute tests for a PR (runs in background)."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=501, detail="ANTHROPIC_API_KEY not configured")

    ref = PRRef(owner=req.owner, repo=req.repo, number=req.pr_number)
    client = GitHubClient(token=settings.github_token)

    try:
        metadata = await client.get_pr_metadata(ref)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"PR not found: {exc}") from exc

    agent = TestGenerationAgent(client, settings.anthropic_api_key)
    gen_result = await agent.generate(ref, metadata)

    if not gen_result.success:
        return TestResponse(
            suite_id=gen_result.suite.id,
            pr_ref=gen_result.suite.pr_ref,
            status="generation_failed",
            message=gen_result.error or "No test cases generated",
        )

    background_tasks.add_task(
        execute_suite,
        gen_result.suite,
        metadata.body or "",
    )

    return TestResponse(
        suite_id=gen_result.suite.id,
        pr_ref=gen_result.suite.pr_ref,
        status="running",
        message=f"Executing {len(gen_result.suite.cases)} generated tests in background",
    )


@router.get("/{suite_id}")
async def get_results(suite_id: str) -> dict:
    """Retrieve results for a completed test suite."""
    suite = load_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Suite {suite_id!r} not found")
    return format_results_json(suite)
