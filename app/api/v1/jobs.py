from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbSession, get_current_user
from app.models.user import User
from app.schemas.repository import JobPollResponse
from app.services.repository_service import JobNotFoundError, build_job_poll_response, get_user_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

JOB_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.get("/{job_id}", response_model=JobPollResponse, summary="Poll job status and results")
def get_job(
    job_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> JobPollResponse:
    try:
        job = get_user_job(db, user_id=current_user.id, job_id=job_id)
    except JobNotFoundError:
        raise JOB_NOT_FOUND from None

    return JobPollResponse(**build_job_poll_response(db, job))
