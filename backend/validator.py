import re
from dataclasses import dataclass
from typing import Literal

UrlKind =Literal["https","ssh","api"]

@dataclass
class ParsedGitHubURL:
    raw:str
    kind:UrlKind
    owner:str
    repo:str
    branch:str|None

    @property
    def clone_url(self)->str:
        return f"https://github.com/{self.owner}/{self.repo}.git"
    def __str__(self) -> str:
        branch_info=f",branch={self.branch}"if self.branch else ""
        return (
             f"ParsedGitHubURL(kind={self.kind},owner={self.owner},"
             f"repo={self.repo}{branch_info})"
        )

_OWNER=r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9\-]{0,37}[A-Za-z0-9])?)"
_REPO=r"(?P<repo>[A-Za-z0-9_.\-]{1,100})"

_PATTERNS: list[tuple[UrlKind,re.Pattern]] = [
    (
        "api",
        re.compile(
            rf"https://api\.github\.com/repos/{_OWNER}/{_REPO}(?:\.git)?(?:/.*)?$",
            re.IGNORECASE,
        ),
    ),
    (
        "https",
        re.compile(
            rf"^https://github\.com/{_OWNER}/{_REPO}"
            r"(?:\.git)?"
            r"(?:/(?:tree|blob|commits?)/(?P<branch>[^/?#\s]+))?(?:[/?#].*)?$",
            re.IGNORECASE,
        ),
    ),
    (
        "ssh",
        re.compile(
            rf"^git@github\.com:{_OWNER}/{_REPO}(?:\.git)?(?:/.*)?$",
            re.IGNORECASE,
        ),
    ),
    (
       "ssh",
       re.compile(
           rf"^ssh://git@github\.com/{_OWNER}/{_REPO}(?:\.git)?$",
           re.IGNORECASE,
       ),
    ),
]

class InvalidGitHubURLError(ValueError):
    pass

def validate_github_url(raw: str) -> ParsedGitHubURL:
    url = raw.strip()

    if not url:
        raise InvalidGitHubURLError("URL must not be empty.")

    for kind,pattern in _PATTERNS:
        m = pattern.match(url)
        if m:
            groups=m.groupdict()
            repo = groups["repo"]
            if repo.endswith(".git"):
                repo=repo[:-4]
            return ParsedGitHubURL(
                 raw=raw,
                 kind=kind,
                 owner=groups["owner"],
                 repo=repo,
                 branch=groups.get("branch"),
             )
    raise InvalidGitHubURLError(
        f"'{url}'does not look like a valid GitHub URL.\n"
        "Accepted formats:\n"
        " HTTPS : https://github.com/owner/repo\n"
        " SSH : git@github.com:owner/repo.git\n"
        " API :https://api.github.com/repos/owner/repo"
    )

def is_valid_github_url(raw: str)-> bool:
    try:
        validate_github_url(raw)
        return True
    except InvalidGitHubURLError:
        return False


