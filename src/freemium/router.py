"""FastAPI router for license validation and tier info endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from config import Tier, get_settings
from freemium.gate import get_capabilities
from freemium.license import detect_tier, validate_api_key

router = APIRouter(prefix="/license", tags=["license"])


class TierResponse(BaseModel):
    tier: str
    features: list[str]
    is_paid: bool


class ValidateRequest(BaseModel):
    api_key: str


class ValidateResponse(BaseModel):
    valid: bool
    tier: str
    message: str


@router.get(
    "/tier",
    response_model=TierResponse,
    summary="Get current subscription tier and features",
)
async def get_tier(
    x_runowl_api_key: str = Header(default=""),
) -> TierResponse:
    """Return the tier and feature set for the provided (or configured) API key."""
    settings = get_settings()

    # Header takes precedence over env var
    tier = validate_api_key(x_runowl_api_key) if x_runowl_api_key else detect_tier(settings)
    caps = get_capabilities(tier)

    return TierResponse(
        tier=str(tier),
        features=sorted(str(f) for f in caps.features),
        is_paid=tier != Tier.FREE,
    )


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Validate a RunOwl API key",
)
async def validate_license(body: ValidateRequest) -> ValidateResponse:
    """Validate an API key and return the associated tier."""
    if not body.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_key must not be empty",
        )

    tier = validate_api_key(body.api_key)

    return ValidateResponse(
        valid=True,
        tier=str(tier),
        message=f"API key is valid. Tier: {tier}",
    )


@router.get(
    "/features",
    summary="List all features and their minimum required tier",
)
async def list_features() -> dict[str, str]:
    """Return a map of feature → minimum tier required."""
    from freemium.models import _FEATURE_MIN_TIER

    return {str(feat): str(min_tier) for feat, min_tier in _FEATURE_MIN_TIER.items()}
