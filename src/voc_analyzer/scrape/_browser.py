"""Shared Playwright browser plumbing for the per-platform scrapers.

This module isolates the flaky IO (launching a real browser, navigating,
auto-scrolling lazy feeds) from the pure ``parse(html)`` functions in each
platform module. Playwright is imported lazily so the rest of the package — and
the offline parse tests — never need a browser installed.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from voc_analyzer import config

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ScrapeError(RuntimeError):
    """A page could not be fetched/rendered (missing browser, network, anti-bot)."""


def stable_id(*parts: str) -> str:
    """Deterministic short id from the given parts (for platforms with no native id)."""
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8", "ignore")).hexdigest()
    return digest[:16]


_COUNT_RE = re.compile(r"([\d,.]+)\s*([kmb]?)", re.IGNORECASE)
_MULTIPLIER = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def parse_count(text: str | None) -> int | None:
    """Parse social counts like '1.2K', '3,400', '5 likes' into an int."""
    if not text:
        return None
    match = _COUNT_RE.search(text.strip())
    if not match:
        return None
    number, suffix = match.groups()
    number = number.replace(",", "")
    try:
        value = float(number)
    except ValueError:
        return None
    return int(value * _MULTIPLIER[suffix.lower()])


_REL_RE = re.compile(
    r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE
)
_REL_DELTAS = {
    "second": lambda n: timedelta(seconds=n),
    "minute": lambda n: timedelta(minutes=n),
    "hour": lambda n: timedelta(hours=n),
    "day": lambda n: timedelta(days=n),
    "week": lambda n: timedelta(weeks=n),
    "month": lambda n: timedelta(days=30 * n),
    "year": lambda n: timedelta(days=365 * n),
}


def relative_time(text: str | None, now: datetime | None = None) -> datetime:
    """Best-effort conversion of '3 days ago' style text to an absolute UTC time.

    Falls back to ``now`` when nothing parseable is found.
    """
    now = now or datetime.now(UTC)
    if not text:
        return now
    match = _REL_RE.search(text)
    if not match:
        return now
    n, unit = int(match.group(1)), match.group(2).lower()
    return now - _REL_DELTAS[unit](n)


class Browser:
    """Context manager around a headless Chromium page renderer.

    Usage::

        with Browser() as browser:
            html = browser.render(url, wait_selector="#content")
    """

    def __init__(
        self,
        headless: bool | None = None,
        profile: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._headless = config.HEADLESS if headless is None else headless
        self._profile = config.BROWSER_PROFILE if profile is None else profile
        self._timeout_ms = config.SCRAPE_TIMEOUT_MS if timeout_ms is None else timeout_ms
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self) -> Browser:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ScrapeError(
                "playwright is not installed; run `uv sync` then "
                "`uv run playwright install chromium`"
            ) from exc

        try:
            self._pw = sync_playwright().start()
            if self._profile:
                self._context = self._pw.chromium.launch_persistent_context(
                    self._profile,
                    headless=self._headless,
                    user_agent=DEFAULT_USER_AGENT,
                    locale="en-US",
                )
            else:
                self._browser = self._pw.chromium.launch(headless=self._headless)
                self._context = self._browser.new_context(
                    user_agent=DEFAULT_USER_AGENT, locale="en-US"
                )
            self._context.set_default_timeout(self._timeout_ms)
        except ScrapeError:
            raise
        except Exception as exc:  # pragma: no cover - depends on env
            self.close()
            raise ScrapeError(f"failed to launch browser: {exc}") from exc
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.close()
        return False

    def close(self) -> None:
        import contextlib

        for obj in (self._context, self._browser):
            if obj is not None:
                with contextlib.suppress(Exception):
                    obj.close()
        if self._pw is not None:
            with contextlib.suppress(Exception):
                self._pw.stop()
        self._context = self._browser = self._pw = None

    def render(
        self,
        url: str,
        wait_selector: str | None = None,
        max_scrolls: int | None = None,
    ) -> str:
        """Navigate to ``url``, trigger lazy loading by scrolling, return final HTML."""
        if self._context is None:  # pragma: no cover - misuse
            raise ScrapeError("Browser must be used as a context manager")

        import contextlib

        max_scrolls = config.MAX_SCROLLS if max_scrolls is None else max_scrolls
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            if wait_selector:
                with contextlib.suppress(Exception):
                    page.wait_for_selector(wait_selector, timeout=self._timeout_ms)
            self._auto_scroll(page, max_scrolls)
            return page.content()
        except Exception as exc:
            raise ScrapeError(f"failed to render {url}: {exc}") from exc
        finally:
            with contextlib.suppress(Exception):
                page.close()

    @staticmethod
    def _auto_scroll(page: object, max_scrolls: int) -> None:
        last_height = -1
        for _ in range(max(0, max_scrolls)):
            page.mouse.wheel(0, 20_000)  # type: ignore[attr-defined]
            page.wait_for_timeout(800)  # type: ignore[attr-defined]
            height = page.evaluate("document.body.scrollHeight")  # type: ignore[attr-defined]
            if height == last_height:
                break
            last_height = height
