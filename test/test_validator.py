# import pytest

from backend.validator import (
    # InvalidGitHubURLError,
    is_valid_github_url,
    validate_github_url,
)


def test_https_standard():
    r = validate_github_url("https://github.com/owner/repo")
    assert r.owner == "owner" and r.repo == "repo" and r.kind == "https"


def test_https_branch():
    r = validate_github_url("https://github.com/owner/repo/tree/main")
    assert r.branch == "main"


def test_https_with_git_suffix():
    r = validate_github_url("https://github.com/owner/repo.git")
    assert r.repo == "repo"


def test_ssh_standard():
    r = validate_github_url("ssh://git@github.com/owner/repo")
    assert r.owner == "owner" and r.kind == "ssh"


def test_api_url():
    r = validate_github_url("https://api.github.com/repos/owner/repo")
    assert r.kind == "api"


def test_empty_url():
    assert not is_valid_github_url("")


def test_invalid_url():
    assert not is_valid_github_url("https://gitlab.com/owner/repo")
