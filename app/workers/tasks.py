from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select

from app.analytics.engine import AnalyticsEngine
from app.core.cache import invalidate_analytics_cache, set_repo_progress
from app.db.session import SessionLocal
from app.git.cloner import GitCloneError, GitRepositoryCloner
from app.git.history import parse_repository_history
from app.models.commit import Commit
from app.models.enums import RepositoryStatus
from app.models.file_change import FileChange
from app.models.repository import Repository
from app.services.repository_service import get_latest_job, update_job_progress
from app.workers.celery_app import celery_app


def _get_repository(db, repository_id: str) -> Repository:
    repo = db.get(Repository, UUID(repository_id))
    if repo is None:
        raise ValueError(f"Repository {repository_id} not found")
    return repo


def _set_progress(db, repo: Repository, stage: str, progress_pct: int) -> None:
    update_job_progress(db, repo, stage=stage, progress_pct=progress_pct)
    set_repo_progress(repo.id, stage=stage, progress_pct=progress_pct)


@celery_app.task(bind=True, name="run_analysis_pipeline")
def run_analysis_pipeline(self, repository_id: str) -> None:
    db = SessionLocal()
    repo = _get_repository(db, repository_id)
    job = get_latest_job(db, repo.id)
    if job:
        job.celery_task_id = self.request.id
        db.commit()

    try:
        clone_repo(repository_id)
        parse_history(repository_id)
        compute_analytics(repository_id)
        mark_completed(repository_id)
    except Exception as exc:
        repo = _get_repository(db, repository_id)
        update_job_progress(
            db,
            repo,
            status=RepositoryStatus.FAILED,
            stage="failed",
            progress_pct=0,
            error_message=str(exc),
        )
        set_repo_progress(repo.id, stage="failed", progress_pct=0)
        raise
    finally:
        db.close()


@celery_app.task(name="clone_repo")
def clone_repo(repository_id: str) -> None:
    db = SessionLocal()
    try:
        repo = _get_repository(db, repository_id)
        invalidate_analytics_cache(repo.id)
        update_job_progress(
            db, repo, status=RepositoryStatus.CLONING, stage="clone", progress_pct=5
        )
        set_repo_progress(repo.id, stage="clone", progress_pct=5)

        cloner = GitRepositoryCloner()
        cloner.clone(url=repo.url, owner=repo.owner, name=repo.name)

        update_job_progress(db, repo, stage="clone", progress_pct=25)
        set_repo_progress(repo.id, stage="clone", progress_pct=25)
    except GitCloneError as exc:
        repo = _get_repository(db, repository_id)
        update_job_progress(
            db,
            repo,
            status=RepositoryStatus.FAILED,
            stage="clone",
            progress_pct=0,
            error_message=str(exc),
        )
        raise
    finally:
        db.close()


@celery_app.task(name="parse_history")
def parse_history(repository_id: str) -> None:
    db = SessionLocal()
    try:
        repo = _get_repository(db, repository_id)
        update_job_progress(
            db, repo, status=RepositoryStatus.PARSING, stage="parse", progress_pct=30
        )
        set_repo_progress(repo.id, stage="parse", progress_pct=30)

        db.execute(delete(FileChange).where(
            FileChange.commit_id.in_(
                select(Commit.id).where(Commit.repository_id == repo.id)
            )
        ))
        db.execute(delete(Commit).where(Commit.repository_id == repo.id))
        db.commit()

        def on_progress(pct: int) -> None:
            mapped = min(85, 30 + int(pct * 0.55))
            _set_progress(db, repo, "parse", mapped)

        parse_repository_history(db, repo.id, repo.clone_path, on_progress=on_progress)

        update_job_progress(db, repo, stage="parse", progress_pct=85)
        set_repo_progress(repo.id, stage="parse", progress_pct=85)
    finally:
        db.close()


@celery_app.task(name="compute_analytics")
def compute_analytics(repository_id: str) -> None:
    db = SessionLocal()
    try:
        repo = _get_repository(db, repository_id)
        update_job_progress(
            db, repo, status=RepositoryStatus.ANALYZING, stage="analyze", progress_pct=90
        )
        set_repo_progress(repo.id, stage="analyze", progress_pct=90)

        engine = AnalyticsEngine(db, repo.id)
        engine.run()

        update_job_progress(db, repo, stage="analyze", progress_pct=98)
        set_repo_progress(repo.id, stage="analyze", progress_pct=98)
    finally:
        db.close()


@celery_app.task(name="mark_completed")
def mark_completed(repository_id: str) -> None:
    db = SessionLocal()
    try:
        repo = _get_repository(db, repository_id)
        repo.status = RepositoryStatus.COMPLETED
        repo.analyzed_at = datetime.now(UTC)
        job = get_latest_job(db, repo.id)
        if job:
            job.stage = "completed"
            job.progress_pct = 100
            job.error_message = None
        db.commit()
        set_repo_progress(repo.id, stage="completed", progress_pct=100)
        invalidate_analytics_cache(repo.id)
    finally:
        db.close()


def enqueue_analysis(repository_id: UUID) -> str:
    result = run_analysis_pipeline.delay(str(repository_id))
    return result.id
