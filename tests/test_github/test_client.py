"""Tests for GitHub API client using pytest-httpx."""

import base64

import pytest
from pytest_httpx import HTTPXMock

from github.client import GitHubClient
from github.models import PRRef

REF = PRRef(owner="acme", repo="widget", number=7)


@pytest.fixture
def client() -> GitHubClient:
    return GitHubClient(token="test-token")


@pytest.fixture
def pr_payload() -> dict:
    return {
        "number": 7,
        "title": "Fix bug",
        "body": "Fixes #5",
        "user": {"login": "alice"},
        "base": {"ref": "main", "sha": "abc123"},
        "head": {"ref": "fix/bug", "sha": "def456"},
        "state": "open",
        "additions": 10,
        "deletions": 2,
        "changed_files": 1,
    }


@pytest.fixture
def commits_payload() -> list:
    return [
        {
            "sha": "def456",
            "commit": {"message": "Fix bug", "author": {"name": "Alice"}},
        }
    ]


@pytest.fixture
def files_payload() -> list:
    return [
        {
            "filename": "src/app.py",
            "status": "modified",
            "additions": 10,
            "deletions": 2,
            "changes": 12,
            "patch": "@@ -1,2 +1,3 @@\n context\n-old\n+new",
        }
    ]


class TestGetPrMetadata:
    async def test_returns_metadata(
        self,
        httpx_mock: HTTPXMock,
        client: GitHubClient,
        pr_payload: dict,
        commits_payload: list,
        files_payload: list,
    ) -> None:
        httpx_mock.add_response(json=pr_payload)
        httpx_mock.add_response(json=commits_payload)
        httpx_mock.add_response(json=files_payload)

        meta = await client.get_pr_metadata(REF)
        assert meta.number == 7
        assert meta.title == "Fix bug"
        assert meta.author == "alice"
        assert len(meta.commits) == 1
        assert len(meta.files) == 1
        assert meta.files[0].filename == "src/app.py"


class TestGetFile:
    async def test_fetches_and_caches_file(
        self, httpx_mock: HTTPXMock, client: GitHubClient
    ) -> None:
        content = base64.b64encode(b"print('hello')\n").decode()
        httpx_mock.add_response(
            json={
                "content": content + "\n",
                "sha": "aaabbb",
                "size": 16,
                "type": "file",
            }
        )

        result = await client.get_file(REF, "src/app.py", "def456")
        assert result.content == "print('hello')\n"
        assert result.sha == "aaabbb"

        # Second call — should hit cache, no extra HTTP request
        result2 = await client.get_file(REF, "src/app.py", "def456")
        assert result2.content == result.content

    async def test_path_traversal_rejected(self, client: GitHubClient) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            await client.get_file(REF, "../../etc/passwd", "abc")


class TestListDir:
    async def test_returns_entries(self, httpx_mock: HTTPXMock, client: GitHubClient) -> None:
        httpx_mock.add_response(
            json=[
                {
                    "name": "main.py",
                    "path": "src/main.py",
                    "type": "file",
                    "size": 100,
                    "sha": "aaa",
                },
                {"name": "utils", "path": "src/utils", "type": "dir", "sha": "bbb"},
            ]
        )
        entries = await client.list_dir(REF, "src", "main")
        assert len(entries) == 2
        assert entries[0].name == "main.py"
        assert entries[1].type == "dir"


class TestSearchCode:
    async def test_returns_results(self, httpx_mock: HTTPXMock, client: GitHubClient) -> None:
        httpx_mock.add_response(
            json={
                "items": [
                    {
                        "path": "src/auth.py",
                        "repository": {"full_name": "acme/widget"},
                        "score": 0.9,
                        "text_matches": [],
                    }
                ]
            }
        )
        results = await client.search_code(REF, "def login")
        assert len(results) == 1
        assert results[0].path == "src/auth.py"


class TestPostPrComment:
    async def test_posts_comment(self, httpx_mock: HTTPXMock, client: GitHubClient) -> None:
        httpx_mock.add_response(json={"id": 1, "body": "Review complete"})
        resp = await client.post_pr_comment(REF, "Review complete")
        assert resp["id"] == 1
