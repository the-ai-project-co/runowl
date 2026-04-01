"""Tests for the freemium gate — feature flags and tier checks."""

import pytest

from config import Tier
from freemium.gate import (
    FeatureGatedError,
    check_feature,
    get_capabilities,
    is_paid,
    require_feature,
)
from freemium.models import Feature

# ── check_feature ──────────────────────────────────────────────────────────────


class TestCheckFeature:
    def test_free_feature_allowed_on_free_tier(self) -> None:
        result = check_feature(Tier.FREE, Feature.SURFACE_SECURITY)
        assert result.allowed
        assert not result.blocked

    def test_free_feature_allowed_on_paid_tier(self) -> None:
        result = check_feature(Tier.TEAM, Feature.SURFACE_SECURITY)
        assert result.allowed

    def test_paid_feature_blocked_on_free_tier(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        assert result.blocked
        assert not result.allowed

    def test_paid_feature_allowed_on_team_tier(self) -> None:
        result = check_feature(Tier.TEAM, Feature.DEEP_SECURITY)
        assert result.allowed

    def test_solid_blocked_on_free(self) -> None:
        result = check_feature(Tier.FREE, Feature.SOLID_ANALYSIS)
        assert result.blocked

    def test_solid_allowed_on_team(self) -> None:
        result = check_feature(Tier.TEAM, Feature.SOLID_ANALYSIS)
        assert result.allowed

    def test_business_feature_blocked_on_team(self) -> None:
        result = check_feature(Tier.TEAM, Feature.SSO)
        assert result.blocked

    def test_business_feature_allowed_on_business(self) -> None:
        result = check_feature(Tier.BUSINESS, Feature.SSO)
        assert result.allowed

    def test_enterprise_feature_blocked_on_business(self) -> None:
        result = check_feature(Tier.BUSINESS, Feature.SELF_HOSTED)
        assert result.blocked

    def test_enterprise_feature_allowed_on_enterprise(self) -> None:
        result = check_feature(Tier.ENTERPRISE, Feature.SELF_HOSTED)
        assert result.allowed

    def test_blocked_result_includes_upgrade_url(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        assert result.upgrade_url
        assert "runowl.ai" in result.upgrade_url

    def test_blocked_result_includes_upgrade_message(self) -> None:
        result = check_feature(Tier.FREE, Feature.DEEP_SECURITY)
        assert result.upgrade_message
        assert len(result.upgrade_message) > 10

    def test_allowed_result_has_no_upgrade_message(self) -> None:
        result = check_feature(Tier.TEAM, Feature.DEEP_SECURITY)
        assert result.upgrade_message == ""

    def test_result_contains_correct_tiers(self) -> None:
        result = check_feature(Tier.FREE, Feature.SOLID_ANALYSIS)
        assert result.tier == Tier.FREE
        assert result.required_tier == Tier.TEAM


# ── require_feature ────────────────────────────────────────────────────────────


class TestRequireFeature:
    def test_free_feature_does_not_raise(self) -> None:
        require_feature(Tier.FREE, Feature.CODE_REVIEW)  # should not raise

    def test_paid_feature_raises_on_free(self) -> None:
        with pytest.raises(FeatureGatedError) as exc_info:
            require_feature(Tier.FREE, Feature.DEEP_SECURITY)
        err = exc_info.value
        assert err.result.feature == Feature.DEEP_SECURITY
        assert err.upgrade_url
        assert "team" in err.upgrade_message.lower()

    def test_error_to_dict(self) -> None:
        with pytest.raises(FeatureGatedError) as exc_info:
            require_feature(Tier.FREE, Feature.SOLID_ANALYSIS)
        d = exc_info.value.to_dict()
        assert d["error"] == "feature_gated"
        assert d["feature"] == "solid_analysis"
        assert d["required_tier"] == "team"
        assert d["current_tier"] == "free"
        assert "upgrade_url" in d


# ── get_capabilities ───────────────────────────────────────────────────────────


class TestGetCapabilities:
    def test_free_tier_has_surface_security(self) -> None:
        caps = get_capabilities(Tier.FREE)
        assert caps.has(Feature.SURFACE_SECURITY)

    def test_free_tier_lacks_deep_security(self) -> None:
        caps = get_capabilities(Tier.FREE)
        assert not caps.has(Feature.DEEP_SECURITY)

    def test_team_tier_has_deep_security(self) -> None:
        caps = get_capabilities(Tier.TEAM)
        assert caps.has(Feature.DEEP_SECURITY)

    def test_team_tier_has_solid_analysis(self) -> None:
        caps = get_capabilities(Tier.TEAM)
        assert caps.has(Feature.SOLID_ANALYSIS)

    def test_team_tier_has_all_free_features(self) -> None:
        free_caps = get_capabilities(Tier.FREE)
        team_caps = get_capabilities(Tier.TEAM)
        assert free_caps.features.issubset(team_caps.features)

    def test_business_has_all_team_features(self) -> None:
        team_caps = get_capabilities(Tier.TEAM)
        biz_caps = get_capabilities(Tier.BUSINESS)
        assert team_caps.features.issubset(biz_caps.features)

    def test_enterprise_has_all_features(self) -> None:
        biz_caps = get_capabilities(Tier.BUSINESS)
        ent_caps = get_capabilities(Tier.ENTERPRISE)
        assert biz_caps.features.issubset(ent_caps.features)
        assert ent_caps.has(Feature.SELF_HOSTED)
        assert ent_caps.has(Feature.AUDIT_LOG)


# ── is_paid ────────────────────────────────────────────────────────────────────


class TestIsPaid:
    def test_free_is_not_paid(self) -> None:
        assert not is_paid(Tier.FREE)

    def test_team_is_paid(self) -> None:
        assert is_paid(Tier.TEAM)

    def test_business_is_paid(self) -> None:
        assert is_paid(Tier.BUSINESS)

    def test_enterprise_is_paid(self) -> None:
        assert is_paid(Tier.ENTERPRISE)
