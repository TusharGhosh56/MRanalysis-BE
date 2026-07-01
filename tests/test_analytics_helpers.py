from app.analytics.helpers import (
    classify_commit_message,
    file_extension,
    is_merge_commit,
    pattern_counts,
)


def test_file_extension():
    assert file_extension("src/main.py") == ".py"
    assert file_extension("README") == "(no extension)"
    assert file_extension(".gitignore") == "(no extension)"


def test_classify_commit_message():
    assert classify_commit_message("feat: add login", is_merge=False) == "feat"
    assert classify_commit_message("fix(api): handle null", is_merge=False) == "fix"
    assert classify_commit_message("random commit", is_merge=False) == "other"
    assert classify_commit_message("Merge branch 'main'", is_merge=False) == "merge"


def test_is_merge_commit():
    assert is_merge_commit("Merge pull request #1", 1) is True
    assert is_merge_commit("feat: x", 2) is True
    assert is_merge_commit("feat: x", 1) is False


def test_pattern_counts():
    result = pattern_counts([("feat", 2), ("fix", 1), ("feat", 1)])
    assert result == [
        {"category": "feat", "count": 3},
        {"category": "fix", "count": 1},
    ]
