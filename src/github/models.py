"""Data models for GitHub API responses."""

from dataclasses import dataclass, field


@dataclass
class PRRef:
    owner: str
    repo: str
    number: int


@dataclass
class PRFile:
    filename: str
    status: str  # added | removed | modified | renamed | copied | changed | unchanged
    additions: int
    deletions: int
    changes: int
    patch: str | None = None  # unified diff hunk
    previous_filename: str | None = None


@dataclass
class PRCommit:
    sha: str
    message: str
    author: str


@dataclass
class PRMetadata:
    number: int
    title: str
    body: str | None
    author: str
    base_branch: str
    head_branch: str
    head_sha: str
    base_sha: str
    state: str
    commits: list[PRCommit]
    files: list[PRFile]
    additions: int
    deletions: int
    changed_files: int


@dataclass
class DiffHunk:
    header: str  # e.g. "@@ -10,7 +10,9 @@"
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str]  # raw diff lines including +/-/space prefix


@dataclass
class FileDiff:
    filename: str
    status: str
    additions: int
    deletions: int
    hunks: list[DiffHunk]
    previous_filename: str | None = None


@dataclass
class FileContent:
    path: str
    content: str
    sha: str
    size: int
    ref: str  # the git ref this was fetched at


@dataclass
class SearchResult:
    path: str
    repository: str
    score: float
    matches: list[dict[str, object]] = field(default_factory=list)


@dataclass
class DirEntry:
    name: str
    path: str
    type: str  # file | dir | symlink
    size: int | None = None
    sha: str | None = None
