# Bulk Certificate Generator (Backend API)

A FastAPI service that accepts a list of recipients, generates a PDF certificate
for each one from a single predefined template, tracks progress, and lets the
client retrieve the results.

**Stack:** Python 3.10+, FastAPI, SQLAlchemy 2 + SQLite (any relational DB via `DATABASE_URL`), ReportLab, pytest.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

| Env var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./certificates.db` | Any SQLAlchemy URL (e.g. PostgreSQL) |
| `OUTPUT_DIR` | `./generated_certificates` | Where PDFs are written |
| `MAX_RECIPIENTS_PER_JOB` | `1000` | Upper bound per request |

## Run tests

```bash
pytest -q
```

Covers: job creation, input validation, certificate generation, job status/progress,
individual certificate failure, and certificate retrieval.

## API

### 1. Submit a request — `POST /jobs`  → `202 Accepted`

```bash
curl -X POST http://127.0.0.1:8000/jobs -H "Content-Type: application/json" -d '{
  "event_name": "Python Bootcamp",
  "issued_by": "Acme Academy",
  "issue_date": "2026-10-01",
  "recipients": [
    {"name": "Asha Verma", "email": "asha@example.com"},
    {"name": "Ravi Kumar", "email": "ravi@example.com", "course": "Advanced Python"}
  ]
}'
```

`issued_by`, `issue_date` (defaults to today) and per-recipient `course` are optional.
Response contains `job_id` and `status_url`.

### 2. Check progress — `GET /jobs/{job_id}`

Returns job `status`, counts (`total`, `succeeded`, `failed`, `pending`) and one entry per
recipient with its own `status` (`pending` / `success` / `failed`), `error` (if any) and `download_url`.

Job status: `pending` → `processing` → `completed` | `completed_with_errors` | `failed`.

### 3. Retrieve certificates

- `GET /jobs/{job_id}/certificates/{certificate_id}` — one PDF
- `GET /jobs/{job_id}/download` — ZIP of all successful certificates

(`409` if a certificate/job has nothing available yet or the certificate failed; `404` if unknown.)

## Design decisions

**Background processing (not synchronous).** Rendering hundreds of PDFs inside one HTTP request
risks client/proxy timeouts and ties up a worker. `POST /jobs` therefore validates, stores the
job, returns `202` immediately and renders using FastAPI `BackgroundTasks`; the client polls
`GET /jobs/{id}`. Progress is committed after every certificate, so the status is live.
*Trade-off:* `BackgroundTasks` runs in-process, so a server crash mid-job leaves it `processing`.
For production I would swap in a durable queue (Celery/RQ/Arq) — `process_job(job_id)` is already
a standalone function keyed only by an ID, so that change is small and the API stays identical.

**Validation without all-or-nothing rejection.** The request envelope (event name, 1..N
recipients, max size) is validated strictly with `422`. Each recipient is then validated
individually (name present, ≤100 chars, valid email, no duplicate email in the request, name
encodable by the built-in PDF font). Invalid recipients are recorded as `failed` with a clear
`error`, and valid ones still proceed. If *every* recipient is invalid the job is `failed` immediately.

**Failure isolation.** Each certificate is generated in its own `try/except` and committed
independently. One failure marks only that certificate `failed`; the rest of the job continues.
Final job status is `completed_with_errors` if some succeeded and some failed.

**Data model.** `jobs` (1) → `certificates` (N). Each certificate keeps its original request
position, status, error and file path, so results map back to the submitted list.

**Template.** One landscape-A4 template drawn with ReportLab (no external assets needed);
long names/event titles auto-shrink to fit.

## Known limitations

- Built-in PDF fonts support Latin (Windows-1252) characters only; other scripts are rejected at
  validation. Embedding a TTF font (e.g. Noto) would lift this.
- No authentication/rate limiting; files stored on local disk (swap for object storage in production).
- Jobs interrupted by a process restart are not auto-resumed.
