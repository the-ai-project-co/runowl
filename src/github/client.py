"""GitHub API client with auth, rate limiting, caching, and concurrency control."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, cast

import httpx
from cachetools import LRUCache
from tenacity import retry, stop_after_attempt, wait_exponential

from github.models import (
    DirEntry,
    FileContent,
    PRCommit,
    PRFile,
    PRMetadata,
    PRRef,
    SearchResult,
)
from github.parser import sanitize_path

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_MAX_CACHE_ENTRIES = 200
_MAX_CONCURRENT_REQUESTS = 5


class GitHubClient:
    """Async GitHub API client.

    - Authenticates via GITHUB_TOKEN when provided (required for private repos).
    - Handles rate limiting with exponential backoff via tenacity.
    - Caches file content (LRU, 200 entries) to reduce API calls.
    - Limits concurrent requests to 5 via asyncio.Semaphore.
    """

    def __init__(self, token: str | None = None) -> None:
        self._token = token
        self._cache: LRUCache[str, Any] = LRUCache(maxsize=_MAX_CACHE_ENTRIES)
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
        self._client = httpx.AsyncClient(
            base_url=_GITHUB_API,
            headers=self._build_headers(),
            timeout=30.0,
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    async def _get(self, path: str, **params: Any) -> Any:
        """Make a rate-limit-aware GET request."""
        async with self._semaphore:
            resp = await self._client.get(path, params=params or None)

            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                retry_after = int(resp.headers.get("Retry-After", "60"))
                logger.warning("GitHub rate limit hit — waiting %ds", retry_after)
                await asyncio.sleep(retry_after)
                raise httpx.HTTPStatusError("Rate limited", request=resp.request, response=resp)

            if resp.status_code == 404:
                raise FileNotFoundError(f"GitHub resource not found: {path}")

            resp.raise_for_status()
            return resp.json()

    # ── PR Metadata ───────────────────────────────────────────────────────────

    async def get_pr_metadata(self, ref: PRRef) -> PRMetadata:
        """Fetch full PR metadata including file list and commit list."""
        pr_data, commits_data, files_data = await asyncio.gather(
            self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"),
            self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/commits"),
            self._get(
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/files",
                per_page=100,
            ),
        )

        commits = [
            PRCommit(
                sha=c["sha"],
                message=c["commit"]["message"],
                author=c["commit"]["author"]["name"],
            )
            for c in commits_data
        ]

        files = [
            PRFile(
                filename=f["filename"],
                status=f["status"],
                additions=f["additions"],
                deletions=f["deletions"],
                changes=f["changes"],
                patch=f.get("patch"),
                previous_filename=f.get("previous_filename"),
            )
            for f in files_data
        ]

        return PRMetadata(
            number=pr_data["number"],
            title=pr_data["title"],
            body=pr_data.get("body"),
            author=pr_data["user"]["login"],
            base_branch=pr_data["base"]["ref"],
            head_branch=pr_data["head"]["ref"],
            head_sha=pr_data["head"]["sha"],
            base_sha=pr_data["base"]["sha"],
            state=pr_data["state"],
            commits=commits,
            files=files,
            additions=pr_data["additions"],
            deletions=pr_data["deletions"],
            changed_files=pr_data["changed_files"],
        )

    # ── File Content ──────────────────────────────────────────────────────────

    async def get_file(self, ref: PRRef, path: str, git_ref: str) -> FileContent:
        """Fetch a file's content at a specific git ref.

        Results are cached by (owner/repo/path@ref).
        """
        safe_path = sanitize_path(path)
        cache_key = f"{ref.owner}/{ref.repo}/{safe_path}@{git_ref}"

        if cache_key in self._cache:
            logger.debug("Cache hit: %s", cache_key)
            return cast(FileContent, self._cache[cache_key])

        data = await self._get(
            f"/repos/{ref.owner}/{ref.repo}/contents/{safe_path}",
            ref=git_ref,
        )

        if isinstance(data, list):
            raise IsADirectoryError(f"{safe_path!r} is a directory, not a file")

        content_raw = data.get("content", "")
        # GitHub returns base64-encoded content
        content = base64.b64decode(content_raw).decode("utf-8", errors="replace")

        result = FileContent(
            path=safe_path,
            content=content,
            sha=data["sha"],
            size=data["size"],
            ref=git_ref,
        )
        self._cache[cache_key] = result
        return result

    # ── Directory Listing ─────────────────────────────────────────────────────

    async def list_dir(self, ref: PRRef, path: str, git_ref: str) -> list[DirEntry]:
        """List the contents of a directory at a specific git ref."""
        safe_path = sanitize_path(path) if path else ""
        endpoint = f"/repos/{ref.owner}/{ref.repo}/contents/{safe_path}"
        data = await self._get(endpoint, ref=git_ref)

        if not isinstance(data, list):
            raise NotADirectoryError(f"{safe_path!r} is a file, not a directory")

        return [
            DirEntry(
                name=entry["name"],
                path=entry["path"],
                type=entry["type"],
                size=entry.get("size"),
                sha=entry.get("sha"),
            )
            for entry in data
        ]

    # ── Code Search ───────────────────────────────────────────────────────────

    async def search_code(
        self, ref: PRRef, query: str, max_results: int = 30
    ) -> list[SearchResult]:
        """Search code within a specific repository."""
        scoped_query = f"{query} repo:{ref.owner}/{ref.repo}"
        data = await self._get(
            "/search/code",
            q=scoped_query,
            per_page=min(max_results, 100),
        )

        return [
            SearchResult(
                path=item["path"],
                repository=item["repository"]["full_name"],
                score=item.get("score", 0.0),
                matches=item.get("text_matches", []),
            )
            for item in data.get("items", [])
        ]

    # ── PR Comment ────────────────────────────────────────────────────────────

    async def post_pr_comment(self, ref: PRRef, body: str) -> dict[str, Any]:
        """Post a comment on a PR."""
        async with self._semaphore:
            resp = await self._client.post(
                f"/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments",
                json={"body": body},
            )
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

    # ── Check Runs API ────────────────────────────────────────────────────────

    async def create_check_run(
        self,
        owner: str,
        repo: str,
        name: str,
        head_sha: str,
        status: str = "in_progress",
    ) -> dict[str, Any]:
        """Create a GitHub Check Run and return its id."""
        async with self._semaphore:
            resp = await self._client.post(
                f"/repos/{owner}/{repo}/check-runs",
                json={"name": name, "head_sha": head_sha, "status": status},
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

    async def update_check_run(
        self,
        owner: str,
        repo: str,
        check_run_id: int,
        conclusion: str,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a Check Run with conclusion and output summary."""
        async with self._semaphore:
            resp = await self._client.patch(
                f"/repos/{owner}/{repo}/check-runs/{check_run_id}",
                json={"status": "completed", "conclusion": conclusion, "output": output},
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())
