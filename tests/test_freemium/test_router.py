"""Tests for the license validation FastAPI endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from config import Tier
from main import app


@pytest.fixture
def free_settings():
    m = MagicMock()
    m.runowl_api_key = None
    m.runowl_tier = Tier.FREE
    m.github_token = None
    m.gemini_api_key = "test"
    m.github_webhook_secret = None
    return m


@pytest.fixture
def team_settings():
    m = MagicMock()
    m.runowl_api_key = "rwl_team_key"
    m.runowl_tier = Tier.FREE  # key present but tier not overridden
    m.github_token = None
    m.gemini_api_key = "test"
    m.github_webhook_secret = None
    return m


class TestGetTierEndpoint:
    @pytest.mark.asyncio
    async def test_free_tier_no_key(self, free_settings) -> None:
        with patch("freemium.router.get_settings", return_value=free_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/license/tier")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "free"
        assert not data["is_paid"]
        assert "surface_security" in data["features"]
        assert "deep_security" not in data["features"]

    @pytest.mark.asyncio
    async def test_team_tier_with_api_key_header(self, free_settings) -> None:
        with patch("freemium.router.get_settings", return_value=free_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/license/tier",
                    headers={"X-RunOwl-Api-Key": "rwl_some_key"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "team"
        assert data["is_paid"]
        assert "deep_security" in data["features"]
        assert "solid_analysis" in data["features"]

    @pytest.mark.asyncio
    async def test_team_tier_from_settings(self, team_settings) -> None:
        with patch("freemium.router.get_settings", return_value=team_settings):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/license/tier")
        assert resp.status_code == 200
        assert resp.json()["tier"] == "team"


class TestValidateEndpoint:
    @pytest.mark.asyncio
    async def test_valid_key_returns_team(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/license/validate",
                json={"api_key": "rwl_abc123"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"]
        assert data["tier"] == "team"

    @pytest.mark.asyncio
    async def test_empty_key_returns_400(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/license/validate",
                json={"api_key": ""},
            )
        assert resp.status_code == 400


class TestListFeaturesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_all_features(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/license/features")
        assert resp.status_code == 200
        data = resp.json()
        assert "surface_security" in data
        assert "deep_security" in data
        assert "solid_analysis" in data
        assert data["surface_security"] == "free"
        assert data["deep_security"] == "team"
        assert data["solid_analysis"] == "team"
        assert data["self_hosted"] == "enterprise"


class TestPromptFormatters:
    def test_cli_prompt_contains_upgrade_url(self) -> None:
        from freemium.gate import check_feature
        from freemium.models import Feature
        from freemium.prompt import format_upgrade_prompt_cli

        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        prompt = format_upgrade_prompt_cli(result)
        assert "runowl.ai" in prompt
        assert "upgrade" in prompt.lower() or "plan" in prompt.lower()

    def test_markdown_prompt_contains_link(self) -> None:
        from freemium.gate import check_feature
        from freemium.models import Feature
        from freemium.prompt import format_upgrade_prompt_markdown

        result = check_feature(Tier.FREE, Feature.SOLID_ANALYSIS)
        prompt = format_upgrade_prompt_markdown(result)
        assert "runowl.ai" in prompt
        assert "Upgrade" in prompt

    def test_gated_error_cli_prompt(self) -> None:
        from freemium.gate import FeatureGatedError, check_feature
        from freemium.models import Feature
        from freemium.prompt import format_gated_error_cli

        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        exc = FeatureGatedError(result)
        prompt = format_gated_error_cli(exc)
        assert "plan" in prompt.lower() or "upgrade" in prompt.lower()
