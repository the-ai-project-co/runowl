"""Tests for the testing FastAPI router (HTTP endpoint tests)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from testing.models import FrameworkType, TestResult, TestStatus, TestSuite


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings_no_anthropic():
    mock = MagicMock()
    mock.anthropic_api_key = None
    mock.github_token = "gh_token"
    return mock


@pytest.fixture
def settings_with_anthropic():
    mock = MagicMock()
    mock.anthropic_api_key = "sk-ant-test"
    mock.github_token = "gh_token"
    return mock


def _pr_payload(owner: str = "acme", repo: str = "api", pr_number: int = 7) -> dict:
    return {"owner": owner, "repo": repo, "pr_number": pr_number}


def _make_metadata() -> MagicMock:
    meta = MagicMock()
    meta.title = "Add feature"
    meta.author = "alice"
    meta.head_branch = "feature"
    meta.base_branch = "main"
    meta.head_sha = "abc123"
    meta.changed_files = 3
    meta.additions = 50
    meta.deletions = 10
    meta.body = "Implements feature X"
    return meta


def _make_successful_gen_result(suite_id: str = "abc123456789") -> MagicMock:
    suite = TestSuite(id=suite_id, pr_ref="acme/api#7", framework=FrameworkType.PYTEST)
    suite.generation_success = True
    result = MagicMock()
    result.success = True
    result.suite = suite
    result.error = None
    return result


def _make_failed_gen_result() -> MagicMock:
    suite = TestSuite(pr_ref="acme/api#7")
    suite.generation_success = False
    suite.generation_error = "No test cases produced"
    result = MagicMock()
    result.success = False
    result.suite = suite
    result.error = "No test cases produced"
    return result


# ---------------------------------------------------------------------------
# POST /tests/generate
# ---------------------------------------------------------------------------


class TestGenerateEndpoint:
    @pytest.mark.asyncio
    async def test_returns_501_when_no_anthropic_key(self, settings_no_anthropic) -> None:
        with patch("testing.router.get_settings", return_value=settings_no_anthropic):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/tests/generate", json=_pr_payload())
        assert resp.status_code == 501
        assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_returns_404_when_pr_not_found(self, settings_with_anthropic) -> None:
        with (
            patch("testing.router.get_settings", return_value=settings_with_anthropic),
            patch(
                "testing.router.GitHubClient.get_pr_metadata",
                new_callable=AsyncMock,
                side_effect=Exception("Not Found"),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/tests/generate", json=_pr_payload())
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_happy_path_returns_suite_id(self, settings_with_anthropic) -> None:
        gen_result = _make_successful_gen_result("suite_abc123")
        metadata = _make_metadata()

        with (
            patch("testing.router.get_settings", return_value=settings_with_anthropic),
            patch("testing.router.GitHubClient") as MockGH,
            patch("testing.router.TestGenerationAgent") as MockAgent,
        ):
            gh_instance = AsyncMock()
            gh_instance.get_pr_metadata = AsyncMock(return_value=metadata)
            MockGH.return_value = gh_instance

            agent_instance = AsyncMock()
            agent_instance.generate = AsyncMock(return_value=gen_result)
            MockAgent.return_value = agent_instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/tests/generate", json=_pr_payload())

        assert resp.status_code == 200
        data = resp.json()
        assert data["suite_id"] == "suite_abc123"
        assert data["status"] == "generated"

    @pytest.mark.asyncio
    async def test_generation_failure_returns_failed_status(self, settings_with_anthropic) -> None:
        gen_result = _make_failed_gen_result()
        metadata = _make_metadata()

        with (
            patch("testing.router.get_settings", return_value=settings_with_anthropic),
            patch("testing.router.GitHubClient") as MockGH,
            patch("testing.router.TestGenerationAgent") as MockAgent,
        ):
            gh_instance = AsyncMock()
            gh_instance.get_pr_metadata = AsyncMock(return_value=metadata)
            MockGH.return_value = gh_instance

            agent_instance = AsyncMock()
            agent_instance.generate = AsyncMock(return_value=gen_result)
            MockAgent.return_value = agent_instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/tests/generate", json=_pr_payload())

        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# POST /tests/run
# ---------------------------------------------------------------------------


class TestRunEndpoint:
    @pytest.mark.asyncio
    async def test_returns_running_status_on_success(self, settings_with_anthropic) -> None:
        gen_result = _make_successful_gen_result()
        metadata = _make_metadata()

        with (
            patch("testing.router.get_settings", return_value=settings_with_anthropic),
            patch("testing.router.GitHubClient") as MockGH,
            patch("testing.router.TestGenerationAgent") as MockAgent,
        ):
            gh_instance = AsyncMock()
            gh_instance.get_pr_metadata = AsyncMock(return_value=metadata)
            MockGH.return_value = gh_instance

            agent_instance = AsyncMock()
            agent_instance.generate = AsyncMock(return_value=gen_result)
            MockAgent.return_value = agent_instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/tests/run", json=_pr_payload())

        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_returns_generation_failed_when_agent_fails(self, settings_with_anthropic) -> None:
        gen_result = _make_failed_gen_result()
        metadata = _make_metadata()

        with (
            patch("testing.router.get_settings", return_value=settings_with_anthropic),
            patch("testing.router.GitHubClient") as MockGH,
            patch("testing.router.TestGenerationAgent") as MockAgent,
        ):
            gh_instance = AsyncMock()
            gh_instance.get_pr_metadata = AsyncMock(return_value=metadata)
            MockGH.return_value = gh_instance

            agent_instance = AsyncMock()
            agent_instance.generate = AsyncMock(return_value=gen_result)
            MockAgent.return_value = agent_instance

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/tests/run", json=_pr_payload())

        assert resp.status_code == 200
        assert resp.json()["status"] == "generation_failed"


# ---------------------------------------------------------------------------
# GET /tests/{suite_id}
# ---------------------------------------------------------------------------


class TestGetResultsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_404_when_suite_not_found(self) -> None:
        with patch("testing.router.load_suite", return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/tests/missing_suite_id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_200_with_suite_data(self) -> None:
        suite = TestSuite(id="found_suite", pr_ref="owner/repo#1", framework=FrameworkType.PYTEST)
        suite.generation_success = True
        suite.results.append(
            TestResult(test_id="t1", test_name="test_one", status=TestStatus.PASS)
        )

        with patch("testing.router.load_suite", return_value=suite):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/tests/found_suite")

        assert resp.status_code == 200
        data = resp.json()
        assert data["suite_id"] == "found_suite"
        assert data["pr_ref"] == "owner/repo#1"
        assert len(data["results"]) == 1

    @pytest.mark.asyncio
    async def test_schema_includes_new_fields(self) -> None:
        """Verify that the JSON schema includes retry_count, thumbnail_path, replay_events."""
        suite = TestSuite(id="schema_suite", pr_ref="owner/repo#1", framework=FrameworkType.PYTEST)
        suite.generation_success = True
        result = TestResult(
            test_id="t1",
            test_name="test_schema",
            status=TestStatus.PASS,
            retry_count=1,
            thumbnail_path="/path/to/thumb.jpg",
        )
        suite.results.append(result)

        with patch("testing.router.load_suite", return_value=suite):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/tests/schema_suite")

        data = resp.json()
        result_data = data["results"][0]
        assert "retry_count" in result_data
        assert result_data["retry_count"] == 1
        assert "thumbnail_path" in result_data
        assert result_data["thumbnail_path"] == "/path/to/thumb.jpg"
        assert "replay_events" in result_data
