# API Contract (Frontend)

Base URL: `http://localhost:8000/api/v1`

All repository and job endpoints require: `Authorization: Bearer <access_token>`

**`repository_id` is the analysis report ID** — one record per user + GitHub repo.

## Auth

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/auth/register` | `{email, password}` | `201` user |
| POST | `/auth/login` | `{email, password}` | `{access_token, token_type}` |
| GET | `/auth/me` | — | user |

---

## Flow overview

| Page | Endpoints | Polling |
|------|-----------|---------|
| **Landing** | `POST /repositories`, `GET /jobs/{job_id}` | Job poll every 2–3s, max **4 minutes** |
| **Analysis Report list** | `GET /repositories` | Optional refresh every 10s if any item in progress |
| **Analysis Report detail** | `GET /repositories/{id}/report` | Poll every 5–10s until `completed` or `failed` |

**Landing UX:** Do not render the metrics dashboard inline. On success show “Analysis complete — View report” and link to `/reports/{repository_id}`. On timeout or failure, link to the same report detail page.

---

## 1. Landing flow

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

Save both `job_id` (for polling) and `repository_id` (for navigation to report page).

If the same repo URL is submitted again, the existing record is **re-analyzed** (new `job_id`, same `repository_id`).

---

### Step 2 — GET `/jobs/{job_id}` (poll every 2–3s, max 4 minutes)

Used **only on the landing page**. After timeout, stop polling and navigate to the report detail page.

| Stop polling when | Landing action |
|-------------------|----------------|
| `status === "completed"` | Show success message + link to `/reports/{repository_id}` |
| `status === "failed"` | Show `error_message` + link to report |
| `polling_timed_out === true` | Show timeout message + link to report (still in progress) |

**While in progress:**
```json
{
  "job_id": "...",
  "repository_id": "...",
  "status": "parsing",
  "stage": "parse",
  "progress_pct": 45,
  "error_message": null,
  "polling_timed_out": false,
  "poll_timeout_seconds": 240,
  "result": null
}
```

**Polling timeout (analysis continues in background):**
```json
{
  "job_id": "...",
  "repository_id": "...",
  "status": "parsing",
  "stage": "parse",
  "progress_pct": 52,
  "error_message": "Analysis is taking longer than expected. Processing continues in the background—you can track progress on the Analysis Report page.",
  "polling_timed_out": true,
  "poll_timeout_seconds": 240,
  "result": null
}
```

**On failure:**
```json
{
  "status": "failed",
  "error_message": "Cmd('git') failed...",
  "polling_timed_out": false,
  "result": null
}
```

**On success:** `status` is `completed` and `result` contains full metrics (same shape as `/report`). Landing should **not** render `result.metrics` — redirect to report detail instead.

Configurable via `JOB_POLL_TIMEOUT_SECONDS` (default `240`).

---

### Landing integration example

```ts
async function submitAnalysis(url: string) {
  const { job_id, repository_id } = (await api.post("/repositories", { url })).data;

  while (true) {
    const poll = await api.get(`/jobs/${job_id}`);
    const { status, progress_pct, error_message, polling_timed_out } = poll.data;

    updateLoader(progress_pct);

    if (polling_timed_out) {
      return { outcome: "timeout", repository_id, message: error_message };
    }
    if (status === "failed") {
      return { outcome: "failed", repository_id, message: error_message };
    }
    if (status === "completed") {
      return { outcome: "completed", repository_id };
    }

    await sleep(2500);
  }
}
```

---

## 2. Analysis Report list

### GET `/repositories`

Returns all analyses for the user (newest first). Use on the **Analysis Report** list page.

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "owner": "owner",
      "name": "repo",
      "url": "https://github.com/owner/repo",
      "status": "parsing",
      "created_at": "2026-07-01T10:00:00+00:00",
      "analyzed_at": null,
      "summary": null,
      "stage": "parse",
      "progress_pct": 52,
      "error_message": null,
      "latest_job_id": "550e8400-e29b-41d4-a716-446655440001"
    },
    {
      "id": "...",
      "owner": "owner",
      "name": "other-repo",
      "status": "completed",
      "analyzed_at": "2026-07-01T10:05:30+00:00",
      "summary": {
        "total_commits": 112,
        "total_contributors": 3,
        "first_commit": "2025-01-06T10:00:00+00:00",
        "last_commit": "2026-06-15T14:30:00+00:00",
        "avg_commits_per_day": 1.47
      },
      "stage": "completed",
      "progress_pct": 100,
      "error_message": null,
      "latest_job_id": "..."
    }
  ],
  "total": 2
}
```

- `summary` is `null` while in progress or failed.
- Optionally poll this endpoint every **10s** while any item has an in-progress `status`.

Clicking a row navigates to `/reports/{id}`.

---

## 3. Analysis Report detail (primary dashboard contract)

### GET `/repositories/{repository_id}/report`

Single endpoint for the report detail page. Poll every **5–10s** while `status` is `pending`, `cloning`, `parsing`, or `analyzing`.

**While in progress:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "owner": "owner",
  "name": "repo",
  "url": "https://github.com/owner/repo",
  "status": "parsing",
  "created_at": "2026-07-01T10:00:00+00:00",
  "analyzed_at": null,
  "stage": "parse",
  "progress_pct": 52,
  "error_message": null,
  "summary": null,
  "computed_at": null,
  "metrics": null
}
```

**When completed:** `summary`, `computed_at`, and `metrics` are populated. `metrics` contains all 16 keys (`summary`, `commits_per_week`, `commits_by_weekday`, `commits_by_hour`, `top_contributors`, `top_modified_files`, `inactive_contributors`, `folder_growth`, `bus_factor`, `largest_commits`, `commit_message_patterns`, `merge_vs_regular`, `file_type_breakdown`, `contributor_timeline`, `code_ownership`, `activity_patterns`).

**When failed:** `error_message` is set; `metrics` is `null`.

### Report detail integration example

```ts
async function loadReport(repositoryId: string) {
  while (true) {
    const { data } = await api.get(`/repositories/${repositoryId}/report`);
    renderReport(data);

    if (data.status === "completed" || data.status === "failed") {
      return data;
    }

    await sleep(5000);
  }
}
```

---

## Legacy / optional endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/repositories/{id}` | Repo metadata + summary only |
| GET | `/repositories/{id}/status` | Progress only |
| GET | `/repositories/{id}/analytics` | All metrics (409 if not complete) |
| DELETE | `/repositories/{id}` | Delete analysis |
| POST | `/repositories/{id}/reanalyze` | Re-run analysis |

Prefer `/report` for the detail dashboard.

---

## Running locally

```bash
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker --loglevel=info
```
