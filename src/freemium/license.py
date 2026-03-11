"""License validation — maps RunOwl API keys to subscription tiers.

In production this would call the RunOwl licensing backend.
For now, it uses a simple environment-variable-based approach:
  - No RUNOWL_API_KEY → free tier
  - RUNOWL_API_KEY set + RUNOWL_TIER set → that tier
  - RUNOWL_API_KEY set, no RUNOWL_TIER → team tier (default paid)
"""

from __future__ import annotations

import logging

from config import Settings, Tier

logger = logging.getLogger(__name__)


def detect_tier(settings: Settings) -> Tier:
    """Determine the active subscription tier from settings.

    Priority:
    1. RUNOWL_TIER env var (explicit override)
    2. RUNOWL_API_KEY present → team (minimum paid tier)
    3. Default → free
    """
    # Explicit tier override always wins
    if settings.runowl_tier != Tier.FREE:
        return settings.runowl_tier

    # API key present without explicit tier → team
    if settings.runowl_api_key:
        logger.debug("RUNOWL_API_KEY set, defaulting to team tier")
        return Tier.TEAM

    return Tier.FREE


def validate_api_key(api_key: str | None) -> Tier:
    """Validate a RunOwl API key and return the associated tier.

    Stub implementation — in production this would call the licensing API.
    Currently treats any non-empty key as a valid team-tier key.
    """
    if not api_key:
        return Tier.FREE

    # In production: POST /licensing/validate with the key
    # and parse the returned tier. For now: any key = team.
    logger.debug("API key present — granting team tier")
    return Tier.TEAM
