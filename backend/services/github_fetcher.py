import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import requests

from backend.separator import _BINARY_EXTS, MAX_FILE_BYTES

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"


@dataclass
class TreeEntry:
    path: str
    mode: str
    sha: str
    size: int | None = None
    entry_type: str = "blob"


@dataclass
class RepoData:
    owner: str
    repo: str
    branch: str
    default_branch: str = "main"
    files: list[dict[str, Any]] = field(default_factory=list)


def _api_get(url: str, token: str | None = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def _raw_get(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _resolve_branch(
    owner: str, repo: str, branch: str | None, token: str | None = None
) -> str:
    if branch:
        return branch
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    repo_data = _api_get(url, token)
    return repo_data.get("default_branch", "main")


def fetch_repo_tree(
    owner: str,
    repo: str,
    branch: str,
    token: str | None = None,
) -> list[TreeEntry]:
    url = (
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{quote(branch)}?recursive=1"
    )
    data = _api_get(url, token)
    entries = []
    for item in data.get("tree", []):
        entries.append(
            TreeEntry(
                path=item["path"],
                mode=item.get("mode", ""),
                sha=item.get("sha", ""),
                size=item.get("size"),
                entry_type=item.get("type", "blob"),
            )
        )

    if data.get("truncated"):
        logger.warning(
            "Tree truncated by GitHub API - repos with >300k entries are incomplete"
        )

    return entries


def fetch_file_content(owner: str, repo: str, branch: str, path: str) -> str | None:
    url = f"{RAW_BASE}/{quote(owner)}/{quote(repo)}/{quote(branch)}/{quote(path)}"
    try:
        return _raw_get(url)
    except requests.exceptions.RequestException as e:
        logger.warning("Failed to fetch %s: %s", path, e)
        return None


def should_skip(entry: TreeEntry) -> bool:
    if entry.entry_type != "blob":
        return True
    ext = entry.path.lower().rsplit(".", 1)[-1] if "." in entry.path else ""
    if f".{ext}" in _BINARY_EXTS:
        return True
    if entry.size is not None and entry.size > MAX_FILE_BYTES:
        return True
    if entry.size == 0:
        return True
    return False


def fetch_repo(
    owner: str, repo: str, branch: str | None = None, token: str | None = None
) -> RepoData:
    resolved_branch = _resolve_branch(owner, repo, branch, token)
    repo_info = _api_get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", token)

    tree = fetch_repo_tree(owner, repo, resolved_branch, token)

    data = RepoData(
        owner=owner,
        repo=repo,
        branch=resolved_branch,
        default_branch=repo_info.get("default_branch", "main"),
    )

    for entry in tree:
        if should_skip(entry):
            continue

        content = fetch_file_content(owner, repo, resolved_branch, entry.path)
        if content is None:
            continue

        ext = entry.path.rsplit(".", 1)[-1] if "." in entry.path else ""
        data.files.append(
            {
                "path": entry.path,
                "relative_path": entry.path,
                "content": content,
                "file_type": f".{ext}" if ext else "",
                "size_bytes": entry.size,
            }
        )

    return data
