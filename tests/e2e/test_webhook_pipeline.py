"""E2E tests for the webhook processing pipeline.

Tests the full flow: raw GitHub payload -> signature verification ->
event parsing -> should_review filtering -> FastAPI endpoint accept/reject.

Uses real signature verification and real event parsing; only mocks
run_review_job (to avoid launching actual review jobs) and get_settings
(to control configuration without .env dependency).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from webhook.models import PullRequestEvent
from webhook.signature import verify_signature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = "e2e-test-secret-key"


def _make_signature(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Compute a valid X-Hub-Signature-256 header value."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _build_pr_payload(
    action: str = "opened",
    *,
    pr_number: int = 99,
    title: str = "E2E test PR",
    body: str | None = "Automated e2e test body",
    state: str = "open",
    user_login: str = "e2e-bot",
    user_id: int = 42,
    head_sha: str = "abc123def456",
    head_ref: str = "feature/e2e",
    base_ref: str = "main",
    repo_id: int = 777,
    repo_name: str = "test-repo",
    repo_full_name: str = "org/test-repo",
    private: bool = False,
    owner_login: str = "org",
    installation_id: int | None = 12345,
    additions: int = 10,
    deletions: int = 3,
    changed_files: int = 2,
) -> dict:
    """Build a realistic GitHub pull_request webhook payload."""
    payload: dict = {
        "action": action,
        "pull_request": {
            "number": pr_number,
            "title": title,
            "body": body,
            "state": state,
            "user": {"login": user_login, "id": user_id},
            "head": {
                "sha": head_sha,
                "ref": head_ref,
                "label": f"{user_login}:{head_ref}",
            },
            "base": {"ref": base_ref, "label": f"{owner_login}:{base_ref}"},
            "html_url": f"https://github.com/{repo_full_name}/pull/{pr_number}",
            "additions": additions,
            "deletions": deletions,
            "changed_files": changed_files,
        },
        "repository": {
            "id": repo_id,
            "name": repo_name,
            "full_name": repo_full_name,
            "private": private,
            "owner": {"login": owner_login},
        },
    }
    if installation_id is not None:
        payload["installation"] = {"id": installation_id}
    return payload


def _settings_with_secret(secret: str = WEBHOOK_SECRET) -> MagicMock:
    mock = MagicMock()
    mock.github_webhook_secret = secret
    mock.github_token = None
    mock.gemini_api_key = "test-key"
    return mock


def _settings_no_secret() -> MagicMock:
    mock = MagicMock()
    mock.github_webhook_secret = None
    mock.github_token = None
    mock.gemini_api_key = "test-key"
    return mock


# ---------------------------------------------------------------------------
# 1. Full webhook flow: opened PR -> valid signature -> accepted (202)
# ---------------------------------------------------------------------------


class TestFullFlowOpenedPR:
    @pytest.mark.asyncio
    async def test_opened_pr_with_valid_signature_returns_202_accepted(self) -> None:
        """An opened PR with a valid HMAC signature should be accepted and
        schedule a review job."""
        payload_dict = _build_pr_payload("opened")
        payload_bytes = json.dumps(payload_dict).encode()
        signature = _make_signature(payload_bytes)

        with (
            patch("webhook.router.get_settings", return_value=_settings_with_secret()),
            patch("webhook.router.run_review_job", new_callable=AsyncMock) as mock_review,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": signature,
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "org/test-repo#99" in data["pr"]
        assert data["sha"] == "abc123d"  # first 7 chars of head_sha


# ---------------------------------------------------------------------------
# 2. Full webhook flow: closed PR -> skipped
# ---------------------------------------------------------------------------


class TestFullFlowClosedPR:
    @pytest.mark.asyncio
    async def test_closed_pr_returns_skipped(self) -> None:
        """A closed PR should be parsed successfully but skipped (not reviewed)."""
        payload_dict = _build_pr_payload("closed")
        payload_bytes = json.dumps(payload_dict).encode()
        signature = _make_signature(payload_bytes)

        with (
            patch("webhook.router.get_settings", return_value=_settings_with_secret()),
            patch("webhook.router.run_review_job", new_callable=AsyncMock) as mock_review,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": signature,
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"
        assert resp.json()["action"] == "closed"
        mock_review.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Full webhook flow: invalid signature -> 401
# ---------------------------------------------------------------------------


class TestFullFlowInvalidSignature:
    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self) -> None:
        """A request with a wrong HMAC signature should be rejected with 401."""
        payload_dict = _build_pr_payload("opened")
        payload_bytes = json.dumps(payload_dict).encode()
        wrong_signature = _make_signature(payload_bytes, secret="wrong-secret")

        with patch("webhook.router.get_settings", return_value=_settings_with_secret()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": wrong_signature,
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Full webhook flow: non-PR event (push) -> ignored
# ---------------------------------------------------------------------------


class TestFullFlowNonPREvent:
    @pytest.mark.asyncio
    async def test_push_event_returns_ignored(self) -> None:
        """A push event (non pull_request) should be acknowledged but ignored."""
        payload_bytes = json.dumps({"ref": "refs/heads/main"}).encode()
        signature = _make_signature(payload_bytes)

        with patch("webhook.router.get_settings", return_value=_settings_with_secret()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "push",
                        "X-Hub-Signature-256": signature,
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["event"] == "push"

    @pytest.mark.asyncio
    async def test_issues_event_returns_ignored(self) -> None:
        """An issues event should also be ignored."""
        payload_bytes = json.dumps({"action": "opened"}).encode()
        signature = _make_signature(payload_bytes)

        with patch("webhook.router.get_settings", return_value=_settings_with_secret()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-Hub-Signature-256": signature,
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 202
        assert resp.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# 5. Payload parsing for all reviewable actions
# ---------------------------------------------------------------------------


class TestReviewableActionsParsing:
    @pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
    def test_reviewable_actions_parse_and_should_review(self, action: str) -> None:
        """All three reviewable actions must parse correctly and set should_review=True."""
        payload = _build_pr_payload(action)
        event = PullRequestEvent.from_dict(payload)

        assert event.action == action
        assert event.should_review is True
        assert event.pr_number == 99
        assert event.owner == "org"
        assert event.repo == "test-repo"
        assert event.head_sha == "abc123def456"
        assert event.pr_url == "https://github.com/org/test-repo/pull/99"

    @pytest.mark.parametrize("action", ["closed", "edited", "labeled", "assigned"])
    def test_non_reviewable_actions_should_not_review(self, action: str) -> None:
        """Non-reviewable actions must parse but return should_review=False."""
        payload = _build_pr_payload(action)
        event = PullRequestEvent.from_dict(payload)

        assert event.action == action
        assert event.should_review is False

    @pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
    @pytest.mark.asyncio
    async def test_reviewable_actions_accepted_via_endpoint(self, action: str) -> None:
        """Each reviewable action should flow through the endpoint and return accepted."""
        payload_bytes = json.dumps(_build_pr_payload(action)).encode()

        with (
            patch("webhook.router.get_settings", return_value=_settings_no_secret()),
            patch("webhook.router.run_review_job", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"


# ---------------------------------------------------------------------------
# 6. Private repo handling
# ---------------------------------------------------------------------------


class TestPrivateRepoHandling:
    def test_private_repo_parsed_correctly(self) -> None:
        """A payload from a private repo should have repository.private=True."""
        payload = _build_pr_payload("opened", private=True)
        event = PullRequestEvent.from_dict(payload)

        assert event.repository.private is True
        assert event.should_review is True

    def test_public_repo_parsed_correctly(self) -> None:
        """A payload from a public repo should have repository.private=False."""
        payload = _build_pr_payload("opened", private=False)
        event = PullRequestEvent.from_dict(payload)

        assert event.repository.private is False

    @pytest.mark.asyncio
    async def test_private_repo_accepted_via_endpoint(self) -> None:
        """Private repo PRs should flow through the endpoint normally."""
        payload_bytes = json.dumps(_build_pr_payload("opened", private=True)).encode()

        with (
            patch("webhook.router.get_settings", return_value=_settings_no_secret()),
            patch("webhook.router.run_review_job", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"


# ---------------------------------------------------------------------------
# 7. Installation ID extraction
# ---------------------------------------------------------------------------


class TestInstallationIDExtraction:
    def test_installation_id_present(self) -> None:
        """When installation.id is present in the payload, it should be extracted."""
        payload = _build_pr_payload("opened", installation_id=9876)
        event = PullRequestEvent.from_dict(payload)

        assert event.installation_id == 9876

    def test_installation_id_absent(self) -> None:
        """When no installation block exists, installation_id should be None."""
        payload = _build_pr_payload("opened", installation_id=None)
        event = PullRequestEvent.from_dict(payload)

        assert event.installation_id is None

    def test_installation_block_without_id(self) -> None:
        """An installation block without an id key should yield None."""
        payload = _build_pr_payload("opened", installation_id=None)
        payload["installation"] = {}  # empty installation block
        event = PullRequestEvent.from_dict(payload)

        assert event.installation_id is None


# ---------------------------------------------------------------------------
# 8. Malformed payload -> 400
# ---------------------------------------------------------------------------


class TestMalformedPayload:
    @pytest.mark.asyncio
    async def test_non_json_body_returns_400(self) -> None:
        """Completely invalid JSON should trigger a 400 response."""
        with patch("webhook.router.get_settings", return_value=_settings_no_secret()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=b"this is not json at all!!!",
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_json_missing_required_fields_returns_400(self) -> None:
        """Valid JSON but missing required PR fields should trigger 400."""
        bad_payload = json.dumps({"action": "opened", "not_a_pr": {}}).encode()

        with patch("webhook.router.get_settings", return_value=_settings_no_secret()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=bad_payload,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_json_object_returns_400(self) -> None:
        """An empty JSON object should trigger 400 for a pull_request event."""
        with patch("webhook.router.get_settings", return_value=_settings_no_secret()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=b"{}",
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 9. Missing signature when secret is configured -> 401
# ---------------------------------------------------------------------------


class TestMissingSignatureWithSecret:
    @pytest.mark.asyncio
    async def test_missing_signature_header_returns_401(self) -> None:
        """When a webhook secret is configured but the request has no signature
        header, the endpoint must reject with 401."""
        payload_bytes = json.dumps(_build_pr_payload("opened")).encode()

        with patch("webhook.router.get_settings", return_value=_settings_with_secret()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                        # deliberately omitting X-Hub-Signature-256
                    },
                )

        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_no_secret_configured_skips_signature_check(self) -> None:
        """When no webhook secret is configured, requests without a signature
        should still be processed normally."""
        payload_bytes = json.dumps(_build_pr_payload("opened")).encode()

        with (
            patch("webhook.router.get_settings", return_value=_settings_no_secret()),
            patch("webhook.router.run_review_job", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhook/github",
                    content=payload_bytes,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "Content-Type": "application/json",
                    },
                )

        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"


# ---------------------------------------------------------------------------
# Signature verification unit-level (real crypto, no mocks)
# ---------------------------------------------------------------------------


class TestSignatureVerificationReal:
    """Exercise the real verify_signature function end-to-end with known values."""

    def test_valid_signature_returns_true(self) -> None:
        secret = "super-secret"
        body = b'{"hello": "world"}'
        sig = _make_signature(body, secret)
        assert verify_signature(body, sig, secret) is True

    def test_wrong_secret_returns_false(self) -> None:
        body = b'{"hello": "world"}'
        sig = _make_signature(body, "correct-secret")
        assert verify_signature(body, sig, "wrong-secret") is False

    def test_tampered_body_returns_false(self) -> None:
        secret = "my-secret"
        original = b'{"amount": 100}'
        sig = _make_signature(original, secret)
        tampered = b'{"amount": 999}'
        assert verify_signature(tampered, sig, secret) is False

    def test_missing_sha256_prefix_returns_false(self) -> None:
        body = b"test"
        digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        assert verify_signature(body, digest, "secret") is False

    def test_empty_body_signature(self) -> None:
        secret = "secret"
        body = b""
        sig = _make_signature(body, secret)
        assert verify_signature(body, sig, secret) is True


# ---------------------------------------------------------------------------
# Event parsing edge cases
# ---------------------------------------------------------------------------


class TestEventParsingEdgeCases:
    def test_pull_request_body_none(self) -> None:
        """PR body can be None (e.g. empty description)."""
        payload = _build_pr_payload("opened", body=None)
        event = PullRequestEvent.from_dict(payload)
        assert event.pull_request.body is None

    def test_pull_request_fields_extracted(self) -> None:
        """Verify all PR fields are extracted correctly from a full payload."""
        payload = _build_pr_payload(
            "synchronize",
            pr_number=123,
            title="My PR",
            body="Description here",
            user_login="alice",
            user_id=55,
            head_sha="deadbeef12345678",
            head_ref="feature/x",
            base_ref="develop",
            repo_name="my-repo",
            repo_full_name="myorg/my-repo",
            owner_login="myorg",
            additions=50,
            deletions=20,
            changed_files=8,
        )
        event = PullRequestEvent.from_dict(payload)

        assert event.action == "synchronize"
        assert event.pr_number == 123
        assert event.pull_request.title == "My PR"
        assert event.pull_request.body == "Description here"
        assert event.pull_request.user.login == "alice"
        assert event.pull_request.user.id == 55
        assert event.head_sha == "deadbeef12345678"
        assert event.pull_request.head.ref == "feature/x"
        assert event.pull_request.base.ref == "develop"
        assert event.owner == "myorg"
        assert event.repo == "my-repo"
        assert event.repository.full_name == "myorg/my-repo"
        assert event.pull_request.additions == 50
        assert event.pull_request.deletions == 20
        assert event.pull_request.changed_files == 8

    def test_repository_id_and_owner(self) -> None:
        payload = _build_pr_payload("opened", repo_id=42, owner_login="testorg")
        event = PullRequestEvent.from_dict(payload)
        assert event.repository.id == 42
        assert event.repository.owner_login == "testorg"
