"""Detect the test framework used in a repository."""

from __future__ import annotations

import logging

from github.client import GitHubClient
from github.models import PRRef
from testing.models import FrameworkType

logger = logging.getLogger(__name__)

# Files whose presence indicates a framework
_FRAMEWORK_SIGNALS: list[tuple[str, FrameworkType]] = [
    ("playwright.config.ts", FrameworkType.PLAYWRIGHT),
    ("playwright.config.js", FrameworkType.PLAYWRIGHT),
    ("vitest.config.ts", FrameworkType.VITEST),
    ("vitest.config.js", FrameworkType.VITEST),
    ("jest.config.ts", FrameworkType.JEST),
    ("jest.config.js", FrameworkType.JEST),
    ("jest.config.cjs", FrameworkType.JEST),
    ("pytest.ini", FrameworkType.PYTEST),
    ("pyproject.toml", FrameworkType.PYTEST),  # confirmed below by content check
    ("setup.cfg", FrameworkType.PYTEST),
]

# Content substrings that confirm a framework inside a config file
_CONTENT_SIGNALS: dict[FrameworkType, list[str]] = {
    FrameworkType.PYTEST: ["[tool.pytest", "[pytest]", "pytest"],
    FrameworkType.JEST: ['"jest"', "'jest'", "jest.config"],
    FrameworkType.VITEST: ["vitest"],
    FrameworkType.PLAYWRIGHT: ["playwright"],
}


async def detect_framework(client: GitHubClient, ref: PRRef, head_sha: str) -> FrameworkType:
    """
    Inspect the repository root and common config files to determine the
    primary test framework in use.

    Priority: Playwright > Vitest > Jest > Pytest > Unknown
    """
    try:
        entries = await client.list_dir(ref, "", head_sha)
        filenames = {e.name.lower() for e in entries}
    except Exception:
        logger.debug("Could not list repo root for framework detection")
        return FrameworkType.UNKNOWN

    for config_file, framework in _FRAMEWORK_SIGNALS:
        if config_file.lower() in filenames:
            # For pyproject.toml, confirm pytest is actually configured
            if config_file == "pyproject.toml":
                try:
                    content = await client.get_file(ref, "pyproject.toml", head_sha)
                    if any(s in content.content for s in _CONTENT_SIGNALS[FrameworkType.PYTEST]):
                        return FrameworkType.PYTEST
                except Exception:
                    pass
                continue
            return framework

    # Fall back: check package.json for jest/vitest/playwright
    if "package.json" in filenames:
        try:
            pkg = await client.get_file(ref, "package.json", head_sha)
            for framework, signals in _CONTENT_SIGNALS.items():
                if any(s in pkg.content for s in signals):
                    return framework
        except Exception:
            pass

    return FrameworkType.UNKNOWN


async def find_test_paths(client: GitHubClient, ref: PRRef, head_sha: str) -> list[str]:
    """
    Return a list of existing test directory / file paths found in the repo
    (up to 10) so the generator knows what already exists.
    """
    candidates = ["tests", "test", "__tests__", "spec", "e2e"]
    found: list[str] = []

    try:
        entries = await client.list_dir(ref, "", head_sha)
        root_names = {e.name for e in entries}
        for candidate in candidates:
            if candidate in root_names:
                found.append(candidate)
    except Exception:
        pass

    return found[:10]
