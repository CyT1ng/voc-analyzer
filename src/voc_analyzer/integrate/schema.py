from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["youtube", "reddit", "tiktok", "instagram", "x"]


class Comment(BaseModel):
    """Unified record produced by every scraper.

    The schema is the contract between scrape/ and analyze/ — change it
    deliberately, because everything downstream depends on it.
    """

    source: Source
    source_id: str
    text: str
    author: str | None = None
    timestamp: datetime
    likes: int | None = None
    url: str
    raw: dict = Field(default_factory=dict)
