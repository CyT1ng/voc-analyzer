"""Pydantic request/response models for the web API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from voc_analyzer.scrape import FETCHERS


class CreateAnalysisRequest(BaseModel):
    """Body of `POST /api/analyses` — mirrors the CLI `run` options."""

    product: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)
    max_rounds: int | None = Field(default=None, ge=0)
    target: int | None = Field(default=None, ge=0)
    max_total: int | None = Field(default=None, ge=1)
    use_llm: bool = True
    demo: bool = False
    model: str | None = None  # LLM model id for the report; None → server default

    @field_validator("model")
    @classmethod
    def _blank_model_is_none(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None

    @field_validator("product")
    @classmethod
    def _strip_product(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("product must not be empty")
        return v

    @field_validator("platforms")
    @classmethod
    def _known_platforms(cls, v: list[str]) -> list[str]:
        unknown = [p for p in v if p not in FETCHERS]
        if unknown:
            raise ValueError(f"unknown platform(s): {unknown}; choose from {list(FETCHERS)}")
        return v


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | done | error
    error: str | None = None
    progress: list[str] = Field(default_factory=list)
    result: dict | None = None  # the analysis dict, present only when status == "done"
    rounds: int | None = None
    stop_reason: str | None = None
    controller: str | None = None
    comment_count: int | None = None


class MetaResponse(BaseModel):
    platforms: list[str]
    llm_enabled: bool
    llm_provider: str
    models: list[str]
    default_model: str
    gather_defaults: dict


class HealthResponse(BaseModel):
    status: str
    version: str
