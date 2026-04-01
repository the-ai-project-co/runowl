"""E2E tests for the freemium / licensing pipeline.

Tests feature gating across all 4 tiers, license validation,
FastAPI license endpoints, and capability accumulation.

Uses real gate logic and real model checks; only mocks get_settings
for FastAPI endpoint tests to avoid requiring a .env file.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from config import Tier
from freemium.gate import (
    FeatureGatedError,
    check_feature,
    get_capabilities,
    is_paid,
    require_feature,
)
from freemium.license import detect_tier, validate_api_key
from freemium.models import Feature, _FEATURE_MIN_TIER, _TIER_RANK
from freemium.prompt import (
    format_gated_error_cli,
    format_gated_error_markdown,
    format_upgrade_prompt_cli,
    format_upgrade_prompt_markdown,
)
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FREE_FEATURES = {Feature.SURFACE_SECURITY, Feature.CODE_REVIEW, Feature.QA_SESSION, Feature.WEBHOOK}
TEAM_FEATURES = {Feature.DEEP_SECURITY, Feature.SOLID_ANALYSIS, Feature.PR_COMMENT_AUTO, Feature.CHECK_RUNS}
BUSINESS_FEATURES = {Feature.PRIORITY_SUPPORT, Feature.SSO}
ENTERPRISE_FEATURES = {Feature.SELF_HOSTED, Feature.AUDIT_LOG}

ALL_FEATURES = FREE_FEATURES | TEAM_FEATURES | BUSINESS_FEATURES | ENTERPRISE_FEATURES


def _free_settings() -> MagicMock:
    m = MagicMock()
    m.runowl_api_key = None
    m.runowl_tier = Tier.FREE
    m.github_token = None
    m.gemini_api_key = "test"
    m.github_webhook_secret = None
    return m


def _team_settings() -> MagicMock:
    m = MagicMock()
    m.runowl_api_key = "rwl_team_key"
    m.runowl_tier = Tier.FREE  # key present, tier not overridden -> detect_tier returns TEAM
    m.github_token = None
    m.gemini_api_key = "test"
    m.github_webhook_secret = None
    return m


def _business_settings() -> MagicMock:
    m = MagicMock()
    m.runowl_api_key = "rwl_biz_key"
    m.runowl_tier = Tier.BUSINESS  # explicit override
    m.github_token = None
    m.gemini_api_key = "test"
    m.github_webhook_secret = None
    return m


def _enterprise_settings() -> MagicMock:
    m = MagicMock()
    m.runowl_api_key = "rwl_ent_key"
    m.runowl_tier = Tier.ENTERPRISE
    m.github_token = None
    m.gemini_api_key = "test"
    m.github_webhook_secret = None
    return m


# ---------------------------------------------------------------------------
# 1. Full tier progression
# ---------------------------------------------------------------------------


class TestTierProgression:
    """Verify each tier unlocks its expected features and blocks higher-tier features."""

    def test_free_tier_unlocks_only_free_features(self) -> None:
        caps = get_capabilities(Tier.FREE)
        for feat in FREE_FEATURES:
            assert caps.has(feat), f"FREE tier should have {feat}"
        for feat in TEAM_FEATURES | BUSINESS_FEATURES | ENTERPRISE_FEATURES:
            assert not caps.has(feat), f"FREE tier should NOT have {feat}"

    def test_team_tier_unlocks_free_and_team_features(self) -> None:
        caps = get_capabilities(Tier.TEAM)
        for feat in FREE_FEATURES | TEAM_FEATURES:
            assert caps.has(feat), f"TEAM tier should have {feat}"
        for feat in BUSINESS_FEATURES | ENTERPRISE_FEATURES:
            assert not caps.has(feat), f"TEAM tier should NOT have {feat}"

    def test_business_tier_unlocks_up_to_business_features(self) -> None:
        caps = get_capabilities(Tier.BUSINESS)
        for feat in FREE_FEATURES | TEAM_FEATURES | BUSINESS_FEATURES:
            assert caps.has(feat), f"BUSINESS tier should have {feat}"
        for feat in ENTERPRISE_FEATURES:
            assert not caps.has(feat), f"BUSINESS tier should NOT have {feat}"

    def test_enterprise_tier_unlocks_all_features(self) -> None:
        caps = get_capabilities(Tier.ENTERPRISE)
        for feat in ALL_FEATURES:
            assert caps.has(feat), f"ENTERPRISE tier should have {feat}"

    def test_check_feature_allows_own_tier(self) -> None:
        result = check_feature(Tier.TEAM, Feature.DEEP_SECURITY)
        assert result.allowed is True
        assert result.blocked is False

    def test_check_feature_blocks_higher_tier(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        assert result.allowed is False
        assert result.blocked is True
        assert result.required_tier == Tier.TEAM

    def test_require_feature_raises_for_blocked(self) -> None:
        with pytest.raises(FeatureGatedError):
            require_feature(Tier.FREE, Feature.DEEP_SECURITY)

    def test_require_feature_passes_for_allowed(self) -> None:
        # Should not raise
        require_feature(Tier.FREE, Feature.CODE_REVIEW)
        require_feature(Tier.TEAM, Feature.DEEP_SECURITY)
        require_feature(Tier.BUSINESS, Feature.SSO)
        require_feature(Tier.ENTERPRISE, Feature.SELF_HOSTED)


# ---------------------------------------------------------------------------
# 2. Capability superset chain: FREE < TEAM < BUSINESS < ENTERPRISE
# ---------------------------------------------------------------------------


class TestCapabilitySupersetChain:
    def test_free_subset_of_team(self) -> None:
        free_caps = get_capabilities(Tier.FREE).features
        team_caps = get_capabilities(Tier.TEAM).features
        assert free_caps < team_caps, "FREE features must be a strict subset of TEAM"

    def test_team_subset_of_business(self) -> None:
        team_caps = get_capabilities(Tier.TEAM).features
        biz_caps = get_capabilities(Tier.BUSINESS).features
        assert team_caps < biz_caps, "TEAM features must be a strict subset of BUSINESS"

    def test_business_subset_of_enterprise(self) -> None:
        biz_caps = get_capabilities(Tier.BUSINESS).features
        ent_caps = get_capabilities(Tier.ENTERPRISE).features
        assert biz_caps < ent_caps, "BUSINESS features must be a strict subset of ENTERPRISE"

    def test_full_chain(self) -> None:
        """Verify the full inclusion chain in one assertion."""
        free = get_capabilities(Tier.FREE).features
        team = get_capabilities(Tier.TEAM).features
        biz = get_capabilities(Tier.BUSINESS).features
        ent = get_capabilities(Tier.ENTERPRISE).features

        assert free < team < biz < ent

    def test_enterprise_contains_all_defined_features(self) -> None:
        ent_caps = get_capabilities(Tier.ENTERPRISE).features
        all_defined = set(Feature)
        assert ent_caps == all_defined


# ---------------------------------------------------------------------------
# 3. FeatureGatedError contains correct upgrade URL, message, tiers
# ---------------------------------------------------------------------------


class TestFeatureGatedErrorDetails:
    def test_error_contains_upgrade_url(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        exc = FeatureGatedError(result)
        assert "runowl.ai/pricing" in exc.upgrade_url
        assert "#team" in exc.upgrade_url

    def test_error_contains_upgrade_message(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        exc = FeatureGatedError(result)
        assert "Team plan" in exc.upgrade_message or "team" in exc.upgrade_message.lower()

    def test_error_contains_tier_info_in_str(self) -> None:
        result = check_feature(Tier.FREE, Feature.SSO)
        exc = FeatureGatedError(result)
        error_str = str(exc)
        assert "business" in error_str.lower()
        assert "free" in error_str.lower()

    def test_to_dict_structure(self) -> None:
        result = check_feature(Tier.FREE, Feature.SELF_HOSTED)
        exc = FeatureGatedError(result)
        d = exc.to_dict()
        assert d["error"] == "feature_gated"
        assert d["feature"] == "self_hosted"
        assert d["required_tier"] == "enterprise"
        assert d["current_tier"] == "free"
        assert "runowl.ai" in d["upgrade_url"]
        assert d["message"]  # non-empty

    def test_error_for_business_tier_feature(self) -> None:
        result = check_feature(Tier.TEAM, Feature.PRIORITY_SUPPORT)
        exc = FeatureGatedError(result)
        assert exc.result.required_tier == Tier.BUSINESS
        assert "#business" in exc.upgrade_url

    def test_error_for_enterprise_tier_feature(self) -> None:
        result = check_feature(Tier.BUSINESS, Feature.AUDIT_LOG)
        exc = FeatureGatedError(result)
        assert exc.result.required_tier == Tier.ENTERPRISE
        assert "#enterprise" in exc.upgrade_url


# ---------------------------------------------------------------------------
# 4. License detection: no key -> FREE, key present -> TEAM, explicit override
# ---------------------------------------------------------------------------


class TestLicenseDetection:
    def test_no_key_returns_free(self) -> None:
        settings = _free_settings()
        assert detect_tier(settings) == Tier.FREE

    def test_api_key_present_no_override_returns_team(self) -> None:
        settings = _team_settings()
        assert detect_tier(settings) == Tier.TEAM

    def test_explicit_tier_override_business(self) -> None:
        settings = _business_settings()
        assert detect_tier(settings) == Tier.BUSINESS

    def test_explicit_tier_override_enterprise(self) -> None:
        settings = _enterprise_settings()
        assert detect_tier(settings) == Tier.ENTERPRISE

    def test_explicit_team_override(self) -> None:
        m = MagicMock()
        m.runowl_api_key = None
        m.runowl_tier = Tier.TEAM
        assert detect_tier(m) == Tier.TEAM


# ---------------------------------------------------------------------------
# 5. API key validation flow
# ---------------------------------------------------------------------------


class TestAPIKeyValidation:
    def test_no_key_returns_free(self) -> None:
        assert validate_api_key(None) == Tier.FREE

    def test_empty_string_returns_free(self) -> None:
        assert validate_api_key("") == Tier.FREE

    def test_any_key_returns_team(self) -> None:
        assert validate_api_key("rwl_abc123") == Tier.TEAM

    def test_different_key_formats_all_return_team(self) -> None:
        keys = ["rwl_key1", "some-random-key", "x", "a" * 100]
        for key in keys:
            assert validate_api_key(key) == Tier.TEAM

    def test_is_paid_free(self) -> None:
        assert is_paid(Tier.FREE) is False

    def test_is_paid_team(self) -> None:
        assert is_paid(Tier.TEAM) is True

    def test_is_paid_business(self) -> None:
        assert is_paid(Tier.BUSINESS) is True

    def test_is_paid_enterprise(self) -> None:
        assert is_paid(Tier.ENTERPRISE) is True


# ---------------------------------------------------------------------------
# 6. FastAPI /license/tier endpoint with and without API key header
# ---------------------------------------------------------------------------


class TestLicenseTierEndpoint:
    @pytest.mark.asyncio
    async def test_tier_without_key_returns_free(self) -> None:
        with patch("freemium.router.get_settings", return_value=_free_settings()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/license/tier")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "free"
        assert data["is_paid"] is False
        # Free features present
        assert "surface_security" in data["features"]
        assert "code_review" in data["features"]
        assert "qa_session" in data["features"]
        assert "webhook" in data["features"]
        # Team features absent
        assert "deep_security" not in data["features"]
        assert "solid_analysis" not in data["features"]

    @pytest.mark.asyncio
    async def test_tier_with_api_key_header_returns_team(self) -> None:
        with patch("freemium.router.get_settings", return_value=_free_settings()):
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
        assert data["is_paid"] is True
        # Team features present
        assert "deep_security" in data["features"]
        assert "solid_analysis" in data["features"]
        assert "pr_comment_auto" in data["features"]
        assert "check_runs" in data["features"]
        # Business features absent
        assert "priority_support" not in data["features"]
        assert "sso" not in data["features"]

    @pytest.mark.asyncio
    async def test_tier_from_settings_api_key(self) -> None:
        """When settings have an API key but no header is sent, tier comes from settings."""
        with patch("freemium.router.get_settings", return_value=_team_settings()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/license/tier")

        assert resp.status_code == 200
        assert resp.json()["tier"] == "team"

    @pytest.mark.asyncio
    async def test_tier_business_from_settings_override(self) -> None:
        with patch("freemium.router.get_settings", return_value=_business_settings()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/license/tier")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "business"
        assert data["is_paid"] is True
        assert "priority_support" in data["features"]
        assert "sso" in data["features"]
        # Enterprise absent
        assert "self_hosted" not in data["features"]

    @pytest.mark.asyncio
    async def test_tier_enterprise_from_settings_override(self) -> None:
        with patch("freemium.router.get_settings", return_value=_enterprise_settings()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/license/tier")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "enterprise"
        assert "self_hosted" in data["features"]
        assert "audit_log" in data["features"]


# ---------------------------------------------------------------------------
# 7. FastAPI /license/validate endpoint
# ---------------------------------------------------------------------------


class TestLicenseValidateEndpoint:
    @pytest.mark.asyncio
    async def test_valid_key_returns_team(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/license/validate", json={"api_key": "rwl_test_key"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["tier"] == "team"
        assert "valid" in data["message"].lower() or "team" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_empty_key_returns_400(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/license/validate", json={"api_key": ""})

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_body_returns_422(self) -> None:
        """Sending no JSON body should trigger a validation error (422)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/license/validate",
                content=b"{}",
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 8. FastAPI /license/features endpoint returns correct tier mapping
# ---------------------------------------------------------------------------


class TestLicenseFeaturesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_all_features_with_correct_tiers(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/license/features")

        assert resp.status_code == 200
        data = resp.json()

        # Verify every defined feature is present
        for feature in Feature:
            assert str(feature) in data, f"Feature {feature} missing from response"

        # Verify tier mapping matches source of truth
        for feat, min_tier in _FEATURE_MIN_TIER.items():
            assert data[str(feat)] == str(min_tier), (
                f"Feature {feat} should map to {min_tier}, got {data[str(feat)]}"
            )

    @pytest.mark.asyncio
    async def test_free_features_mapped_correctly(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/license/features")

        data = resp.json()
        assert data["surface_security"] == "free"
        assert data["code_review"] == "free"
        assert data["qa_session"] == "free"
        assert data["webhook"] == "free"

    @pytest.mark.asyncio
    async def test_team_features_mapped_correctly(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/license/features")

        data = resp.json()
        assert data["deep_security"] == "team"
        assert data["solid_analysis"] == "team"
        assert data["pr_comment_auto"] == "team"
        assert data["check_runs"] == "team"

    @pytest.mark.asyncio
    async def test_business_and_enterprise_features_mapped_correctly(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/license/features")

        data = resp.json()
        assert data["priority_support"] == "business"
        assert data["sso"] == "business"
        assert data["self_hosted"] == "enterprise"
        assert data["audit_log"] == "enterprise"


# ---------------------------------------------------------------------------
# 9. Upgrade prompt formatting for CLI and markdown
# ---------------------------------------------------------------------------


class TestUpgradePromptFormatting:
    def test_cli_prompt_for_team_feature(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        prompt = format_upgrade_prompt_cli(result)
        assert "runowl.ai" in prompt
        assert "not available" in prompt.lower() or "plan" in prompt.lower()
        assert result.upgrade_url in prompt

    def test_cli_prompt_for_business_feature(self) -> None:
        result = check_feature(Tier.FREE, Feature.SSO)
        prompt = format_upgrade_prompt_cli(result)
        assert "runowl.ai/pricing#business" in prompt

    def test_cli_prompt_for_enterprise_feature(self) -> None:
        result = check_feature(Tier.FREE, Feature.SELF_HOSTED)
        prompt = format_upgrade_prompt_cli(result)
        assert "runowl.ai/pricing#enterprise" in prompt

    def test_markdown_prompt_for_team_feature(self) -> None:
        result = check_feature(Tier.FREE, Feature.SOLID_ANALYSIS)
        prompt = format_upgrade_prompt_markdown(result)
        assert "runowl.ai" in prompt
        assert "Upgrade" in prompt
        assert "[Upgrade" in prompt  # markdown link
        assert result.upgrade_url in prompt

    def test_markdown_prompt_for_enterprise_feature(self) -> None:
        result = check_feature(Tier.FREE, Feature.AUDIT_LOG)
        prompt = format_upgrade_prompt_markdown(result)
        assert "Enterprise" in prompt or "enterprise" in prompt
        assert "runowl.ai/pricing#enterprise" in prompt

    def test_gated_error_cli_formatting(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        exc = FeatureGatedError(result)
        prompt = format_gated_error_cli(exc)
        assert "runowl.ai" in prompt
        assert result.upgrade_url in prompt

    def test_gated_error_markdown_formatting(self) -> None:
        result = check_feature(Tier.FREE, Feature.PR_COMMENT_AUTO)
        exc = FeatureGatedError(result)
        prompt = format_gated_error_markdown(exc)
        assert "Upgrade" in prompt
        assert "runowl.ai" in prompt

    def test_allowed_feature_has_empty_upgrade_fields(self) -> None:
        """When a feature IS allowed, upgrade_message and upgrade_url should be empty."""
        result = check_feature(Tier.ENTERPRISE, Feature.SELF_HOSTED)
        assert result.allowed is True
        assert result.upgrade_message == ""
        assert result.upgrade_url == ""

    def test_cli_and_markdown_differ(self) -> None:
        """CLI and markdown formatters should produce different output."""
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        cli = format_upgrade_prompt_cli(result)
        md = format_upgrade_prompt_markdown(result)
        assert cli != md
        # CLI uses Rich markup
        assert "[bold" in cli or "[dim" in cli
        # Markdown uses --- separators
        assert "---" in md
