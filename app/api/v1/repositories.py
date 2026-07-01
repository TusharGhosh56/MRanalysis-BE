from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import DbSession, get_current_user
from app.core.cache import get_cached_analytics, get_repo_progress, set_cached_analytics
from app.git.url_parser import InvalidRepositoryUrlError
from app.models.enums import RepositoryStatus
from app.models.user import User
from app.schemas.repository import (
    METRIC_KEYS,
    AnalysisStatusResponse,
    AnalyticsResponse,
    CreateRepositoryRequest,
    MetricSnapshotResponse,
    RepositoryDetailResponse,
    RepositoryHistoryItem,
    RepositoryListResponse,
    RepositoryResponse,
    SubmitRepositoryResponse,
    SummaryPayload,
)
from app.services.repository_service import (
    AnalysisNotCompleteError,
    DuplicateRepositoryError,
    InvalidMetricKeyError,
    RepositoryNotFoundError,
    create_repository,
    delete_repository_data,
    get_all_analytics,
    get_latest_job,
    get_metric_analytics,
    get_summary_snapshot,
    get_user_repository,
    list_repositories_with_summary,
    reset_repository_for_reanalysis,
)
from app.workers.tasks import enqueue_analysis

router = APIRouter(prefix="/repositories", tags=["repositories"])

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
ANALYSIS_PENDING = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Analysis not complete",
)


def _to_response(repo) -> RepositoryResponse:
    return RepositoryResponse.model_validate(repo)


@router.post(
    "",
    response_model=SubmitRepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a repository and start analysis",
)
def create_repo(
    payload: CreateRepositoryRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> SubmitRepositoryResponse:
    try:
        repository, job = create_repository(db, user=current_user, url=payload.url)
    except InvalidRepositoryUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except DuplicateRepositoryError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository already exists for this user",
        ) from None

    enqueue_analysis(repository.id)
    return SubmitRepositoryResponse(
        job_id=job.id,
        repository_id=repository.id,
        owner=repository.owner,
        name=repository.name,
        url=repository.url,
        status=repository.status,
        created_at=repository.created_at,
    )


@router.get("", response_model=RepositoryListResponse)
def list_repos(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> RepositoryListResponse:
    items, total = list_repositories_with_summary(db, user_id=current_user.id)
    history_items = []
    for repo, raw_summary in items:
        summary = None
        if raw_summary:
            summary = SummaryPayload(
                total_commits=raw_summary["total_commits"],
                total_contributors=raw_summary["total_contributors"],
                first_commit=raw_summary.get("first_commit"),
                last_commit=raw_summary.get("last_commit"),
                avg_commits_per_day=raw_summary["avg_commits_per_day"],
            )
        history_items.append(
            RepositoryHistoryItem(**_to_response(repo).model_dump(), summary=summary)
        )
    return RepositoryListResponse(items=history_items, total=total)


@router.get("/{repository_id}", response_model=RepositoryDetailResponse)
def get_repo(
    repository_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> RepositoryDetailResponse:
    try:
        repo = get_user_repository(db, user_id=current_user.id, repository_id=repository_id)
    except RepositoryNotFoundError:
        raise NOT_FOUND from None

    summary = None
    if repo.status == RepositoryStatus.COMPLETED:
        raw = get_summary_snapshot(db, repo.id)
        if raw:
            summary = SummaryPayload(
                total_commits=raw["total_commits"],
                total_contributors=raw["total_contributors"],
                first_commit=raw.get("first_commit"),
                last_commit=raw.get("last_commit"),
                avg_commits_per_day=raw["avg_commits_per_day"],
            )

    return RepositoryDetailResponse(**_to_response(repo).model_dump(), summary=summary)


@router.get("/{repository_id}/status", response_model=AnalysisStatusResponse)
def get_status(
    repository_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> AnalysisStatusResponse:
    try:
        repo = get_user_repository(db, user_id=current_user.id, repository_id=repository_id)
    except RepositoryNotFoundError:
        raise NOT_FOUND from None

    job = get_latest_job(db, repo.id)
    progress = get_repo_progress(repo.id)
    return AnalysisStatusResponse(
        status=repo.status,
        stage=progress.get("stage") if progress else (job.stage if job else None),
        progress_pct=(
            progress.get("progress_pct", 0) if progress else (job.progress_pct if job else 0)
        ),
        error_message=job.error_message if job else None,
    )


@router.get("/{repository_id}/analytics", response_model=AnalyticsResponse)
def get_analytics(
    repository_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> AnalyticsResponse:
    try:
        repo = get_user_repository(db, user_id=current_user.id, repository_id=repository_id)
    except RepositoryNotFoundError:
        raise NOT_FOUND from None

    cached = get_cached_analytics(repo.id)
    if cached:
        response.headers["Cache-Control"] = f"private, max-age={300}"
        return AnalyticsResponse(**cached)

    try:
        metrics, computed_at = get_all_analytics(db, repo)
    except AnalysisNotCompleteError:
        raise ANALYSIS_PENDING from None

    payload = AnalyticsResponse(
        repository_id=repo.id,
        computed_at=computed_at,
        metrics=metrics,
    )
    set_cached_analytics(repo.id, payload.model_dump(mode="json"))
    response.headers["Cache-Control"] = f"private, max-age={300}"
    return payload


@router.get("/{repository_id}/analytics/{metric}", response_model=MetricSnapshotResponse)
def get_analytics_metric(
    repository_id: UUID,
    metric: str,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> MetricSnapshotResponse:
    if metric not in METRIC_KEYS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown metric")

    try:
        repo = get_user_repository(db, user_id=current_user.id, repository_id=repository_id)
    except RepositoryNotFoundError:
        raise NOT_FOUND from None

    cached = get_cached_analytics(repo.id, metric=metric)
    if cached:
        response.headers["Cache-Control"] = f"private, max-age={300}"
        return MetricSnapshotResponse(**cached)

    try:
        snap = get_metric_analytics(db, repo, metric)
    except InvalidMetricKeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown metric",
        ) from None
    except AnalysisNotCompleteError:
        raise ANALYSIS_PENDING from None

    payload = MetricSnapshotResponse(
        metric_key=snap.metric_key,
        payload=snap.payload,
        computed_at=snap.computed_at,
    )
    set_cached_analytics(repo.id, payload.model_dump(mode="json"), metric=metric)
    response.headers["Cache-Control"] = f"private, max-age={300}"
    return payload


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(
    repository_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        repo = get_user_repository(db, user_id=current_user.id, repository_id=repository_id)
    except RepositoryNotFoundError:
        raise NOT_FOUND from None

    delete_repository_data(db, repo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{repository_id}/reanalyze",
    response_model=RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reanalyze_repo(
    repository_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> RepositoryResponse:
    try:
        repo = get_user_repository(db, user_id=current_user.id, repository_id=repository_id)
    except RepositoryNotFoundError:
        raise NOT_FOUND from None

    reset_repository_for_reanalysis(db, repo)
    enqueue_analysis(repo.id)
    return _to_response(repo)
