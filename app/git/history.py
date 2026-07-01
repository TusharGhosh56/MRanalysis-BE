from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.git.fast_log_parser import FastGitLogParser
from app.git.parser import GitHistoryParser

settings = get_settings()


def create_history_parser(db: Session, repository_id) -> GitHistoryParser | FastGitLogParser:
    if settings.PARSE_USE_GIT_LOG:
        return FastGitLogParser(db, repository_id)
    return GitHistoryParser(db, repository_id)


def parse_repository_history(
    db: Session,
    repository_id,
    clone_path: str | Path,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    parser = create_history_parser(db, repository_id)
    return parser.parse(clone_path, on_progress=on_progress)
