"""E2E tests for the GitHub API client pipeline.

Uses pytest-httpx to mock HTTP calls so no real GitHub API access is needed.
All responses use realistic payloads matching the GitHub REST API v3 format.
"""

import base64

import pytest
from pytest_httpx import HTTPXMock

from github.client import GitHubClient
from github.models import PRRef


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pr_ref() -> PRRef:
    return PRRef(owner="octocat", repo="hello-world", number=42)


@pytest.fixture
async def client():
    c = GitHubClient(token="ghp_test_token_abc123")
    yield c
    await c.close()


@pytest.fixture
async def client_no_token():
    c = GitHubClient(token=None)
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# Realistic GitHub API response payloads
# ---------------------------------------------------------------------------

PR_RESPONSE = {
    "number": 42,
    "title": "Add authentication module",
    "body": "This PR adds JWT-based authentication.\n\n## Changes\n- New auth middleware\n- Token validation\n- Tests",
    "state": "open",
    "user": {"login": "octocat", "id": 1},
    "base": {
        "ref": "main",
        "sha": "abc123base",
        "repo": {"full_name": "octocat/hello-world"},
    },
    "head": {
        "ref": "feature/auth",
        "sha": "def456head",
        "repo": {"full_name": "octocat/hello-world"},
    },
    "additions": 150,
    "deletions": 20,
    "changed_files": 5,
    "merged": False,
    "mergeable": True,
}

COMMITS_RESPONSE = [
    {
        "sha": "aaa111",
        "commit": {
            "message": "feat: add auth middleware",
            "author": {"name": "Octocat", "email": "octocat@github.com"},
        },
    },
    {
        "sha": "bbb222",
        "commit": {
            "message": "feat: add token validation",
            "author": {"name": "Octocat", "email": "octocat@github.com"},
        },
    },
    {
        "sha": "ccc333",
        "commit": {
            "message": "test: add auth tests",
            "author": {"name": "Mona Lisa", "email": "mona@github.com"},
        },
    },
]

FILES_RESPONSE = [
    {
        "sha": "file_sha_1",
        "filename": "src/auth/middleware.py",
        "status": "added",
        "additions": 80,
        "deletions": 0,
        "changes": 80,
        "patch": "@@ -0,0 +1,80 @@\n+import jwt\n+\n+class AuthMiddleware:\n+    pass",
    },
    {
        "sha": "file_sha_2",
        "filename": "src/auth/token.py",
        "status": "added",
        "additions": 45,
        "deletions": 0,
        "changes": 45,
        "patch": "@@ -0,0 +1,45 @@\n+def validate_token(token):\n+    return True",
    },
    {
        "sha": "file_sha_3",
        "filename": "src/main.py",
        "status": "modified",
        "additions": 5,
        "deletions": 2,
        "changes": 7,
        "patch": "@@ -10,7 +10,10 @@\n import os\n+from auth.middleware import AuthMiddleware\n \n def create_app():\n-    app = App()\n+    app = App()\n+    app.add_middleware(AuthMiddleware)\n+    return app",
    },
    {
        "sha": "file_sha_4",
        "filename": "tests/test_auth.py",
        "status": "added",
        "additions": 20,
        "deletions": 0,
        "changes": 20,
        "patch": "@@ -0,0 +1,20 @@\n+import pytest\n+\n+def test_auth():\n+    assert True",
    },
    {
        "sha": "file_sha_5",
        "filename": "src/config.py",
        "status": "modified",
        "additions": 0,
        "deletions": 18,
        "changes": 18,
        "previous_filename": None,
    },
]


def _file_content_response(content: str, path: str = "src/auth/middleware.py") -> dict:
    """Build a realistic GitHub contents API response with base64-encoded content."""
    encoded = base64.b64encode(content.encode()).decode()
    return {
        "name": path.split("/")[-1],
        "path": path,
        "sha": "abc123sha",
        "size": len(content),
        "type": "file",
        "content": encoded,
        "encoding": "base64",
    }


DIRECTORY_RESPONSE = [
    {
        "name": "middleware.py",
        "path": "src/auth/middleware.py",
        "type": "file",
        "size": 2048,
        "sha": "sha_middleware",
    },
    {
        "name": "token.py",
        "path": "src/auth/token.py",
        "type": "file",
        "size": 1024,
        "sha": "sha_token",
    },
    {
        "name": "utils",
        "path": "src/auth/utils",
        "type": "dir",
        "size": None,
        "sha": "sha_utils_tree",
    },
]

SEARCH_RESPONSE = {
    "total_count": 2,
    "incomplete_results": False,
    "items": [
        {
            "name": "middleware.py",
            "path": "src/auth/middleware.py",
            "repository": {"full_name": "octocat/hello-world"},
            "score": 1.0,
            "text_matches": [
                {
                    "fragment": "class AuthMiddleware:",
                    "matches": [{"text": "AuthMiddleware", "indices": [6, 20]}],
                }
            ],
        },
        {
            "name": "token.py",
            "path": "src/auth/token.py",
            "repository": {"full_name": "octocat/hello-world"},
            "score": 0.8,
            "text_matches": [],
        },
    ],
}

COMMENT_RESPONSE = {
    "id": 9876,
    "body": "Review complete. Found 2 issues.",
    "user": {"login": "runowl[bot]"},
    "created_at": "2025-06-01T12:00:00Z",
}


# ---------------------------------------------------------------------------
# 1. Full PR metadata fetch
# ---------------------------------------------------------------------------


class TestFetchPRMetadata:
    async def test_full_metadata(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42",
            json=PR_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/commits",
            json=COMMITS_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/files?per_page=100",
            json=FILES_RESPONSE,
        )

        meta = await client.get_pr_metadata(pr_ref)

        assert meta.number == 42
        assert meta.title == "Add authentication module"
        assert meta.body is not None and "JWT" in meta.body
        assert meta.author == "octocat"
        assert meta.base_branch == "main"
        assert meta.head_branch == "feature/auth"
        assert meta.head_sha == "def456head"
        assert meta.base_sha == "abc123base"
        assert meta.state == "open"
        assert meta.additions == 150
        assert meta.deletions == 20
        assert meta.changed_files == 5

    async def test_commits_parsed_correctly(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42",
            json=PR_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/commits",
            json=COMMITS_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/files?per_page=100",
            json=FILES_RESPONSE,
        )

        meta = await client.get_pr_metadata(pr_ref)

        assert len(meta.commits) == 3
        assert meta.commits[0].sha == "aaa111"
        assert meta.commits[0].message == "feat: add auth middleware"
        assert meta.commits[0].author == "Octocat"
        assert meta.commits[2].author == "Mona Lisa"

    async def test_files_parsed_correctly(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42",
            json=PR_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/commits",
            json=COMMITS_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/files?per_page=100",
            json=FILES_RESPONSE,
        )

        meta = await client.get_pr_metadata(pr_ref)

        assert len(meta.files) == 5
        filenames = [f.filename for f in meta.files]
        assert "src/auth/middleware.py" in filenames
        assert "src/main.py" in filenames
        assert "tests/test_auth.py" in filenames

        added = [f for f in meta.files if f.status == "added"]
        assert len(added) == 3

        modified = [f for f in meta.files if f.status == "modified"]
        assert len(modified) == 2


# ---------------------------------------------------------------------------
# 2. File fetch with base64 decoding + LRU caching
# ---------------------------------------------------------------------------


class TestFileFetch:
    async def test_base64_decoding(self, httpx_mock: HTTPXMock, client, pr_ref):
        source = "import jwt\n\ndef validate(token):\n    return jwt.decode(token)\n"
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/contents/src/auth/middleware.py?ref=def456head",
            json=_file_content_response(source),
        )

        result = await client.get_file(pr_ref, "src/auth/middleware.py", "def456head")

        assert result.content == source
        assert result.path == "src/auth/middleware.py"
        assert result.sha == "abc123sha"
        assert result.ref == "def456head"
        assert result.size == len(source)

    async def test_lru_cache_prevents_extra_http(self, httpx_mock: HTTPXMock, client, pr_ref):
        source = "cached content"
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/contents/src/main.py?ref=abc123",
            json=_file_content_response(source, "src/main.py"),
        )

        # First call — hits HTTP
        result1 = await client.get_file(pr_ref, "src/main.py", "abc123")
        assert result1.content == source

        # Second call — should use cache, no extra HTTP call
        result2 = await client.get_file(pr_ref, "src/main.py", "abc123")
        assert result2.content == source

        # Only one HTTP request should have been made
        requests = httpx_mock.get_requests()
        matching = [
            r for r in requests
            if "contents/src/main.py" in str(r.url)
        ]
        assert len(matching) == 1

    async def test_different_refs_not_cached_together(self, httpx_mock: HTTPXMock, client, pr_ref):
        source_v1 = "version 1"
        source_v2 = "version 2"
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/contents/src/config.py?ref=ref1",
            json=_file_content_response(source_v1, "src/config.py"),
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/contents/src/config.py?ref=ref2",
            json=_file_content_response(source_v2, "src/config.py"),
        )

        r1 = await client.get_file(pr_ref, "src/config.py", "ref1")
        r2 = await client.get_file(pr_ref, "src/config.py", "ref2")

        assert r1.content == source_v1
        assert r2.content == source_v2


# ---------------------------------------------------------------------------
# 3. Directory listing
# ---------------------------------------------------------------------------


class TestDirectoryListing:
    async def test_lists_files_and_dirs(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/contents/src/auth?ref=main",
            json=DIRECTORY_RESPONSE,
        )

        entries = await client.list_dir(pr_ref, "src/auth", "main")

        assert len(entries) == 3
        names = [e.name for e in entries]
        assert "middleware.py" in names
        assert "token.py" in names
        assert "utils" in names

    async def test_file_entries_have_size(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/contents/src/auth?ref=main",
            json=DIRECTORY_RESPONSE,
        )

        entries = await client.list_dir(pr_ref, "src/auth", "main")

        file_entries = [e for e in entries if e.type == "file"]
        assert all(e.size is not None and e.size > 0 for e in file_entries)

    async def test_dir_entries_have_type(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/contents/src/auth?ref=main",
            json=DIRECTORY_RESPONSE,
        )

        entries = await client.list_dir(pr_ref, "src/auth", "main")

        dir_entries = [e for e in entries if e.type == "dir"]
        assert len(dir_entries) == 1
        assert dir_entries[0].name == "utils"


# ---------------------------------------------------------------------------
# 4. Code search
# ---------------------------------------------------------------------------


class TestCodeSearch:
    async def test_search_returns_results(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/search/code?q=AuthMiddleware+repo%3Aoctocat%2Fhello-world&per_page=30",
            json=SEARCH_RESPONSE,
        )

        results = await client.search_code(pr_ref, "AuthMiddleware")

        assert len(results) == 2
        assert results[0].path == "src/auth/middleware.py"
        assert results[0].repository == "octocat/hello-world"
        assert results[0].score == 1.0
        assert len(results[0].matches) == 1

    async def test_search_second_result(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/search/code?q=AuthMiddleware+repo%3Aoctocat%2Fhello-world&per_page=30",
            json=SEARCH_RESPONSE,
        )

        results = await client.search_code(pr_ref, "AuthMiddleware")

        assert results[1].path == "src/auth/token.py"
        assert results[1].score == 0.8
        assert results[1].matches == []


# ---------------------------------------------------------------------------
# 5. Post PR comment
# ---------------------------------------------------------------------------


class TestPostComment:
    async def test_post_comment(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/issues/42/comments",
            json=COMMENT_RESPONSE,
            status_code=201,
        )

        result = await client.post_pr_comment(pr_ref, "Review complete. Found 2 issues.")

        assert result["id"] == 9876
        assert result["body"] == "Review complete. Found 2 issues."

        # Verify the request body
        request = httpx_mock.get_requests()[-1]
        import json
        body = json.loads(request.content)
        assert body["body"] == "Review complete. Found 2 issues."


# ---------------------------------------------------------------------------
# 6. Path traversal rejection
# ---------------------------------------------------------------------------


class TestPathTraversalRejection:
    async def test_traversal_in_get_file(self, client, pr_ref):
        with pytest.raises(ValueError, match="Path traversal"):
            await client.get_file(pr_ref, "../../etc/passwd", "main")

    async def test_traversal_in_list_dir(self, client, pr_ref):
        with pytest.raises(ValueError, match="Path traversal"):
            await client.list_dir(pr_ref, "../../../etc", "main")

    async def test_deep_traversal(self, client, pr_ref):
        with pytest.raises(ValueError, match="Path traversal"):
            await client.get_file(pr_ref, "src/../../etc/passwd", "main")

    async def test_encoded_traversal_characters(self, client, pr_ref):
        with pytest.raises(ValueError, match="Unsafe characters"):
            await client.get_file(pr_ref, "src/%2e%2e/etc/passwd", "main")


# ---------------------------------------------------------------------------
# 7. Large PR with many files
# ---------------------------------------------------------------------------


class TestLargePR:
    async def test_large_file_list(self, httpx_mock: HTTPXMock, client, pr_ref):
        # Generate a PR with 50 files
        large_files_response = [
            {
                "sha": f"sha_{i}",
                "filename": f"src/module_{i}/handler.py",
                "status": "modified" if i % 3 else "added",
                "additions": 10 + i,
                "deletions": i % 5,
                "changes": 10 + i + (i % 5),
                "patch": f"@@ -{i},{i} +{i},{i+2} @@\n+# change {i}",
            }
            for i in range(50)
        ]

        large_pr = {
            **PR_RESPONSE,
            "additions": 500,
            "deletions": 100,
            "changed_files": 50,
        }

        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42",
            json=large_pr,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/commits",
            json=COMMITS_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/files?per_page=100",
            json=large_files_response,
        )

        meta = await client.get_pr_metadata(pr_ref)

        assert len(meta.files) == 50
        assert meta.changed_files == 50
        assert meta.additions == 500
        assert meta.deletions == 100

        # Verify all files are populated
        assert all(f.filename for f in meta.files)
        assert all(f.patch for f in meta.files)


# ---------------------------------------------------------------------------
# 8. Auth header present when token configured
# ---------------------------------------------------------------------------


class TestAuthHeader:
    async def test_token_included_in_request(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42",
            json=PR_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/commits",
            json=COMMITS_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/files?per_page=100",
            json=FILES_RESPONSE,
        )

        await client.get_pr_metadata(pr_ref)

        requests = httpx_mock.get_requests()
        for req in requests:
            auth = req.headers.get("authorization")
            assert auth == "Bearer ghp_test_token_abc123"

    async def test_no_auth_header_without_token(
        self, httpx_mock: HTTPXMock, client_no_token, pr_ref
    ):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42",
            json=PR_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/commits",
            json=COMMITS_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/files?per_page=100",
            json=FILES_RESPONSE,
        )

        await client_no_token.get_pr_metadata(pr_ref)

        requests = httpx_mock.get_requests()
        for req in requests:
            auth = req.headers.get("authorization")
            assert auth is None

    async def test_accept_header_present(self, httpx_mock: HTTPXMock, client, pr_ref):
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42",
            json=PR_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/commits",
            json=COMMITS_RESPONSE,
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/octocat/hello-world/pulls/42/files?per_page=100",
            json=FILES_RESPONSE,
        )

        await client.get_pr_metadata(pr_ref)

        requests = httpx_mock.get_requests()
        for req in requests:
            accept = req.headers.get("accept")
            assert accept == "application/vnd.github+json"
