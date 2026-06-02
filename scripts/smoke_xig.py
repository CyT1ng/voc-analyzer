"""Interactive smoke test for the X + Instagram scrapers.

Opens a *headed* Chromium with a persistent profile, lets you log into X and
Instagram once, then renders the live search/tag pages, saves the raw HTML to
``.scratch/`` (gitignored), and runs the package parsers against it so we can
see exactly what comes back today.

Because the profile is persistent, the login is reused on every later run: the
script checks whether each site is already authenticated and only prompts you to
log into the ones that aren't. Log in once and subsequent runs are hands-off —
no passwords are ever stored, only the browser's own session cookies (in the
gitignored profile dir).

Usage::

    uv run python scripts/smoke_xig.py "sony wh-1000xm5"

The profile dir defaults to ``./.voc-profile`` (gitignored); override with
``VOC_BROWSER_PROFILE=/path/to/profile``. To drive your real Google Chrome
profile instead of Playwright's bundled Chromium, also set
``VOC_BROWSER_CHANNEL=chrome`` (and fully quit Chrome first).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from voc_analyzer.scrape import instagram as ig_scraper
from voc_analyzer.scrape import x as x_scraper
from voc_analyzer.scrape._browser import DEFAULT_USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path(os.getenv("VOC_BROWSER_PROFILE") or (ROOT / ".voc-profile"))
CHANNEL = os.getenv("VOC_BROWSER_CHANNEL") or None
SCRATCH = ROOT / ".scratch"
TIMEOUT = 30_000
MAX_SCROLLS = 10

# Best-effort "are we already logged in?" probes. (home_url, logged-in selector,
# login page to open if not). These selectors target the current public DOM and
# may drift — if a probe wrongly reports logged-out, you just log in again.
X_LOGIN = "https://x.com/login"
X_PROBE = ("https://x.com/home", '[data-testid="SideNav_AccountSwitcher_Button"]')
IG_LOGIN = "https://www.instagram.com/accounts/login/"
IG_PROBE = ("https://www.instagram.com/", 'svg[aria-label="Home"], a[href="/explore/"]')


def auto_scroll(page) -> None:
    last = -1
    for _ in range(MAX_SCROLLS):
        page.mouse.wheel(0, 20_000)
        page.wait_for_timeout(1000)
        height = page.evaluate("document.body.scrollHeight")
        if height == last:
            break
        last = height


def render(context, url: str, wait_selector: str) -> str:
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(wait_selector, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - diagnostic only
        print(f"  (wait_selector {wait_selector!r} never appeared: {exc})")
    auto_scroll(page)
    html = page.content()
    page.close()
    return html


def report(label: str, html: str, comments, out: Path) -> None:
    out.write_text(html, encoding="utf-8")
    print(f"[{label}] {len(html):,} bytes -> {out.relative_to(ROOT)}; "
          f"parse() -> {len(comments)} comment(s)")
    low = html.lower()
    for marker in ("log in", "sign up", "something went wrong", "captcha", "are you a robot"):
        if marker in low:
            print(f"   ! page text contains {marker!r} (possible wall/challenge)")
    for c in comments[:3]:
        print(f"   - {(c.author or '?')!s:>20} | {c.text[:90]}")


def logged_in(context, home_url: str, ok_selector: str, timeout: int = 10_000) -> bool:
    """Best-effort check: is the persistent session already authenticated for this site?

    Navigates to the logged-in landing page and looks for a selector that only
    appears when signed in. Conservative: anything ambiguous returns False, so we
    fall back to prompting for a manual login rather than silently scraping a wall.
    """
    page = context.new_page()
    try:
        page.goto(home_url, wait_until="domcontentloaded")
        try:
            page.wait_for_selector(ok_selector, timeout=timeout)
            return True
        except Exception:  # noqa: BLE001 - probe only
            return False
    finally:
        page.close()


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "sony wh-1000xm5"
    SCRATCH.mkdir(exist_ok=True)
    PROFILE.mkdir(parents=True, exist_ok=True)
    print(f"profile : {PROFILE}")
    print(f"channel : {CHANNEL or 'chromium (bundled)'}")
    print(f"query   : {query!r}")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE),
            headless=False,
            channel=CHANNEL,
            user_agent=DEFAULT_USER_AGENT,
            locale="en-US",
        )
        ctx.set_default_timeout(TIMEOUT)

        print("\nchecking existing session...")
        checks = [
            ("X", X_LOGIN, logged_in(ctx, *X_PROBE)),
            ("Instagram", IG_LOGIN, logged_in(ctx, *IG_PROBE)),
        ]
        for name, _, ok in checks:
            print(f"  {name}: {'already logged in' if ok else 'NOT logged in'}")
        need = [(name, login) for name, login, ok in checks if not ok]
        if need:
            for _, login in need:
                ctx.new_page().goto(login)
            names = " and ".join(name for name, _ in need)
            input(f"\n>>> Log into {names} in the open tab(s), then press ENTER "
                  "here to run the scrape...\n")
        else:
            print("Both sessions already active — skipping login, scraping now.")

        x_url = x_scraper.SEARCH_URL.format(q=quote_plus(query))
        print(f"\n[X]  rendering {x_url}")
        x_html = render(ctx, x_url, 'article[data-testid="tweet"]')
        report("X", x_html, x_scraper.parse(x_html, x_url), SCRATCH / "x_search.html")

        tag = ig_scraper._tag(query)
        ig_url = ig_scraper.TAG_URL.format(tag=tag)
        print(f"\n[IG] rendering {ig_url}")
        ig_html = render(ctx, ig_url, "article")
        report("IG", ig_html, ig_scraper.parse(ig_html, ig_url), SCRATCH / "instagram_tag.html")

        ctx.close()

    print("\nDone. Raw HTML is in .scratch/ — tell me the counts above, or I'll read it directly.")


if __name__ == "__main__":
    main()
