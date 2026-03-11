"""Data models for GitHub webhook payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PullRequestUser:
    login: str
    id: int


@dataclass
class PullRequestHead:
    sha: str
    ref: str
    label: str


@dataclass
class PullRequestBase:
    ref: str
    label: str


@dataclass
class PullRequest:
    number: int
    title: str
    body: str | None
    state: str
    user: PullRequestUser
    head: PullRequestHead
    base: PullRequestBase
    html_url: str
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PullRequest:
        return cls(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            user=PullRequestUser(
                login=data["user"]["login"],
                id=data["user"]["id"],
            ),
            head=PullRequestHead(
                sha=data["head"]["sha"],
                ref=data["head"]["ref"],
                label=data["head"]["label"],
            ),
            base=PullRequestBase(
                ref=data["base"]["ref"],
                label=data["base"]["label"],
            ),
            html_url=data["html_url"],
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
        )


@dataclass
class Repository:
    id: int
    name: str
    full_name: str
    private: bool
    owner_login: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Repository:
        return cls(
            id=data["id"],
            name=data["name"],
            full_name=data["full_name"],
            private=data["private"],
            owner_login=data["owner"]["login"],
        )


@dataclass
class PullRequestEvent:
    """Parsed GitHub pull_request webhook event."""

    action: str  # opened | synchronize | reopened | closed | edited
    pull_request: PullRequest
    repository: Repository
    installation_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PullRequestEvent:
        return cls(
            action=data["action"],
            pull_request=PullRequest.from_dict(data["pull_request"]),
            repository=Repository.from_dict(data["repository"]),
            installation_id=data.get("installation", {}).get("id"),
        )

    @property
    def should_review(self) -> bool:
        """True when this event should trigger an automatic review."""
        return self.action in ("opened", "synchronize", "reopened")

    @property
    def pr_url(self) -> str:
        return self.pull_request.html_url

    @property
    def owner(self) -> str:
        return self.repository.owner_login

    @property
    def repo(self) -> str:
        return self.repository.name

    @property
    def pr_number(self) -> int:
        return self.pull_request.number

    @property
    def head_sha(self) -> str:
        return self.pull_request.head.sha


# Generic alias used in the router
WebhookPayload = dict[str, Any]
