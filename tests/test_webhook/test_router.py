"""Tests for the webhook FastAPI router."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


def _make_sig(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _pr_payload(action: str = "opened") -> dict:
    return {
        "action": action,
        "pull_request": {
            "number": 42,
            "title": "Test PR",
            "body": None,
            "state": "open",
            "user": {"login": "alice", "id": 1},
            "head": {"sha": "deadbeef1234", "ref": "feature", "label": "alice:feature"},
            "base": {"ref": "main", "label": "owner:main"},
            "html_url": "https://github.com/owner/repo/pull/42",
        },
        "repository": {
            "id": 1,
            "name": "repo",
            "full_name": "owner/repo",
            "private": False,
            "owner": {"login": "owner"},
        },
    }


@pytest.fixture
def settings_no_secret():
    """Settings with no webhook secret (signature check disabled)."""
    mock = MagicMock()
    mock.github_webhook_secret = None
    mock.github_token = None
    mock.gemini_api_key = "test-key"
    return mock


@pytest.fixture
def settings_with_secret():
    """Settings with a webhook secret."""
    mock = MagicMock()
    mock.github_webhook_secret = "my-secret"
    mock.github_token = None
    mock.gemini_api_key = "test-key"
    return mock


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestWebhookEndpoint:
    @pytest.mark.asyncio
    async def test_non_pr_event_ignored(self, settings_no_secret) -> None:
        with patch("webhook.router.get_settings", return_value=settings_no_secret):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=b"{}",
                    headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
                )
        assert resp.status_code == 202
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_pr_closed_action_skipped(self, settings_no_secret) -> None:
        payload = json.dumps(_pr_payload("closed")).encode()
        with patch("webhook.router.get_settings", return_value=settings_no_secret):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )
        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_pr_opened_accepted(self, settings_no_secret) -> None:
        payload = json.dumps(_pr_payload("opened")).encode()
        with (
            patch("webhook.router.get_settings", return_value=settings_no_secret),
            patch("webhook.router.run_review_job", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "owner/repo#42" in data["pr"]

    @pytest.mark.asyncio
    async def test_pr_synchronize_accepted(self, settings_no_secret) -> None:
        payload = json.dumps(_pr_payload("synchronize")).encode()
        with (
            patch("webhook.router.get_settings", return_value=settings_no_secret),
            patch("webhook.router.run_review_job", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )
        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, settings_with_secret) -> None:
        payload = json.dumps(_pr_payload("opened")).encode()
        sig = _make_sig(payload, "my-secret")
        with (
            patch("webhook.router.get_settings", return_value=settings_with_secret),
            patch("webhook.router.run_review_job", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": sig,
                        "Content-Type": "application/json",
                    },
                )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, settings_with_secret) -> None:
        payload = json.dumps(_pr_payload("opened")).encode()
        with patch("webhook.router.get_settings", return_value=settings_with_secret):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": "sha256=invalid",
                        "Content-Type": "application/json",
                    },
                )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_signature_rejected(self, settings_with_secret) -> None:
        payload = json.dumps(_pr_payload("opened")).encode()
        with patch("webhook.router.get_settings", return_value=settings_with_secret):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_json_rejected(self, settings_no_secret) -> None:
        with patch("webhook.router.get_settings", return_value=settings_no_secret):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=b"not json",
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )
        assert resp.status_code == 400
