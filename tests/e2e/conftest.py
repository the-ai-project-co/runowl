"""E2E test configuration and shared fixtures."""

import pytest


@pytest.fixture
def gemini_api_key():
    """Provide the Gemini API key for e2e tests that call real APIs."""
    import os

    key = os.environ.get("GEMINI_API_KEY")
    if not key or key == "test-key-for-ci":
        pytest.skip("GEMINI_API_KEY not set or is CI placeholder — skipping e2e test")
    return key


@pytest.fixture
def github_token():
    """Provide the GitHub token for e2e tests that call real APIs."""
    import os

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        pytest.skip("GITHUB_TOKEN not set — skipping e2e test")
    return token
