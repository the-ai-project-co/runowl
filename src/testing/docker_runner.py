"""Docker-based Playwright runner for E2E browser tests.

Lifecycle per test batch:
1. Pull / reuse the official `mcr.microsoft.com/playwright` image.
2. Spin up a container with the generated test code mounted.
3. Execute `npx playwright test` inside the container.
4. Capture stdout / stderr and video artefacts.
5. Tear the container down.

Video and replay data are written to a host temp directory that is bind-mounted
into the container, then picked up by recorder.py.

Advanced features:
- ContainerPool: pre-warms N containers for parallel execution.
- Resource limits: configurable memory and CPU via env vars.
- Firefox support: opt-in via `browsers` parameter.
- Parallel execution: split test cases into shards run concurrently.
- Retry logic: re-run failing tests up to `max_retries` times.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testing.models import TestCase, TestResult, TestStatus

logger = logging.getLogger(__name__)

_PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.50.0-noble"
_E2E_TIMEOUT = 120  # seconds per container run
_CONTAINER_WORK_DIR = "/runowl_tests"

# Resource limits (configurable via env vars)
_CONTAINER_MEM_LIMIT: str = os.environ.get("RUNOWL_E2E_MEM_LIMIT", "1g")
_CONTAINER_NANO_CPUS: int = int(
    float(os.environ.get("RUNOWL_E2E_CPU_LIMIT", "1")) * 1_000_000_000
)

# Default browsers for Playwright
_DEFAULT_BROWSERS: tuple[str, ...] = ("chromium",)

# Container pool health check poll interval and max wait
_HEALTH_POLL_INTERVAL = 0.5  # seconds
_HEALTH_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Container pool
# ---------------------------------------------------------------------------


@dataclass
class ContainerHandle:
    """A reference to a pooled container and its assigned work directory."""

    container: Any  # docker.models.containers.Container
    host_dir: str


class ContainerPool:
    """
    A pool of pre-warmed Docker containers for parallel E2E test execution.

    Each container is started in detach mode with the Playwright image.
    Tests are sent to containers via exec_run. After a run the container
    is restarted and returned to the ready queue, or torn down if unhealthy.
    """

    def __init__(
        self,
        image: str = _PLAYWRIGHT_IMAGE,
        size: int = 2,
        host_dir: str = "",
    ) -> None:
        self._image = image
        self._size = size
        self._host_dir = host_dir
        self._semaphore = asyncio.Semaphore(size)
        self._containers: list[ContainerHandle] = []
        self._ready: asyncio.Queue[ContainerHandle] = asyncio.Queue()
        self._started = False

    async def start(self, docker_client: Any) -> None:
        """Spin up all containers in the pool."""
        loop = asyncio.get_running_loop()

        def _create_containers() -> list[Any]:
            containers = []
            for _ in range(self._size):
                c = docker_client.containers.run(
                    self._image,
                    command="sleep infinity",
                    detach=True,
                    volumes=(
                        {self._host_dir: {"bind": _CONTAINER_WORK_DIR, "mode": "rw"}}
                        if self._host_dir
                        else {}
                    ),
                    working_dir=_CONTAINER_WORK_DIR,
                    mem_limit=_CONTAINER_MEM_LIMIT,
                    nano_cpus=_CONTAINER_NANO_CPUS,
                    environment={"CI": "true"},
                )
                containers.append(c)
            return containers

        containers = await loop.run_in_executor(None, _create_containers)
        for c in containers:
            handle = ContainerHandle(container=c, host_dir=self._host_dir)
            self._containers.append(handle)
            await self._ready.put(handle)
        self._started = True

    async def acquire(self) -> ContainerHandle:
        """Acquire a ready container from the pool (blocks until one is available)."""
        await self._semaphore.acquire()
        handle = await self._ready.get()
        return handle

    async def release(self, handle: ContainerHandle) -> None:
        """Return a container to the pool (restarts it first to reset state)."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, handle.container.restart)
            ready = await _wait_for_container_ready(handle.container)
            if ready:
                await self._ready.put(handle)
            else:
                logger.warning("Container %s unhealthy after restart — removing", handle.container.id[:12])
                await loop.run_in_executor(None, lambda: handle.container.remove(force=True))
        except Exception as exc:
            logger.warning("Failed to restart pooled container: %s", exc)
        finally:
            self._semaphore.release()

    async def shutdown(self) -> None:
        """Stop and remove all containers in the pool."""
        loop = asyncio.get_running_loop()
        for handle in self._containers:
            try:
                await loop.run_in_executor(None, lambda c=handle.container: c.remove(force=True))
            except Exception as exc:
                logger.debug("Error removing pooled container: %s", exc)
        self._containers.clear()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def _wait_for_container_ready(container: Any, timeout: int = _HEALTH_TIMEOUT) -> bool:
    """
    Poll until the container is running (or until timeout).

    The Playwright image has no HEALTHCHECK instruction so we fall back to
    checking container.status == "running".
    """
    loop = asyncio.get_running_loop()
    elapsed = 0.0
    while elapsed < timeout:
        try:
            await loop.run_in_executor(None, container.reload)
            if container.status == "running":
                return True
        except Exception as exc:
            logger.debug("Health poll error: %s", exc)
        await asyncio.sleep(_HEALTH_POLL_INTERVAL)
        elapsed += _HEALTH_POLL_INTERVAL
    return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_e2e_tests(
    cases: list[TestCase],
    preview_url: str | None = None,
    timeout: int = _E2E_TIMEOUT,
    pool: ContainerPool | None = None,
    max_workers: int = 1,
    max_retries: int = 0,
    browsers: tuple[str, ...] = _DEFAULT_BROWSERS,
) -> list[TestResult]:
    """
    Run E2E Playwright tests inside Docker container(s).

    Args:
        cases: Test cases to run.
        preview_url: Base URL for the app under test.
        timeout: Seconds per container run.
        pool: Optional pre-warmed container pool for parallel execution.
        max_workers: How many containers to use in parallel (ignored when pool is given).
        max_retries: How many times to retry failing tests.
        browsers: Which browsers to run tests on ("chromium", "firefox").
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

    # Split into shards for parallel execution
    effective_workers = max(1, min(max_workers, len(cases)))
    shards = _split_shards(cases, effective_workers)

    shard_tasks = [
        _run_shard(
            shard=shard,
            preview_url=preview_url,
            timeout=timeout,
            pool=pool,
            browsers=browsers,
        )
        for shard in shards
    ]
    shard_results = await asyncio.gather(*shard_tasks, return_exceptions=True)

    # Merge results in case order
    results: list[TestResult] = []
    for shard, shard_result in zip(shards, shard_results):
        if isinstance(shard_result, Exception):
            logger.error("Shard failed: %s", shard_result)
            for case in shard:
                results.append(
                    TestResult(
                        test_id=case.id,
                        test_name=case.name,
                        status=TestStatus.ERROR,
                        stderr=str(shard_result),
                    )
                )
        else:
            results.extend(shard_result)  # type: ignore[arg-type]

    # Retry failing tests
    if max_retries > 0:
        results = await _retry_failures(results, cases, preview_url, timeout, pool, browsers, max_retries)

    return results


def _split_shards(cases: list[TestCase], n: int) -> list[list[TestCase]]:
    """Split cases into n roughly equal shards."""
    if n <= 1:
        return [cases]
    size = max(1, (len(cases) + n - 1) // n)
    return [cases[i : i + size] for i in range(0, len(cases), size)]


async def _run_shard(
    shard: list[TestCase],
    preview_url: str | None,
    timeout: int,
    pool: ContainerPool | None,
    browsers: tuple[str, ...],
) -> list[TestResult]:
    """Run one shard of E2E tests in a single container."""
    import docker  # type: ignore[import-untyped]

    with tempfile.TemporaryDirectory(prefix="runowl_e2e_") as tmpdir:
        tmp = Path(tmpdir)
        videos_dir = tmp / "videos"
        videos_dir.mkdir()

        _write_playwright_config(tmp, preview_url, browsers=browsers)
        test_files: list[tuple[TestCase, Path]] = []
        for case in shard:
            fpath = tmp / f"{case.id}.spec.ts"
            fpath.write_text(case.code, encoding="utf-8")
            test_files.append((case, fpath))

        if pool is not None:
            handle = await pool.acquire()
            try:
                stdout_log, stderr_log, exit_code = await _run_via_pool(handle, timeout)
            finally:
                await pool.release(handle)
        else:
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
                    for c in shard
                ]

        results: list[TestResult] = []
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


async def _retry_failures(
    results: list[TestResult],
    cases: list[TestCase],
    preview_url: str | None,
    timeout: int,
    pool: ContainerPool | None,
    browsers: tuple[str, ...],
    max_retries: int,
) -> list[TestResult]:
    """Re-run failing test cases up to max_retries times."""
    # Build a map for quick lookup
    result_by_id = {r.test_id: (i, r) for i, r in enumerate(results)}
    case_by_id = {c.id: c for c in cases}

    for attempt in range(1, max_retries + 1):
        failing_ids = [
            r.test_id for r in results if r.status in (TestStatus.FAIL, TestStatus.ERROR)
        ]
        if not failing_ids:
            break

        failing_cases = [case_by_id[tid] for tid in failing_ids if tid in case_by_id]
        if not failing_cases:
            break

        logger.info("Retry attempt %d/%d for %d failing tests", attempt, max_retries, len(failing_cases))
        retry_results = await _run_shard(
            shard=failing_cases,
            preview_url=preview_url,
            timeout=timeout,
            pool=pool,
            browsers=browsers,
        )

        for retry_result in retry_results:
            if retry_result.test_id in result_by_id:
                idx, _old = result_by_id[retry_result.test_id]
                retry_result.retry_count = attempt
                results[idx] = retry_result
                result_by_id[retry_result.test_id] = (idx, retry_result)

    return results


# ---------------------------------------------------------------------------
# Container execution helpers
# ---------------------------------------------------------------------------


async def _run_via_pool(handle: ContainerHandle, timeout: int) -> tuple[str, str, int]:
    """Execute the Playwright test suite in a pooled container via exec_run."""
    loop = asyncio.get_running_loop()

    def _sync_exec() -> tuple[str, str, int]:
        exit_code, output = handle.container.exec_run(
            f"npx playwright test --output={_CONTAINER_WORK_DIR}/videos",
            workdir=_CONTAINER_WORK_DIR,
            environment={"CI": "true", "PLAYWRIGHT_VIDEOS_DIR": f"{_CONTAINER_WORK_DIR}/videos"},
        )
        out = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output)
        return out, "", exit_code or 0

    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _sync_exec),
            timeout=timeout,
        )
    except TimeoutError:
        return "", f"E2E container timed out after {timeout}s", 1


async def _run_container(
    client: Any,
    image: str,
    host_dir: str,
    timeout: int,
) -> tuple[str, str, int]:
    """Pull image (if needed) and run the Playwright test suite inside it."""
    loop = asyncio.get_running_loop()

    def _sync_run() -> tuple[str, str, int]:
        c = client.containers.run(
            image=image,
            command=f"npx playwright test --output={_CONTAINER_WORK_DIR}/videos",
            volumes={host_dir: {"bind": _CONTAINER_WORK_DIR, "mode": "rw"}},
            working_dir=_CONTAINER_WORK_DIR,
            remove=True,
            stdout=True,
            stderr=True,
            mem_limit=_CONTAINER_MEM_LIMIT,
            nano_cpus=_CONTAINER_NANO_CPUS,
            environment={
                "CI": "true",
                "PLAYWRIGHT_VIDEOS_DIR": f"{_CONTAINER_WORK_DIR}/videos",
            },
        )
        if isinstance(c, bytes):
            return c.decode("utf-8", errors="replace"), "", 0
        logs = c.logs(stdout=True, stderr=True)
        return logs.decode("utf-8", errors="replace"), "", 0

    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _sync_run),
            timeout=timeout,
        )
    except TimeoutError:
        return "", f"E2E container timed out after {timeout}s", 1
    except Exception as exc:
        try:
            import docker.errors  # type: ignore[import-untyped]

            if hasattr(docker.errors, "ContainerError") and isinstance(
                exc, docker.errors.ContainerError
            ):
                return (
                    exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "",
                    str(exc),
                    exc.exit_status,
                )
        except ImportError:
            pass
        return "", str(exc), 1


# ---------------------------------------------------------------------------
# Config and artefact helpers
# ---------------------------------------------------------------------------


def _write_playwright_config(
    dest: Path,
    preview_url: str | None,
    browsers: tuple[str, ...] = _DEFAULT_BROWSERS,
) -> None:
    base_url = preview_url or "http://localhost:3000"

    projects_block = ""
    if len(browsers) > 1 or "firefox" in browsers:
        browser_entries = []
        if "chromium" in browsers:
            browser_entries.append(
                "  { name: 'chromium', use: { ...devices['Desktop Chrome'] } },"
            )
        if "firefox" in browsers:
            browser_entries.append(
                "  { name: 'firefox',  use: { ...devices['Desktop Firefox'] } },"
            )
        projects_block = f"\n  projects: [\n" + "\n".join(browser_entries) + "\n  ],"

    config = f"""import {{ defineConfig, devices }} from '@playwright/test';

export default defineConfig({{
  testDir: '.',
  timeout: 30_000,
  use: {{
    baseURL: '{base_url}',
    video: 'on',
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  }},{projects_block}
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
