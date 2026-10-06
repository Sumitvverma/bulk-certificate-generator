"""Request validation and response schemas."""
import re
from datetime import date

from pydantic import BaseModel, Field

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Recipient(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=254)
    course: str | None = Field(default=None, max_length=200)


class JobRequest(BaseModel):
    """Envelope is validated strictly; each recipient is validated individually
    later so a single bad row does not reject the whole batch."""
    event_name: str = Field(min_length=1, max_length=200)
    issued_by: str = Field(default="", max_length=200)
    issue_date: date | None = None
    recipients: list[dict] = Field(min_length=1)


def validate_recipient(raw: dict) -> tuple[Recipient | None, str | None]:
    """Return (recipient, None) if valid, else (None, error message)."""
    try:
        r = Recipient.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        errors = getattr(exc, "errors", lambda: [])()
        msg = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'recipient'}: {e['msg']}" for e in errors
        ) or "invalid recipient"
        return None, msg

    r.name = r.name.strip()
    r.email = r.email.strip().lower()
    if not r.name:
        return None, "name: must not be blank"
    if not EMAIL_RE.match(r.email):
        return None, "email: not a valid email address"
    try:
        r.name.encode("cp1252")  # built-in PDF font limitation
    except UnicodeEncodeError:
        return None, "name: contains characters unsupported by the certificate font"
    return r, None


class CertificateOut(BaseModel):
    id: str
    position: int
    name: str | None
    email: str | None
    status: str
    error: str | None
    download_url: str | None


class JobOut(BaseModel):
    job_id: str
    status: str
    event_name: str
    total: int
    succeeded: int
    failed: int
    pending: int
    status_url: str
    download_all_url: str | None
    certificates: list[CertificateOut] | None = None
