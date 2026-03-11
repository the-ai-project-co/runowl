"""GitHub API layer — client, parser, diff, and models."""

from github.client import GitHubClient
from github.diff import parse_patch
from github.models import (
    DiffHunk,
    DirEntry,
    FileContent,
    FileDiff,
    PRCommit,
    PRFile,
    PRMetadata,
    PRRef,
    SearchResult,
)
from github.parser import parse_pr_url, sanitize_path

__all__ = [
    "GitHubClient",
    "parse_pr_url",
    "parse_patch",
    "sanitize_path",
    "PRRef",
    "PRMetadata",
    "PRFile",
    "PRCommit",
    "FileDiff",
    "DiffHunk",
    "FileContent",
    "DirEntry",
    "SearchResult",
]
