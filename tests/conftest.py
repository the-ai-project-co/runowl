"""Shared pytest configuration and fixtures for all test types."""

import pytest


def pytest_collection_modifyitems(config, items):
    """Automatically tag tests based on their location in the test tree."""
    for item in items:
        path = str(item.fspath)
        if "/unit/" in path:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/evals/" in path:
            item.add_marker(pytest.mark.evals)
        elif "/e2e/" in path:
            item.add_marker(pytest.mark.e2e)
