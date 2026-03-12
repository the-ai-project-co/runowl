"""Tests for testing.docker_runner — Docker infrastructure."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.docker_runner import (
    ContainerPool,
    _CONTAINER_MEM_LIMIT,
    _CONTAINER_NANO_CPUS,
    _find_video,
    _wait_for_container_ready,
    _write_playwright_config,
    detect_preview_url,
    run_e2e_tests,
)
from testing.models import TestCase, TestStatus


def _make_case(test_id: str = "e2e12345") -> TestCase:
    return TestCase(id=test_id, name=f"test_{test_id}", code="await page.goto('/')")


# ---------------------------------------------------------------------------
# detect_preview_url — pure regex, no mocking needed
# ---------------------------------------------------------------------------


class TestDetectPreviewUrl:
    @pytest.mark.asyncio
    async def test_vercel_url_from_body(self) -> None:
        url = await detect_preview_url("Deploy: https://my-app-abc123.vercel.app")
        assert url == "https://my-app-abc123.vercel.app"

    @pytest.mark.asyncio
    async def test_netlify_url_from_body(self) -> None:
        url = await detect_preview_url("https://deploy-preview-99--my-site.netlify.app")
        assert url == "https://deploy-preview-99--my-site.netlify.app"

    @pytest.mark.asyncio
    async def test_generic_preview_url(self) -> None:
        url = await detect_preview_url("Preview URL: https://preview.example.com")
        assert url == "https://preview.example.com"

    @pytest.mark.asyncio
    async def test_url_from_comments(self) -> None:
        url = await detect_preview_url("", pr_comments=["Deploy preview: https://pr42.netlify.app"])
        assert url == "https://pr42.netlify.app"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self) -> None:
        url = await detect_preview_url("No URL here", pr_comments=["Also nothing"])
        assert url is None

    @pytest.mark.asyncio
    async def test_empty_body_and_no_comments(self) -> None:
        url = await detect_preview_url("")
        assert url is None


# ---------------------------------------------------------------------------
# _write_playwright_config
# ---------------------------------------------------------------------------


class TestWritePlaywrightConfig:
    def test_default_chromium_only_no_projects_block(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, "http://localhost:3000")
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "baseURL: 'http://localhost:3000'" in content
        # Default: no projects block needed
        assert "firefox" not in content

    def test_firefox_produces_projects_block(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None, browsers=("chromium", "firefox"))
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "projects:" in content
        assert "firefox" in content
        assert "chromium" in content

    def test_chromium_only_explicit_no_firefox(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None, browsers=("chromium",))
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "firefox" not in content

    def test_video_on_enabled(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None)
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "video: 'on'" in content

    def test_trace_on_first_retry(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None)
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "trace: 'on-first-retry'" in content

    def test_fallback_base_url_when_none(self, tmp_path: Path) -> None:
        _write_playwright_config(tmp_path, None)
        content = (tmp_path / "playwright.config.ts").read_text()
        assert "http://localhost:3000" in content


# ---------------------------------------------------------------------------
# _find_video
# ---------------------------------------------------------------------------


class TestFindVideo:
    def test_finds_webm_by_test_id(self, tmp_path: Path) -> None:
        (tmp_path / "e2e12345-video.webm").write_bytes(b"")
        result = _find_video(tmp_path, "e2e12345")
        assert result is not None
        assert "e2e12345" in result.name

    def test_falls_back_to_first_webm_when_id_not_in_name(self, tmp_path: Path) -> None:
        (tmp_path / "other-video.webm").write_bytes(b"")
        result = _find_video(tmp_path, "e2e12345")
        assert result is not None

    def test_returns_none_when_no_videos(self, tmp_path: Path) -> None:
        result = _find_video(tmp_path, "e2e12345")
        assert result is None

    def test_prefers_test_id_match_over_other(self, tmp_path: Path) -> None:
        (tmp_path / "other.webm").write_bytes(b"")
        (tmp_path / "e2e12345.webm").write_bytes(b"")
        result = _find_video(tmp_path, "e2e12345")
        assert result is not None
        assert "e2e12345" in result.name


# ---------------------------------------------------------------------------
# Resource limit constants
# ---------------------------------------------------------------------------


class TestResourceLimits:
    def test_mem_limit_is_non_empty_string(self) -> None:
        assert isinstance(_CONTAINER_MEM_LIMIT, str)
        assert len(_CONTAINER_MEM_LIMIT) > 0

    def test_nano_cpus_is_positive_int(self) -> None:
        assert isinstance(_CONTAINER_NANO_CPUS, int)
        assert _CONTAINER_NANO_CPUS > 0


# ---------------------------------------------------------------------------
# run_e2e_tests — empty list fast path
# ---------------------------------------------------------------------------


class TestRunE2eTestsEmptyList:
    @pytest.mark.asyncio
    async def test_empty_returns_empty(self) -> None:
        result = await run_e2e_tests([])
        assert result == []


# ---------------------------------------------------------------------------
# run_e2e_tests — docker SDK not installed
# ---------------------------------------------------------------------------


class TestRunE2eTestsNoDocker:
    @pytest.mark.asyncio
    async def test_returns_skip_when_docker_not_installed(self) -> None:
        import builtins
        import sys
        cases = [_make_case()]
        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "docker":
                raise ImportError("No module named 'docker'")
            return original_import(name, *args, **kwargs)

        # Remove docker from sys.modules if present so the import runs fresh
        docker_mod = sys.modules.pop("docker", None)
        try:
            with patch("builtins.__import__", side_effect=_mock_import):
                results = await run_e2e_tests(cases)
        finally:
            if docker_mod is not None:
                sys.modules["docker"] = docker_mod

        assert len(results) == 1
        assert results[0].status == TestStatus.SKIP
        assert "docker" in results[0].stderr.lower()


# ---------------------------------------------------------------------------
# ContainerPool — unit tests with mocked Docker client
# ---------------------------------------------------------------------------


class TestContainerPool:
    def _make_docker_client(self, num_containers: int = 2) -> MagicMock:
        client = MagicMock()
        containers = [MagicMock() for _ in range(num_containers)]
        for c in containers:
            c.status = "running"
            c.id = "abc123"
            c.exec_run.return_value = (0, b"passed")
            c.restart.return_value = None
            c.remove.return_value = None
        client.containers.run.side_effect = containers
        return client

    @pytest.mark.asyncio
    async def test_pool_start_creates_containers(self) -> None:
        client = self._make_docker_client(size := 2)
        pool = ContainerPool(size=size, host_dir="/tmp")
        await pool.start(client)
        assert client.containers.run.call_count == size
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_and_release_returns_handle(self) -> None:
        client = self._make_docker_client(1)
        pool = ContainerPool(size=1, host_dir="/tmp")
        await pool.start(client)

        handle = await pool.acquire()
        assert handle is not None

        with patch.object(
            pool._ready,
            "put",
            new_callable=AsyncMock,
        ) as mock_put:
            # Mock container.reload so it appears running
            handle.container.reload = MagicMock()
            handle.container.status = "running"
            await pool.release(handle)
            mock_put.assert_called_once_with(handle)

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_semaphore_blocks_beyond_pool_size(self) -> None:
        """Acquiring more than pool_size handles blocks."""
        pool = ContainerPool(size=1, host_dir="/tmp")
        # Manually put one item in the ready queue (bypass start())
        mock_handle = MagicMock()
        await pool._ready.put(mock_handle)

        # First acquire should succeed immediately
        handle = await pool.acquire()
        assert handle is mock_handle

        # Second acquire should block (semaphore is 0) — verify with timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(pool.acquire(), timeout=0.05)


# ---------------------------------------------------------------------------
# _wait_for_container_ready
# ---------------------------------------------------------------------------


class TestWaitForContainerReady:
    @pytest.mark.asyncio
    async def test_returns_true_when_container_running(self) -> None:
        container = MagicMock()
        container.reload = MagicMock()
        container.status = "running"
        result = await _wait_for_container_ready(container, timeout=5)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_container_stuck_starting(self) -> None:
        container = MagicMock()
        container.reload = MagicMock()
        container.status = "starting"  # never becomes "running"
        result = await _wait_for_container_ready(container, timeout=0.2)
        assert result is False
