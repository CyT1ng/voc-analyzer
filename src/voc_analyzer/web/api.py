"""FastAPI app: wraps the pipeline, streams progress over SSE, serves the built SPA.

Run with the ``voc-analyzer-web`` entry point (``main()``). LLM keys stay server-side (read
from the environment / ``.env``) and are never accepted from the browser.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from voc_analyzer import __version__, config
from voc_analyzer.report import render
from voc_analyzer.scrape import FETCHERS
from voc_analyzer.web import jobs as jobs_mod
from voc_analyzer.web.models import (
    CreateAnalysisRequest,
    HealthResponse,
    JobCreatedResponse,
    JobStatusResponse,
    MetaResponse,
)

app = FastAPI(title="VoC Analyzer", version=__version__)

_origins = [o.strip() for o in os.getenv("VOC_WEB_CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _origins if o],
    allow_methods=["*"],
    allow_headers=["*"],
)

STORE = jobs_mod.JobStore()


# --- API ---
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.get("/api/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    return MetaResponse(
        platforms=list(FETCHERS),
        llm_enabled=config.llm_enabled(),
        llm_provider=config.llm_provider(),
        models=config.llm_models(),
        default_model=config.llm_default_model(),
        gather_defaults={
            "max_rounds": config.GATHER_MAX_ROUNDS,
            "max_total": config.GATHER_MAX_TOTAL,
            "target": config.GATHER_TARGET,
        },
    )


@app.get("/api/models")
def models() -> dict:
    """Full model catalog from the provider (live, cached). Falls back to the curated list."""
    return {"models": config.llm_available_models()}


@app.post("/api/analyses", response_model=JobCreatedResponse, status_code=202)
async def create_analysis(req: CreateAnalysisRequest) -> JobCreatedResponse:
    if not req.demo and not req.platforms:
        req.platforms = list(FETCHERS)  # mirror the CLI default
    job = STORE.create()
    # Run on a dedicated worker thread (decoupled from this request's task, which would be
    # cancelled when the response completes).
    jobs_mod.submit_job(job, req)
    return JobCreatedResponse(job_id=job.id, status=job.status)


@app.get("/api/analyses/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = _job_or_404(job_id)
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        error=job.error,
        progress=list(job.progress),
        result=job.result if job.status == "done" else None,
        rounds=job.rounds,
        stop_reason=job.stop_reason,
        controller=job.controller,
        comment_count=job.comment_count,
    )


@app.get("/api/analyses/{job_id}/progress")
async def progress(job_id: str) -> StreamingResponse:
    job = _job_or_404(job_id)

    async def event_gen():
        # Poll the worker-thread-populated progress list + status. The worker sets a terminal
        # status only after all progress is appended, so once we observe it we flush the rest
        # and finish. (Works the same under uvicorn and the test client.)
        sent = 0
        while True:
            while sent < len(job.progress):
                yield _sse({"type": "progress", "line": job.progress[sent]})
                sent += 1
            if job.status in ("done", "error"):
                while sent < len(job.progress):  # flush any line appended since the check
                    yield _sse({"type": "progress", "line": job.progress[sent]})
                    sent += 1
                break
            await asyncio.sleep(0.1)
        if job.status == "error":
            yield _sse({"type": "error", "error": job.error})
        else:
            yield _sse({"type": "done"})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/analyses/{job_id}/report.md")
def report_md(job_id: str) -> PlainTextResponse:
    job = _require_done(job_id)
    return PlainTextResponse(
        render.to_markdown(job.result),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="report.md"'},
    )


@app.get("/api/analyses/{job_id}/analysis.json")
def analysis_json(job_id: str) -> Response:
    job = _require_done(job_id)
    return Response(
        json.dumps(job.result, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="analysis.json"'},
    )


def _job_or_404(job_id: str) -> jobs_mod.Job:
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return job


def _require_done(job_id: str) -> jobs_mod.Job:
    job = _job_or_404(job_id)
    if job.status != "done" or job.result is None:
        raise HTTPException(status_code=409, detail=f"job not finished (status: {job.status})")
    return job


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


# --- static SPA (production: serve the built frontend) ---
def _mount_static() -> None:
    static_dir = os.getenv("VOC_WEB_STATIC_DIR")
    if not static_dir:
        return
    dist = Path(static_dir)
    if not (dist / "index.html").exists():
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> HTMLResponse:
        last = full_path.rsplit("/", 1)[-1]
        # Unknown API route, or a missing static-looking file (has an extension): 404 —
        # don't mask it with the SPA shell (that served HTML as /style.css etc.). Real
        # assets are handled by the /assets mount above; only navigation paths fall through.
        if full_path.startswith("api") or "." in last:
            raise HTTPException(status_code=404, detail="not found")
        return HTMLResponse((dist / "index.html").read_text(encoding="utf-8"))


_mount_static()


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("VOC_WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("VOC_WEB_PORT", "8000")),
    )
