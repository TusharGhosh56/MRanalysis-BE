import re
from collections import defaultdict

WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

CONVENTIONAL_COMMIT_PREFIXES = (
    "feat",
    "fix",
    "chore",
    "docs",
    "refactor",
    "test",
    "style",
    "perf",
    "build",
    "ci",
    "revert",
)


def file_extension(path: str) -> str:
    normalized = path.replace("\\", "/")
    if "/" in normalized:
        filename = normalized.rsplit("/", 1)[-1]
    else:
        filename = normalized
    if "." not in filename or filename.startswith("."):
        return "(no extension)"
    return "." + filename.rsplit(".", 1)[-1].lower()


def classify_commit_message(message: str, *, is_merge: bool) -> str:
    if is_merge:
        return "merge"
    first_line = (message or "").strip().splitlines()[0].lower() if message else ""
    if first_line.startswith("merge "):
        return "merge"
    match = re.match(r"^(\w+)(?:\([^)]+\))?!?:", first_line)
    if match:
        category = match.group(1)
        if category in CONVENTIONAL_COMMIT_PREFIXES:
            return category
    if first_line.startswith("fix"):
        return "fix"
    if first_line.startswith("feat"):
        return "feat"
    return "other"


def is_merge_commit(message: str, parent_count: int) -> bool:
    if parent_count > 1:
        return True
    first_line = (message or "").strip().splitlines()[0].lower() if message else ""
    return first_line.startswith("merge ")


def pattern_counts(messages: list[tuple[str, int]]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = defaultdict(int)
    for category, amount in messages:
        counts[category] += amount
    return [
        {"category": category, "count": count}
        for category, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]
