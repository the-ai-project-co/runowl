"""Freemium gate — checks whether a feature is accessible for a given tier."""

from __future__ import annotations

from config import Tier
from freemium.models import (
    _FEATURE_MIN_TIER,
    _TIER_RANK,
    _UPGRADE_MESSAGES,
    _UPGRADE_URLS,
    Feature,
    GateResult,
    TierCapabilities,
)


def check_feature(tier: Tier, feature: Feature) -> GateResult:
    """Return a GateResult indicating whether `feature` is accessible at `tier`."""
    required_tier = _FEATURE_MIN_TIER[feature]
    allowed = _TIER_RANK[tier] >= _TIER_RANK[required_tier]

    if allowed:
        return GateResult(
            allowed=True,
            feature=feature,
            tier=tier,
            required_tier=required_tier,
        )

    upgrade_message = _UPGRADE_MESSAGES.get(
        feature, f"This feature requires the {required_tier} plan."
    )
    upgrade_url = _UPGRADE_URLS.get(required_tier, "https://runowl.ai/pricing")

    return GateResult(
        allowed=False,
        feature=feature,
        tier=tier,
        required_tier=required_tier,
        upgrade_message=upgrade_message,
        upgrade_url=upgrade_url,
    )


def require_feature(tier: Tier, feature: Feature) -> None:
    """Raise FeatureGatedError if `feature` is not accessible at `tier`."""
    result = check_feature(tier, feature)
    if result.blocked:
        raise FeatureGatedError(result)


def get_capabilities(tier: Tier) -> TierCapabilities:
    """Return all features accessible at the given tier."""
    return TierCapabilities.for_tier(tier)


def is_paid(tier: Tier) -> bool:
    """Return True if the tier is paid (Team or above)."""
    return _TIER_RANK[tier] >= _TIER_RANK[Tier.TEAM]


class FeatureGatedError(Exception):
    """Raised when a feature is not accessible at the current tier."""

    def __init__(self, result: GateResult) -> None:
        self.result = result
        super().__init__(
            f"Feature '{result.feature}' requires {result.required_tier} tier "
            f"(current: {result.tier}). {result.upgrade_message}"
        )

    @property
    def upgrade_url(self) -> str:
        return self.result.upgrade_url

    @property
    def upgrade_message(self) -> str:
        return self.result.upgrade_message

    def to_dict(self) -> dict[str, str]:
        return {
            "error": "feature_gated",
            "feature": str(self.result.feature),
            "required_tier": str(self.result.required_tier),
            "current_tier": str(self.result.tier),
            "message": self.upgrade_message,
            "upgrade_url": self.upgrade_url,
        }
