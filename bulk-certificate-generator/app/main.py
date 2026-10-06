"""Bulk Certificate Generator - FastAPI application."""
import io
import zipfile
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import MAX_RECIPIENTS_PER_JOB
from app.db import Certificate, Job, SessionLocal, init_db
from app.schemas import CertificateOut, JobOut, JobRequest, validate_recipient
from app.service import process_job


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Bulk Certificate Generator", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _job_out(job: Job, include_certs: bool) -> JobOut:
    certs = job.certificates
    ok = sum(c.status == "success" for c in certs)
    bad = sum(c.status == "failed" for c in certs)
    base = f"/jobs/{job.id}"
    return JobOut(
        job_id=job.id,
        status=job.status,
        event_name=job.event_name,
        total=job.total,
        succeeded=ok,
        failed=bad,
        pending=len(certs) - ok - bad,
        status_url=base,
        download_all_url=f"{base}/download" if ok else None,
        certificates=[
            CertificateOut(
                id=c.id, position=c.position, name=c.name, email=c.email,
                status=c.status, error=c.error,
                download_url=f"{base}/certificates/{c.id}" if c.status == "success" else None,
            )
            for c in certs
        ] if include_certs else None,
    )


@app.post("/jobs", response_model=JobOut, status_code=202)
def create_job(body: JobRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Accept a bulk request. Returns 202 immediately; certificates are
    generated in the background. Poll GET /jobs/{job_id} for progress."""
    if len(body.recipients) > MAX_RECIPIENTS_PER_JOB:
        raise HTTPException(
            422, f"Too many recipients (max {MAX_RECIPIENTS_PER_JOB} per job)"
        )

    job = Job(
        event_name=body.event_name.strip(),
        issued_by=body.issued_by.strip(),
        issue_date=(body.issue_date or date.today()).isoformat(),
        total=len(body.recipients),
    )
    seen: set[str] = set()
    for i, raw in enumerate(body.recipients):
        recipient, error = validate_recipient(raw)
        if recipient and recipient.email in seen:
            recipient, error = None, "email: duplicate recipient in this request"
        if recipient:
            seen.add(recipient.email)
            job.certificates.append(Certificate(
                position=i, name=recipient.name, email=recipient.email,
                course=recipient.course, status="pending"))
        else:
            # Invalid rows are recorded as failed so the client sees exactly why.
            job.certificates.append(Certificate(
                position=i,
                name=str(raw["name"])[:300] if raw.get("name") else None,
                email=str(raw["email"])[:300] if raw.get("email") else None,
                status="failed", error=error))

    if all(c.status == "failed" for c in job.certificates):
        job.status = "failed"  # nothing valid to process
        job.finished_at = None
    db.add(job)
    db.commit()
    if job.status != "failed":
        background.add_task(process_job, job.id)
    return _job_out(job, include_certs=False)


def _get_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/jobs/{job_id}", response_model=JobOut)
def job_status(job_id: str, db: Session = Depends(get_db)):
    return _job_out(_get_job(db, job_id), include_certs=True)


@app.get("/jobs/{job_id}/certificates/{cert_id}")
def download_certificate(job_id: str, cert_id: str, db: Session = Depends(get_db)):
    cert = db.get(Certificate, cert_id)
    if not cert or cert.job_id != job_id:
        raise HTTPException(404, "Certificate not found")
    if cert.status != "success" or not cert.file_path or not Path(cert.file_path).exists():
        raise HTTPException(409, f"Certificate not available (status: {cert.status})")
    return FileResponse(cert.file_path, media_type="application/pdf",
                        filename=f"certificate_{cert.id}.pdf")


@app.get("/jobs/{job_id}/download")
def download_all(job_id: str, db: Session = Depends(get_db)):
    """ZIP of every successfully generated certificate in the job."""
    job = _get_job(db, job_id)
    ready = [c for c in job.certificates
             if c.status == "success" and c.file_path and Path(c.file_path).exists()]
    if not ready:
        raise HTTPException(409, f"No certificates available yet (job status: {job.status})")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in ready:
            safe = "".join(ch if ch.isalnum() else "_" for ch in c.name)[:40]
            zf.write(c.file_path, f"{c.position:04d}_{safe}.pdf")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="job_{job.id}.zip"'})
