# API Contract (Frontend)

Base URL: `http://localhost:8000/api/v1`

All repository and job endpoints require: `Authorization: Bearer <access_token>`

## Auth

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/auth/register` | `{email, password}` | `201` user |
| POST | `/auth/login` | `{email, password}` | `{access_token, token_type}` |
| GET | `/auth/me` | — | user |

---

## Primary flow: submit URL and poll for results

### Step 1 — POST `/repositories`

Submit a public GitHub URL and start background analysis.

**Request:**
```json
{ "url": "https://github.com/owner/repo" }
```

**Response `202 Accepted`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440001",
  "repository_id": "550e8400-e29b-41d4-a716-446655440000",
  "owner": "owner",
  "name": "repo",
  "url": "https://github.com/owner/repo",
  "status": "pending",
  "created_at": "2026-07-01T10:00:00+00:00"
}
```

**FE action:** save `job_id`, show loader, start polling.

**Errors:** `401`, `422` invalid URL

If the same repo URL is submitted again, the existing record is **re-analyzed** (new `job_id`, same `repository_id`).

---

### Step 2 — GET `/jobs/{job_id}` (poll every 2–3s)

Single endpoint for progress **and** final analytics. No second API call needed.

#### While in progress

**Response `200`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440001",
  "repository_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "parsing",
  "stage": "parse",
  "progress_pct": 45,
  "error_message": null,
  "result": null
}
```

Keep polling while `status` is `pending`, `cloning`, `parsing`, or `analyzing`.

#### On failure

**Response `200`:**
```json
{
  "job_id": "...",
  "repository_id": "...",
  "status": "failed",
  "stage": "clone",
  "progress_pct": 0,
  "error_message": "Cmd('git') failed...",
  "result": null
}
```

Stop polling and show `error_message`.

#### On success (all data in one response)

**Response `200`:**
```json
{
  "job_id": "...",
  "repository_id": "...",
  "status": "completed",
  "stage": "completed",
  "progress_pct": 100,
  "error_message": null,
  "result": {
    "repository": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "owner": "owner",
      "name": "repo",
      "url": "https://github.com/owner/repo",
      "status": "completed",
      "created_at": "2026-07-01T10:00:00+00:00",
      "analyzed_at": "2026-07-01T10:05:30+00:00"
    },
    "computed_at": "2026-07-01T10:05:30+00:00",
    "metrics": {
      "summary": {
        "total_commits": 1240,
        "total_contributors": 8,
        "first_commit": "2019-03-01T10:00:00+00:00",
        "last_commit": "2026-06-15T14:30:00+00:00",
        "avg_commits_per_day": 0.62
      },
      "commits_per_week": [{ "week": "2024-W01", "count": 42 }],
      "top_contributors": [{ "name": "Alice", "email": "a@x.com", "commits": 320, "lines_changed": 15400 }],
      "top_modified_files": [{ "path": "src/main.py", "change_count": 87, "churn_score": 12.4 }],
      "inactive_contributors": [{ "name": "Bob", "last_commit_at": "2024-01-01T00:00:00Z", "days_inactive": 545 }],
      "folder_growth": [{ "path": "src/", "commits_first_half": 10, "commits_second_half": 45, "growth_rate": 3.5 }],
      "bus_factor": { "score": 2, "top_contributor_pct": 0.41 },
      "largest_commits": [{ "hash": "abc123", "message": "...", "insertions": 5000, "deletions": 200, "committed_at": "..." }]
    }
  }
}
```

Stop polling and render dashboard from `result.metrics`.

**Errors:** `404` if job not found or not owned by user

---

## FE integration example

```ts
async function analyzeRepo(url: string) {
  const submit = await api.post("/repositories", { url });
  const { job_id } = submit.data;

  while (true) {
    const poll = await api.get(`/jobs/${job_id}`);
    const { status, progress_pct, error_message, result } = poll.data;

    updateLoader(progress_pct);

    if (status === "failed") throw new Error(error_message ?? "Analysis failed");
    if (status === "completed" && result) return result;

    await sleep(2500);
  }
}
```

---

## Optional endpoints (dashboard history)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/repositories` | List user's repos (newest first) with optional `summary` when completed |
| GET | `/repositories/{repository_id}` | Repo detail + summary |
| GET | `/repositories/{repository_id}/analytics` | All metrics (if already completed) |
| DELETE | `/repositories/{repository_id}` | Delete repo |
| POST | `/repositories/{repository_id}/reanalyze` | Re-run analysis |

### History list response (`GET /repositories`)

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "owner": "owner",
      "name": "repo",
      "url": "https://github.com/owner/repo",
      "status": "completed",
      "created_at": "2026-07-01T10:00:00+00:00",
      "analyzed_at": "2026-07-01T10:05:30+00:00",
      "summary": {
        "total_commits": 1240,
        "total_contributors": 8,
        "first_commit": "2019-03-01T10:00:00+00:00",
        "last_commit": "2026-06-15T14:30:00+00:00",
        "avg_commits_per_day": 0.62
      }
    }
  ],
  "total": 1
}
```

`summary` is `null` while analysis is still running or failed.

---

## Running locally

```bash
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker --loglevel=info
```
