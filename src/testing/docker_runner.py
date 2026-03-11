"""Docker-based Playwright runner for E2E browser tests.

Lifecycle per test batch:
1. Pull / reuse the official `mcr.microsoft.com/playwright` image.
2. Spin up a container with the generated test code mounted.
3. Execute `npx playwright test` inside the container.
4. Capture stdout / stderr and video artefacts.
5. Tear the container down.

Video and replay data are written to a host temp directory that is bind-mounted
into the container, then picked up by recorder.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from testing.models import TestCase, TestResult, TestStatus

logger = logging.getLogger(__name__)

_PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.50.0-noble"
_E2E_TIMEOUT = 120  # seconds per container run
_CONTAINER_WORK_DIR = "/runowl_tests"


async def run_e2e_tests(
    cases: list[TestCase],
    preview_url: str | None = None,
    timeout: int = _E2E_TIMEOUT,
) -> list[TestResult]:
    """
    Run E2E Playwright tests inside a Docker container.
    Returns one TestResult per TestCase.
    """
    if not cases:
        return []

    try:
        import docker  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("docker SDK not installed — skipping E2E tests")
        return [
            TestResult(
                test_id=c.id,
                test_name=c.name,
                status=TestStatus.SKIP,
                stderr="docker SDK not installed (pip install docker)",
            )
            for c in cases
        ]

    results: list[TestResult] = []

    with tempfile.TemporaryDirectory(prefix="runowl_e2e_") as tmpdir:
        tmp = Path(tmpdir)
        videos_dir = tmp / "videos"
        videos_dir.mkdir()

        # Write all test files + playwright config
        _write_playwright_config(tmp, preview_url)
        test_files: list[tuple[TestCase, Path]] = []
        for case in cases:
            fpath = tmp / f"{case.id}.spec.ts"
            fpath.write_text(case.code, encoding="utf-8")
            test_files.append((case, fpath))

        # Run inside Docker
        try:
            client = docker.from_env()
            stdout_log, stderr_log, exit_code = await _run_container(
                client=client,
                image=_PLAYWRIGHT_IMAGE,
                host_dir=str(tmp),
                timeout=timeout,
            )
        except Exception as exc:
            logger.error("Docker E2E run failed: %s", exc)
            return [
                TestResult(
                    test_id=c.id,
                    test_name=c.name,
                    status=TestStatus.ERROR,
                    stderr=str(exc),
                )
                for c in cases
            ]

        # Map results — Playwright exits 0 on all pass, 1 on any fail
        for case, fpath in test_files:
            video_path = _find_video(videos_dir, case.id)
            if exit_code == 0:
                status = TestStatus.PASS
            else:
                status = TestStatus.FAIL if fpath.stem in stdout_log else TestStatus.SKIP

            results.append(
                TestResult(
                    test_id=case.id,
                    test_name=case.name,
                    status=status,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    video_path=str(video_path) if video_path else None,
                )
            )

    return results


async def _run_container(
    client: object,
    image: str,
    host_dir: str,
    timeout: int,
) -> tuple[str, str, int]:
    """Pull image (if needed) and run the Playwright test suite inside it."""
    import docker  # type: ignore[import-untyped]

    loop = asyncio.get_event_loop()

    def _sync_run() -> tuple[str, str, int]:
        c = client.containers.run(  # type: ignore[union-attr]
            image=image,
            command=f"npx playwright test --output={_CONTAINER_WORK_DIR}/videos",
            volumes={host_dir: {"bind": _CONTAINER_WORK_DIR, "mode": "rw"}},
            working_dir=_CONTAINER_WORK_DIR,
            remove=True,
            stdout=True,
            stderr=True,
            environment={
                "CI": "true",
                "PLAYWRIGHT_VIDEOS_DIR": f"{_CONTAINER_WORK_DIR}/videos",
            },
        )
        # containers.run with remove=True returns bytes when detach=False
        if isinstance(c, bytes):
            return c.decode("utf-8", errors="replace"), "", 0
        # If we get a Container object (should not happen with remove=True + no detach)
        logs = c.logs(stdout=True, stderr=True)  # type: ignore[union-attr]
        return logs.decode("utf-8", errors="replace"), "", 0

    try:
        stdout, stderr, exit_code = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_run),
            timeout=timeout,
        )
    except TimeoutError:
        return "", f"E2E container timed out after {timeout}s", 1
    except Exception as exc:  # docker.errors.ContainerError
        import docker.errors  # type: ignore[import-untyped]

        if hasattr(docker.errors, "ContainerError") and isinstance(
            exc, docker.errors.ContainerError
        ):
            return (
                exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "",
                str(exc),
                exc.exit_status,
            )
        return "", str(exc), 1

    return stdout, stderr, exit_code


def _write_playwright_config(dest: Path, preview_url: str | None) -> None:
    base_url = preview_url or "http://localhost:3000"
    config = f"""import {{ defineConfig }} from '@playwright/test';

export default defineConfig({{
  testDir: '.',
  timeout: 30_000,
  use: {{
    baseURL: '{base_url}',
    video: 'on',
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  }},
}});
"""
    (dest / "playwright.config.ts").write_text(config, encoding="utf-8")


def _find_video(videos_dir: Path, test_id: str) -> Path | None:
    """Return the video file for a given test id, if it was recorded."""
    for ext in ("webm", "mp4"):
        for f in videos_dir.rglob(f"*{test_id}*.{ext}"):
            return f
        for f in videos_dir.rglob(f"*.{ext}"):
            return f  # fallback: first video found
    return None


async def detect_preview_url(pr_body: str, pr_comments: list[str] | None = None) -> str | None:
    """
    Try to extract a preview deployment URL from the PR body or comments.
    Supports Vercel, Netlify, and generic https:// preview patterns.
    """
    import re

    sources = [pr_body or ""] + (pr_comments or [])
    patterns = [
        r"https://[a-zA-Z0-9\-]+\.vercel\.app",
        r"https://[a-zA-Z0-9\-]+\.netlify\.app",
        r"https://preview\.[a-zA-Z0-9\-\.]+",
        r"Preview URL[:\s]+(\S+)",
        r"Deploy preview[:\s]+(\S+)",
    ]
    for source in sources:
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                url = match.group(1) if match.lastindex else match.group(0)
                if url.startswith("http"):
                    return url
    return None
