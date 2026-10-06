import io
import zipfile

from app import certificate

GOOD = [
    {"name": "Asha Verma", "email": "asha@example.com"},
    {"name": "Ravi Kumar", "email": "ravi@example.com", "course": "Advanced Python"},
]


def submit(client, recipients=GOOD, **extra):
    return client.post("/jobs", json={"event_name": "Python Bootcamp",
                                      "recipients": recipients, **extra})


# --- Creating a generation job -------------------------------------------
def test_create_job_returns_202_and_job_id(client):
    r = submit(client, issued_by="Acme Academy", issue_date="2026-10-01")
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"] and body["total"] == 2
    assert body["status_url"] == f"/jobs/{body['job_id']}"


def test_unknown_job_is_404(client):
    assert client.get("/jobs/doesnotexist").status_code == 404


# --- Input validation ------------------------------------------------------
def test_empty_recipient_list_rejected(client):
    assert submit(client, recipients=[]).status_code == 422


def test_missing_event_name_rejected(client):
    assert client.post("/jobs", json={"recipients": GOOD}).status_code == 422


def test_too_many_recipients_rejected(client):
    many = [{"name": f"P{i}", "email": f"p{i}@example.com"} for i in range(51)]
    assert submit(client, recipients=many).status_code == 422


def test_invalid_recipients_are_reported_not_fatal(client):
    mixed = GOOD + [
        {"name": "", "email": "x@example.com"},
        {"name": "No Email"},
        {"name": "Bad Email", "email": "not-an-email"},
        {"name": "Asha Again", "email": "ASHA@example.com"},  # duplicate
        {"name": "日本語", "email": "jp@example.com"},          # unsupported font chars
    ]
    job = submit(client, recipients=mixed).json()
    status = client.get(job["status_url"]).json()
    assert status["status"] == "completed_with_errors"
    assert status["succeeded"] == 2 and status["failed"] == 5
    by_pos = {c["position"]: c for c in status["certificates"]}
    assert all(by_pos[i]["error"] for i in range(2, 7))
    assert "duplicate" in by_pos[5]["error"]


def test_all_invalid_marks_job_failed(client):
    job = submit(client, recipients=[{"name": "", "email": "bad"}]).json()
    assert job["status"] == "failed"
    assert client.get(job["status_url"]).json()["failed"] == 1


# --- Certificate generation + status/progress ---------------------------------
def test_job_completes_and_reports_progress(client):
    job = submit(client).json()
    status = client.get(job["status_url"]).json()
    assert status["status"] == "completed"
    assert (status["total"], status["succeeded"], status["failed"], status["pending"]) == (2, 2, 0, 0)
    assert all(c["status"] == "success" and c["download_url"] for c in status["certificates"])


# --- Individual certificate failure ---------------------------------------------
def test_one_failure_does_not_block_others(client, monkeypatch):
    real = certificate.generate_certificate_pdf

    def flaky(path, **kw):
        if kw["name"] == "Ravi Kumar":
            raise RuntimeError("boom")
        return real(path, **kw)

    monkeypatch.setattr(certificate, "generate_certificate_pdf", flaky)
    job = submit(client).json()
    status = client.get(job["status_url"]).json()
    assert status["status"] == "completed_with_errors"
    assert (status["succeeded"], status["failed"]) == (1, 1)
    failed = next(c for c in status["certificates"] if c["status"] == "failed")
    assert failed["name"] == "Ravi Kumar" and "boom" in failed["error"]
    assert failed["download_url"] is None


# --- Retrieving generated certificates --------------------------------------------
def test_download_single_certificate_is_pdf(client):
    job = submit(client).json()
    cert = client.get(job["status_url"]).json()["certificates"][0]
    r = client.get(cert["download_url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_download_all_as_zip(client):
    job = submit(client).json()
    r = client.get(f"/jobs/{job['job_id']}/download")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len(names) == 2 and all(n.endswith(".pdf") for n in names)


def test_cannot_download_failed_or_foreign_certificate(client):
    job = submit(client, recipients=GOOD + [{"name": "", "email": "bad"}]).json()
    certs = client.get(job["status_url"]).json()["certificates"]
    failed = next(c for c in certs if c["status"] == "failed")
    assert client.get(f"/jobs/{job['job_id']}/certificates/{failed['id']}").status_code == 409
    other = submit(client).json()
    assert client.get(f"/jobs/{other['job_id']}/certificates/{certs[0]['id']}").status_code == 404


def test_download_all_with_nothing_ready_is_409(client):
    job = submit(client, recipients=[{"name": "", "email": "bad"}]).json()
    assert client.get(f"/jobs/{job['job_id']}/download").status_code == 409
