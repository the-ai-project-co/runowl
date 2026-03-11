"""Freemium gate — feature flags, tier detection, upgrade prompts."""

from freemium.gate import (
    FeatureGatedError,
    check_feature,
    get_capabilities,
    is_paid,
    require_feature,
)
from freemium.license import detect_tier, validate_api_key
from freemium.models import Feature, GateResult, Tier, TierCapabilities

__all__ = [
    "check_feature",
    "require_feature",
    "get_capabilities",
    "is_paid",
    "detect_tier",
    "validate_api_key",
    "Feature",
    "GateResult",
    "TierCapabilities",
    "FeatureGatedError",
    "Tier",
]
