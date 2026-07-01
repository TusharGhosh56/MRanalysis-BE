from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RepositoryStatus

METRIC_KEYS = frozenset(
    {
        "summary",
        "commits_per_week",
        "top_contributors",
        "top_modified_files",
        "inactive_contributors",
        "folder_growth",
        "bus_factor",
        "largest_commits",
    }
)


class CreateRepositoryRequest(BaseModel):
    url: str = Field(min_length=1, max_length=512)


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner: str
    name: str
    url: str
    status: RepositoryStatus
    created_at: datetime
    analyzed_at: datetime | None = None


class SummaryPayload(BaseModel):
    total_commits: int
    total_contributors: int
    first_commit: str | None = None
    last_commit: str | None = None
    avg_commits_per_day: float


class RepositoryHistoryItem(RepositoryResponse):
    summary: SummaryPayload | None = None


class RepositoryListResponse(BaseModel):
    items: list[RepositoryHistoryItem]
    total: int


class RepositoryDetailResponse(RepositoryResponse):
    summary: SummaryPayload | None = None


class AnalysisStatusResponse(BaseModel):
    status: RepositoryStatus
    stage: str | None = None
    progress_pct: int
    error_message: str | None = None


class MetricSnapshotResponse(BaseModel):
    metric_key: str
    payload: Any
    computed_at: datetime


class AnalyticsResponse(BaseModel):
    repository_id: UUID
    computed_at: datetime
    metrics: dict[str, Any]


class SubmitRepositoryResponse(BaseModel):
    job_id: UUID
    repository_id: UUID
    owner: str
    name: str
    url: str
    status: RepositoryStatus
    created_at: datetime


class CompletedRepositoryPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner: str
    name: str
    url: str
    status: RepositoryStatus
    created_at: datetime
    analyzed_at: datetime | None = None


class AnalysisResult(BaseModel):
    repository: CompletedRepositoryPayload
    computed_at: datetime
    metrics: dict[str, Any]


class JobPollResponse(BaseModel):
    job_id: UUID
    repository_id: UUID
    status: RepositoryStatus
    stage: str | None = None
    progress_pct: int
    error_message: str | None = None
    result: AnalysisResult | None = None
