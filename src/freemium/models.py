"""Freemium gate models — feature flags, tier capabilities, upgrade prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from config import Tier

__all__ = ["Tier", "Feature", "GateResult", "TierCapabilities"]


class Feature(StrEnum):
    # Free features
    SURFACE_SECURITY = "surface_security"
    CODE_REVIEW = "code_review"
    QA_SESSION = "qa_session"
    WEBHOOK = "webhook"

    # Paid features (Team tier+)
    DEEP_SECURITY = "deep_security"
    SOLID_ANALYSIS = "solid_analysis"
    PR_COMMENT_AUTO = "pr_comment_auto"
    CHECK_RUNS = "check_runs"

    # Business tier+
    PRIORITY_SUPPORT = "priority_support"
    SSO = "sso"

    # Enterprise tier
    SELF_HOSTED = "self_hosted"
    AUDIT_LOG = "audit_log"


# Map each feature to the minimum tier required to use it
_FEATURE_MIN_TIER: dict[Feature, Tier] = {
    Feature.SURFACE_SECURITY: Tier.FREE,
    Feature.CODE_REVIEW: Tier.FREE,
    Feature.QA_SESSION: Tier.FREE,
    Feature.WEBHOOK: Tier.FREE,
    Feature.DEEP_SECURITY: Tier.TEAM,
    Feature.SOLID_ANALYSIS: Tier.TEAM,
    Feature.PR_COMMENT_AUTO: Tier.TEAM,
    Feature.CHECK_RUNS: Tier.TEAM,
    Feature.PRIORITY_SUPPORT: Tier.BUSINESS,
    Feature.SSO: Tier.BUSINESS,
    Feature.SELF_HOSTED: Tier.ENTERPRISE,
    Feature.AUDIT_LOG: Tier.ENTERPRISE,
}

_TIER_RANK: dict[Tier, int] = {
    Tier.FREE: 0,
    Tier.TEAM: 1,
    Tier.BUSINESS: 2,
    Tier.ENTERPRISE: 3,
}

_UPGRADE_URLS: dict[Tier, str] = {
    Tier.TEAM: "https://runowl.ai/pricing#team",
    Tier.BUSINESS: "https://runowl.ai/pricing#business",
    Tier.ENTERPRISE: "https://runowl.ai/pricing#enterprise",
}

_UPGRADE_MESSAGES: dict[Feature, str] = {
    Feature.DEEP_SECURITY: (
        "Deep OWASP security analysis (JWT, crypto, race conditions, supply chain) "
        "is available on the Team plan."
    ),
    Feature.SOLID_ANALYSIS: (
        "SOLID principle and architecture analysis is available on the Team plan."
    ),
    Feature.PR_COMMENT_AUTO: ("Automatic PR comment posting is available on the Team plan."),
    Feature.CHECK_RUNS: ("GitHub Check Runs integration is available on the Team plan."),
    Feature.PRIORITY_SUPPORT: ("Priority support is available on the Business plan."),
    Feature.SSO: ("SSO / SAML authentication is available on the Business plan."),
    Feature.SELF_HOSTED: ("Self-hosted deployment is available on the Enterprise plan."),
    Feature.AUDIT_LOG: ("Audit logging is available on the Enterprise plan."),
}


@dataclass
class GateResult:
    """Result of checking whether a feature is accessible."""

    allowed: bool
    feature: Feature
    tier: Tier
    required_tier: Tier
    upgrade_message: str = ""
    upgrade_url: str = ""

    @property
    def blocked(self) -> bool:
        return not self.allowed


@dataclass
class TierCapabilities:
    """All features available to a given tier."""

    tier: Tier
    features: set[Feature] = field(default_factory=set)

    @classmethod
    def for_tier(cls, tier: Tier) -> TierCapabilities:
        rank = _TIER_RANK[tier]
        available = {
            feat for feat, min_tier in _FEATURE_MIN_TIER.items() if _TIER_RANK[min_tier] <= rank
        }
        return cls(tier=tier, features=available)

    def has(self, feature: Feature) -> bool:
        return feature in self.features
