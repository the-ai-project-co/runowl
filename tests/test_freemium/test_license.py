"""Tests for tier detection and API key validation."""

from unittest.mock import MagicMock

from config import Tier
from freemium.license import detect_tier, validate_api_key


class TestDetectTier:
    def test_no_api_key_returns_free(self) -> None:
        settings = MagicMock()
        settings.runowl_api_key = None
        settings.runowl_tier = Tier.FREE
        assert detect_tier(settings) == Tier.FREE

    def test_api_key_present_returns_team(self) -> None:
        settings = MagicMock()
        settings.runowl_api_key = "rwl_some_key"
        settings.runowl_tier = Tier.FREE
        assert detect_tier(settings) == Tier.TEAM

    def test_explicit_tier_override_wins(self) -> None:
        settings = MagicMock()
        settings.runowl_api_key = None
        settings.runowl_tier = Tier.BUSINESS
        assert detect_tier(settings) == Tier.BUSINESS

    def test_explicit_tier_with_api_key(self) -> None:
        # Explicit tier always wins, even with API key
        settings = MagicMock()
        settings.runowl_api_key = "rwl_key"
        settings.runowl_tier = Tier.ENTERPRISE
        assert detect_tier(settings) == Tier.ENTERPRISE


class TestValidateApiKey:
    def test_none_key_returns_free(self) -> None:
        assert validate_api_key(None) == Tier.FREE

    def test_empty_string_returns_free(self) -> None:
        assert validate_api_key("") == Tier.FREE

    def test_any_key_returns_team(self) -> None:
        assert validate_api_key("rwl_abc123") == Tier.TEAM

    def test_different_keys_all_return_team(self) -> None:
        for key in ("key1", "rwl_xyz", "some-license-key"):
            assert validate_api_key(key) == Tier.TEAM
