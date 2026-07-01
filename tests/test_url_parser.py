import pytest

from app.git.url_parser import InvalidRepositoryUrlError, parse_github_url


def test_parse_https_url():
    parsed = parse_github_url("https://github.com/torvalds/linux")
    assert parsed.owner == "torvalds"
    assert parsed.name == "linux"
    assert parsed.url == "https://github.com/torvalds/linux"


def test_parse_url_with_git_suffix():
    parsed = parse_github_url("https://github.com/owner/repo.git/")
    assert parsed.owner == "owner"
    assert parsed.name == "repo"


def test_parse_ssh_url():
    parsed = parse_github_url("git@github.com:owner/repo.git")
    assert parsed.owner == "owner"
    assert parsed.name == "repo"


def test_invalid_url_raises():
    with pytest.raises(InvalidRepositoryUrlError):
        parse_github_url("https://gitlab.com/owner/repo")

    with pytest.raises(InvalidRepositoryUrlError):
        parse_github_url("")
