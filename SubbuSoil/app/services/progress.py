"""Background analysis jobs with progress.

A job runs the full pipeline (steps 3-11) in a background thread and records a
percentage and a stage name as it goes. The percentages are fixed milestones
per stage, not timings, so they move in steps rather than smoothly.

Jobs live in memory: they are lost if the server restarts (the finished runs
stay on disk). Only one job runs at a time, so a second request gets a 409.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable

from app.schemas.analysis import ExplainRequest
from app.services.analysis import analyse_run
from app.services.pipeline import prepare

Report = Callable[[str, float, str], None]

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


class JobBusy(RuntimeError):
    pass


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _update(job_id: str, **fields) -> None:
    with _lock:
        _jobs[job_id].update(fields)


def start_job(task: Callable[[Report], dict], kind: str) -> str:
    with _lock:
        if any(j["status"] == "running" for j in _jobs.values()):
            raise JobBusy("Another analysis is already running. Wait for it to finish.")
        job_id = uuid.uuid4().hex[:12]
        _jobs[job_id] = {
            "job_id": job_id, "kind": kind, "status": "running",
            "stage": "Starting", "percent": 0.0, "message": "",
            "started": time.time(), "finished": None, "result": None, "error": None,
        }

    def report(stage: str, percent: float, message: str = "") -> None:
        _update(job_id, stage=stage, percent=round(max(0.0, min(100.0, float(percent))), 1), message=message)

    def run() -> None:
        try:
            result = task(report)
            _update(job_id, status="done", stage="Finished", percent=100.0, message="",
                    result=result, finished=time.time())
        except Exception as e:  # reported to the client, never raised in the thread
            _update(job_id, status="failed", error=f"{type(e).__name__}: {e}", finished=time.time())

    threading.Thread(target=run, daemon=True, name=f"job-{job_id}").start()
    return job_id


def explain_task(req: ExplainRequest, report: Report) -> dict:
    """Steps 3-11 for one request; returns the run id for the viewer."""
    prep = prepare(req, report)
    analyse_run(prep.run_id, req.change, context=req.context, explain=True,
                n_top_regions=req.n_top_regions, report=report)
    return {"run_id": prep.run_id}


def public(job: dict) -> dict:
    end = job["finished"] or time.time()
    return {
        "job_id": job["job_id"],
        "kind": job["kind"],
        "status": job["status"],
        "stage": job["stage"],
        "percent": job["percent"],
        "message": job["message"],
        "elapsed_s": round(end - job["started"], 1),
        "run_id": job["result"]["run_id"] if job["result"] else None,
        "error": job["error"],
    }
