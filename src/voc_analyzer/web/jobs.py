"""In-memory analysis jobs, run on a background worker thread.

The pipeline is blocking and minutes-long. Each job runs in a dedicated **executor thread**
(not an `asyncio.create_task` coroutine — those get cancelled when the request scope tears
down, which would falsely signal completion). The worker simply appends progress lines to
`job.progress` and writes `job.status`/`job.result` (plain attributes, GIL-safe); the SSE
endpoint *polls* those — no cross-thread event-loop coordination, so it behaves identically
under the test client and uvicorn.

v1 limitation: the store is a process-local dict with no TTL/eviction (jobs grow with count
and are lost on restart) and a fixed worker pool. A shared store (Redis) would be needed to
scale horizontally — out of scope here.
"""

from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from voc_analyzer import _pipeline
from voc_analyzer.web.models import CreateAnalysisRequest

log = logging.getLogger(__name__)

# Bounded pool of background analysis workers (each job occupies one slot for its duration).
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="voc-job")

_MARKUP_RE = re.compile(r"\[/?[a-z0-9 #=._-]+?\]", re.IGNORECASE)


def strip_markup(line: str) -> str:
    """Drop rich-console markup tags (e.g. ``[yellow]…[/yellow]``) and trim whitespace."""
    return _MARKUP_RE.sub("", line).strip()


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending | running | done | error
    progress: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    rounds: int | None = None
    stop_reason: str | None = None
    controller: str | None = None
    comment_count: int | None = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self) -> Job:
        job = Job(id=uuid.uuid4().hex)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)


def submit_job(job: Job, req: CreateAnalysisRequest) -> None:
    """Schedule the blocking pipeline on a dedicated worker thread (decoupled from the request)."""
    _EXECUTOR.submit(_run_job, job, req)


def _run_job(job: Job, req: CreateAnalysisRequest) -> None:
    """Runs in a worker thread; appends progress lines and writes the terminal status/result.

    `status` is set to a terminal value (`done`/`error`) only AFTER all progress has been
    appended, so a reader that observes a terminal status has the complete progress + result.
    """

    def on_message(line: str) -> None:
        clean = strip_markup(line)
        if clean:
            job.progress.append(clean)  # list.append is atomic in CPython

    job.status = "running"
    try:
        run = _pipeline.run_analysis(
            req.product,
            req.keywords,
            req.platforms,
            limit=req.limit,
            use_llm=req.use_llm,
            max_rounds=req.max_rounds,
            target=req.target,
            max_total=req.max_total,
            demo=req.demo,
            model=req.model,
            on_message=on_message,
        )
        job.result = run.analysis
        job.rounds = run.rounds
        job.stop_reason = run.stop_reason
        job.controller = run.controller
        job.comment_count = run.comment_count
        job.status = "done"
    except Exception as exc:  # the pipeline already degrades internally; this is last-resort
        log.exception("analysis job %s failed", job.id)
        job.error = str(exc) or exc.__class__.__name__
        job.status = "error"
