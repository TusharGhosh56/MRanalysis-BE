import re
from dataclasses import dataclass
from urllib.parse import urlparse

GITHUB_HTTPS_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$"
)
GITHUB_SSH_RE = re.compile(r"^git@github\.com:(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?$")


class InvalidRepositoryUrlError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedGitHubUrl:
    owner: str
    name: str
    url: str


def parse_github_url(raw_url: str) -> ParsedGitHubUrl:
    url = raw_url.strip()
    if not url:
        raise InvalidRepositoryUrlError("URL is required")

    match = GITHUB_HTTPS_RE.match(url) or GITHUB_SSH_RE.match(url)
    if match:
        owner = match.group("owner")
        name = match.group("name").removesuffix(".git")
        canonical = f"https://github.com/{owner}/{name}"
        return ParsedGitHubUrl(owner=owner, name=name, url=canonical)

    parsed = urlparse(url)
    if parsed.netloc.endswith("github.com") and parsed.path.count("/") >= 2:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            owner, name = parts[0], parts[1].removesuffix(".git")
            canonical = f"https://github.com/{owner}/{name}"
            return ParsedGitHubUrl(owner=owner, name=name, url=canonical)

    raise InvalidRepositoryUrlError(
        "URL must be a public GitHub repository (https://github.com/owner/repo)"
    )
