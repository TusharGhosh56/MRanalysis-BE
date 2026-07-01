from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.cache import invalidate_analytics_cache
from app.git.cloner import GitRepositoryCloner
from app.git.url_parser import InvalidRepositoryUrlError, parse_github_url
from app.models.analysis_job import AnalysisJob
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.commit import Commit
from app.models.contributor_stat import ContributorStat
from app.models.enums import RepositoryStatus
from app.models.file_change import FileChange
from app.models.repository import Repository
from app.models.user import User

settings = get_settings()


class RepositoryNotFoundError(Exception):
    pass


class DuplicateRepositoryError(Exception):
    pass


class AnalysisNotCompleteError(Exception):
    pass


class InvalidMetricKeyError(Exception):
    pass


class JobNotFoundError(Exception):
    pass


def get_user_repository(db: Session, *, user_id: UUID, repository_id: UUID) -> Repository:
    repo = db.scalar(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.user_id == user_id,
        )
    )
    if repo is None:
        raise RepositoryNotFoundError
    return repo


def create_repository(db: Session, *, user: User, url: str) -> tuple[Repository, AnalysisJob]:
    try:
        parsed = parse_github_url(url)
    except InvalidRepositoryUrlError:
        raise

    existing = db.scalar(
        select(Repository).where(
            Repository.user_id == user.id,
            Repository.owner == parsed.owner,
            Repository.name == parsed.name,
        )
    )
    if existing is not None:
        job = reset_repository_for_reanalysis(db, existing)
        return existing, job

    cloner = GitRepositoryCloner()
    clone_path = str(cloner.clone_path_for(parsed.owner, parsed.name))

    repository = Repository(
        user_id=user.id,
        owner=parsed.owner,
        name=parsed.name,
        url=parsed.url,
        clone_path=clone_path,
        status=RepositoryStatus.PENDING,
    )
    db.add(repository)
    try:
        db.flush()
        job = AnalysisJob(repository_id=repository.id, stage="queued", progress_pct=0)
        db.add(job)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateRepositoryError from exc

    db.refresh(repository)
    db.refresh(job)
    return repository, job


def list_repositories_with_summary(
    db: Session, *, user_id: UUID
) -> tuple[list[tuple[Repository, dict | None]], int]:
    items = list(
        db.scalars(
            select(Repository)
            .where(Repository.user_id == user_id)
            .order_by(Repository.created_at.desc())
        ).all()
    )
    if not items:
        return [], 0

    completed_ids = [repo.id for repo in items if repo.status == RepositoryStatus.COMPLETED]
    summaries: dict[UUID, dict] = {}
    if completed_ids:
        snapshots = db.scalars(
            select(AnalyticsSnapshot).where(
                AnalyticsSnapshot.repository_id.in_(completed_ids),
                AnalyticsSnapshot.metric_key == "summary",
            )
        ).all()
        summaries = {snap.repository_id: snap.payload for snap in snapshots}

    return [(repo, summaries.get(repo.id)) for repo in items], len(items)


def get_summary_snapshot(db: Session, repository_id: UUID) -> dict | None:
    snap = db.scalar(
        select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.repository_id == repository_id,
            AnalyticsSnapshot.metric_key == "summary",
        )
    )
    return snap.payload if snap else None


def get_latest_job(db: Session, repository_id: UUID) -> AnalysisJob | None:
    return db.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.repository_id == repository_id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    )


def delete_repository_data(db: Session, repository: Repository) -> None:
    invalidate_analytics_cache(repository.id)
    GitRepositoryCloner().remove_clone(repository.clone_path)
    db.delete(repository)
    db.commit()


def reset_repository_for_reanalysis(db: Session, repository: Repository) -> AnalysisJob:
    invalidate_analytics_cache(repository.id)
    db.execute(delete(FileChange).where(
        FileChange.commit_id.in_(
            select(Commit.id).where(Commit.repository_id == repository.id)
        )
    ))
    db.execute(delete(Commit).where(Commit.repository_id == repository.id))
    db.execute(delete(ContributorStat).where(ContributorStat.repository_id == repository.id))
    db.execute(
        delete(AnalyticsSnapshot).where(AnalyticsSnapshot.repository_id == repository.id)
    )

    repository.status = RepositoryStatus.PENDING
    repository.analyzed_at = None
    job = AnalysisJob(repository_id=repository.id, stage="queued", progress_pct=0)
    db.add(job)
    db.commit()
    db.refresh(repository)
    db.refresh(job)
    return job


def get_all_analytics(db: Session, repository: Repository) -> tuple[dict, object]:
    if repository.status != RepositoryStatus.COMPLETED:
        raise AnalysisNotCompleteError

    snapshots = db.scalars(
        select(AnalyticsSnapshot).where(AnalyticsSnapshot.repository_id == repository.id)
    ).all()
    if not snapshots:
        raise AnalysisNotCompleteError

    metrics = {snap.metric_key: snap.payload for snap in snapshots}
    computed_at = max(snap.computed_at for snap in snapshots)
    return metrics, computed_at


def get_metric_analytics(db: Session, repository: Repository, metric_key: str) -> AnalyticsSnapshot:
    from app.schemas.repository import METRIC_KEYS

    if metric_key not in METRIC_KEYS:
        raise InvalidMetricKeyError

    if repository.status != RepositoryStatus.COMPLETED:
        raise AnalysisNotCompleteError

    snap = db.scalar(
        select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.repository_id == repository.id,
            AnalyticsSnapshot.metric_key == metric_key,
        )
    )
    if snap is None:
        raise AnalysisNotCompleteError
    return snap


def get_user_job(db: Session, *, user_id: UUID, job_id: UUID) -> AnalysisJob:
    job = db.scalar(
        select(AnalysisJob)
        .join(Repository, Repository.id == AnalysisJob.repository_id)
        .where(AnalysisJob.id == job_id, Repository.user_id == user_id)
    )
    if job is None:
        raise JobNotFoundError
    return job


def build_job_poll_response(db: Session, job: AnalysisJob) -> dict:
    from app.core.cache import get_repo_progress
    from app.schemas.repository import AnalysisResult, CompletedRepositoryPayload, JobPollResponse

    repository = db.get(Repository, job.repository_id)
    if repository is None:
        raise JobNotFoundError

    progress = get_repo_progress(repository.id)
    stage = progress.get("stage") if progress else job.stage
    progress_pct = progress.get("progress_pct", 0) if progress else job.progress_pct

    result = None
    if repository.status == RepositoryStatus.COMPLETED:
        metrics, computed_at = get_all_analytics(db, repository)
        result = AnalysisResult(
            repository=CompletedRepositoryPayload.model_validate(repository),
            computed_at=computed_at,
            metrics=metrics,
        )

    return JobPollResponse(
        job_id=job.id,
        repository_id=repository.id,
        status=repository.status,
        stage=stage,
        progress_pct=progress_pct,
        error_message=job.error_message,
        result=result,
    ).model_dump(mode="json")


def update_job_progress(
    db: Session,
    repository: Repository,
    *,
    status: RepositoryStatus | None = None,
    stage: str | None = None,
    progress_pct: int | None = None,
    error_message: str | None = None,
) -> None:
    if status is not None:
        repository.status = status
    job = get_latest_job(db, repository.id)
    if job:
        if stage is not None:
            job.stage = stage
        if progress_pct is not None:
            job.progress_pct = progress_pct
        if error_message is not None:
            job.error_message = error_message
    db.commit()
