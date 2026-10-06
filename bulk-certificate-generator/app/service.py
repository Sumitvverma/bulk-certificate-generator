"""Background job processing: renders every certificate in a job,
isolating failures so one bad certificate never blocks the others."""
import logging
from datetime import datetime, timezone

from app import certificate
from app.config import OUTPUT_DIR
from app.db import Job, SessionLocal

log = logging.getLogger(__name__)


def process_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = "processing"
        db.commit()

        try:
            for cert in [c for c in job.certificates if c.status == "pending"]:
                try:
                    path = OUTPUT_DIR / job.id / f"{cert.id}.pdf"
                    # Looked up on the module so tests can patch the generator.
                    certificate.generate_certificate_pdf(
                        path,
                        name=cert.name,
                        event_name=job.event_name,
                        issue_date=job.issue_date,
                        issued_by=job.issued_by,
                        course=cert.course,
                        certificate_id=cert.id,
                    )
                    cert.status, cert.file_path, cert.error = "success", str(path), None
                except Exception as exc:  # isolate per-certificate failure
                    log.exception("Certificate %s failed", cert.id)
                    cert.status, cert.error = "failed", f"generation error: {exc}"
                db.commit()  # commit per certificate so progress is visible

            failed = sum(c.status == "failed" for c in job.certificates)
            ok = sum(c.status == "success" for c in job.certificates)
            job.status = (
                "completed" if failed == 0
                else "failed" if ok == 0
                else "completed_with_errors"
            )
        except Exception:
            log.exception("Job %s crashed", job_id)
            job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
