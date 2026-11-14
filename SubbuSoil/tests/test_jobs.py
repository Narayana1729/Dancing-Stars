import threading
import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import progress as P

client = TestClient(app)


def _wait(job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = P.get_job(job_id)
        if j["status"] != "running":
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_reports_progress_and_result():
    gate, reached = threading.Event(), threading.Event()

    def task(report):
        report("Stage A", 10, "first")
        reached.set()
        gate.wait(5)  # pause mid-way so progress can be read while running
        report("Stage B", 60, "second")
        return {"run_id": "r1"}

    job_id = P.start_job(task, "test")
    assert reached.wait(5)
    mid = P.get_job(job_id)
    assert mid["status"] == "running" and mid["stage"] == "Stage A" and mid["percent"] == 10.0
    gate.set()
    j = _wait(job_id)
    assert j["status"] == "done" and j["percent"] == 100.0 and j["stage"] == "Finished"
    assert P.public(j)["run_id"] == "r1"


def test_failed_job_reports_error_not_exception():
    def task(report):
        raise ValueError("bad polygon")

    job_id = P.start_job(task, "test")
    j = _wait(job_id)
    assert j["status"] == "failed" and "ValueError: bad polygon" in j["error"]
    assert P.public(j)["run_id"] is None


def test_only_one_job_at_a_time():
    gate = threading.Event()
    first = P.start_job(lambda report: (gate.wait(5), {"run_id": "a"})[1], "test")
    try:
        try:
            P.start_job(lambda report: {"run_id": "b"}, "test")
            raise AssertionError("second job should be refused")
        except P.JobBusy:
            pass
    finally:
        gate.set()
    assert _wait(first)["status"] == "done"
    # once the first job has finished, a new one is accepted
    assert _wait(P.start_job(lambda report: {"run_id": "c"}, "test"))["status"] == "done"


def test_report_clamps_percent():
    job_id = P.start_job(lambda report: (report("x", 250, ""), {"run_id": "z"})[1], "test")
    assert _wait(job_id)["status"] == "done"


def test_endpoints_validate_and_report_unknown_jobs():
    r = client.post("/api/v1/analysis/explain/jobs", json={"bbox": [79, 18, 78, 19]})
    assert r.status_code == 422
    r = client.post("/api/v1/analysis/explain/jobs", json={})
    assert r.status_code == 422
    assert client.get("/api/v1/analysis/jobs/doesnotexist").status_code == 404


def test_endpoint_busy_returns_409(monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(P, "explain_task", lambda req, report: (gate.wait(5), {"run_id": "x"})[1])
    body = {"wkt": "POLYGON((78.90 18.30, 79.30 18.28, 79.35 18.60, 78.88 18.62, 78.90 18.30))",
            "start_date": "2026-08-01", "end_date": "2026-11-11"}
    try:
        r1 = client.post("/api/v1/analysis/explain/jobs", json=body)
        assert r1.status_code == 202
        r2 = client.post("/api/v1/analysis/explain/jobs", json=body)
        assert r2.status_code == 409
        s = client.get(f"/api/v1/analysis/jobs/{r1.json()['job_id']}").json()
        assert s["status"] == "running" and s["kind"] == "explain"
    finally:
        gate.set()
