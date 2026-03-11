"""FastAPI webhook router — receives GitHub PR events and triggers reviews."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from config import Settings, get_settings
from webhook.models import PullRequestEvent
from webhook.reviewer import run_review_job
from webhook.signature import verify_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Actions that trigger an automatic review
_REVIEW_ACTIONS = frozenset({"opened", "synchronize", "reopened"})


@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
    summary="GitHub webhook receiver",
    description=(
        "Receives GitHub pull_request webhook events and triggers async code reviews. "
        "Validates HMAC-SHA256 signature when GITHUB_WEBHOOK_SECRET is configured."
    ),
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
) -> dict[str, str]:
    """Handle incoming GitHub webhook events."""
    settings: Settings = get_settings()

    # 1. Verify signature when secret is configured
    raw_body = await request.body()
    if settings.github_webhook_secret:
        if not x_hub_signature_256:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header",
            )
        if not verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    # 2. Only handle pull_request events
    if x_github_event != "pull_request":
        logger.debug("Ignoring event type: %s", x_github_event)
        return {"status": "ignored", "event": x_github_event}

    # 3. Parse the payload
    try:
        payload: dict[str, Any] = await request.json()
        event = PullRequestEvent.from_dict(payload)
    except Exception as exc:
        logger.warning("Failed to parse webhook payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {exc}",
        ) from exc

    # 4. Only review on relevant actions
    if not event.should_review:
        logger.info(
            "Skipping action '%s' for %s/%s#%d",
            event.action,
            event.owner,
            event.repo,
            event.pr_number,
        )
        return {"status": "skipped", "action": event.action}

    # 5. Kick off the async review job
    logger.info(
        "Scheduling review for %s/%s#%d (action=%s, sha=%s)",
        event.owner,
        event.repo,
        event.pr_number,
        event.action,
        event.head_sha[:7],
    )
    background_tasks.add_task(run_review_job, event, settings)

    return {
        "status": "accepted",
        "pr": f"{event.owner}/{event.repo}#{event.pr_number}",
        "sha": event.head_sha[:7],
    }
