import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from .parsing import parse_count, parse_timestamp, post_identity, profile_url

# Deliberately prefer Facebook's message containers over whole-article text:
# whole-article text includes controls and other people's comments.
EXTRACT = r"""() => [...document.querySelectorAll('[role="article"]')]
  .filter(a => !a.parentElement.closest('[role="article"]'))
  .map(a => {
    const links = [...a.querySelectorAll('a[href]')];
    const link = links.find(l => /\/posts\/|story_fbid=/.test(l.href));
    const message = a.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
    const time = a.querySelector('time[datetime], [data-utime]');
    const labels = [...a.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label'));
    const lines = a.innerText.split('\n').map(s => s.trim()).filter(Boolean);
    const reaction = [...labels, ...lines].find(s => /^All reactions:\s*[\d,]/i.test(s) || /^[\d,.]+\s*[KMB]?\s+reactions?$/i.test(s));
    const comments = [...labels, ...lines].find(s => /^[\d,.]+\s*[KMB]?\s+comments?$/i.test(s));
    return {
      url: link?.href,
      text: message?.innerText ?? null,
      timestamp_raw: time?.getAttribute('datetime') || time?.getAttribute('data-utime') || link?.getAttribute('aria-label') || link?.getAttribute('title') || null,
      reaction_raw: reaction ?? null, comment_raw: comments ?? null,
      text_truncated: message ? [...message.querySelectorAll('[role="button"], a')].some(e => /^See more$/i.test(e.innerText.trim())) : false
    };
  })"""


def normalize(raw: dict, profile: str) -> dict | None:
    identity = post_identity(raw.get("url") or "")
    if identity is None:
        return None
    stamp = parse_timestamp(raw.get("timestamp_raw"))
    parsed = datetime.fromisoformat(stamp) if stamp else None
    reactions = parse_count(raw.get("reaction_raw"))
    comments = parse_count(raw.get("comment_raw"))
    warnings = []
    for key, value in (("timestamp", stamp), ("text", raw.get("text")), ("reaction_count", reactions), ("comment_count", comments)):
        if value is None:
            warnings.append(f"{key}_unavailable")
    if parsed and parsed.tzinfo is None:
        warnings.append("timestamp_timezone_unknown")
    if raw.get("text_truncated"):
        warnings.append("text_may_be_truncated")
    for field in ("reaction", "comment"):
        if raw.get(field + "_raw") and re.search(r"\d\s*[KMB]\b", raw[field + "_raw"], re.I):
            warnings.append(field + "_count_rounded")
    return {
        "post_id": identity[0], "profile_url": profile, "post_url": identity[1],
        "timestamp": stamp, "date": parsed.date().isoformat() if parsed else None,
        "time": parsed.timetz().isoformat() if parsed else None, "text": raw.get("text"),
        "reaction_count": reactions, "comment_count": comments,
        "reaction_count_raw": raw.get("reaction_raw"), "comment_count_raw": raw.get("comment_raw"),
        "timestamp_raw": raw.get("timestamp_raw"), "collected_at": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
    }


async def collect_page(page, profile: str, *, max_scrolls: int = 200, idle_rounds: int = 5, pause_ms: int = 2000) -> tuple[list[dict], dict]:
    if max_scrolls < 1 or idle_rounds < 1 or pause_ms < 0:
        raise ValueError("Scroll limits must be positive and pause_ms nonnegative.")
    seen = {}
    idle = 0
    stop = "scroll_limit"
    rounds = 0
    for rounds in range(1, max_scrolls + 1):
        if "/login" in page.url or "/checkpoint" in page.url:
            stop = "login_or_checkpoint"
            break
        # Expand only message controls, never comment threads or Like buttons.
        buttons = page.locator('[data-ad-preview="message"], [data-ad-comet-preview="message"]').get_by_text("See more", exact=True)
        for button in await buttons.all():
            try:
                await button.click(timeout=1000)
            except Exception:
                # Individual stale/hidden controls must not discard other posts.
                pass
        before = len(seen)
        for raw in await page.evaluate(EXTRACT):
            post = normalize(raw, profile)
            if post is None:
                continue
            old = seen.get(post["post_id"])
            if old:
                # Virtualized feed rerenders can temporarily lose known fields.
                if post["timestamp"] is None and old["timestamp"] is not None:
                    post["timestamp_raw"] = old["timestamp_raw"]
                    if "timestamp_timezone_unknown" in old["warnings"]:
                        post["warnings"].append("timestamp_timezone_unknown")
                for field in ("reaction", "comment"):
                    if post[field + "_count"] is None and old[field + "_count"] is not None:
                        warning = field + "_count_rounded"
                        if warning in old["warnings"]:
                            post["warnings"].append(warning)
                for key, value in old.items():
                    if post.get(key) is None:
                        post[key] = value
                if len(old.get("text") or "") > len(post.get("text") or ""):
                    post["text"] = old["text"]
                    if "text_may_be_truncated" in old["warnings"]:
                        post["warnings"].append("text_may_be_truncated")
                for key in ("timestamp", "text", "reaction_count", "comment_count"):
                    if post[key] is not None:
                        post["warnings"] = [w for w in post["warnings"] if w != key + "_unavailable"]
            seen[post["post_id"]] = post
        idle = idle + 1 if len(seen) == before else 0
        if idle >= idle_rounds:
            stop = "no_new_posts"
            break
        await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        await page.wait_for_timeout(pause_ms)
    posts = list(seen.values())
    report = {
        "profile_url": profile, "posts_collected": len(posts), "scroll_rounds": rounds,
        "stop_reason": stop, "complete": False,
        "limitation": "Only posts exposed by the current Facebook browser session are collected. Feed exhaustion does not prove full profile history.",
        "posts_with_warnings": sum(bool(p["warnings"]) for p in posts),
    }
    return posts, report


def browser_options(headless: bool, executable: str | None) -> dict:
    options = {"headless": headless}
    if executable:
        options["executable_path"] = executable
    return options


async def scrape_profile(url: str, *, storage_state: str | None = None, executable: str | None = None, headed: bool = False, max_scrolls: int = 200, idle_rounds: int = 5, pause_ms: int = 2000) -> tuple[list[dict], dict]:
    profile = profile_url(url)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**browser_options(not headed, executable))
        try:
            context = await browser.new_context(storage_state=storage_state, locale="en-US")
            page = await context.new_page()
            await page.goto(profile, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(pause_ms)
            return await collect_page(page, profile, max_scrolls=max_scrolls, idle_rounds=idle_rounds, pause_ms=pause_ms)
        finally:
            await browser.close()


async def login(state: str, executable: str | None = None) -> None:
    target = Path(state)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**browser_options(False, executable))
        try:
            context = await browser.new_context(locale="en-US")
            page = await context.new_page()
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            await asyncio.to_thread(input, "Log in manually in the browser, then press Enter here to save the session: ")
            # Create with restrictive permissions before Playwright writes cookies.
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.close(fd)
            os.chmod(target, 0o600)
            await context.storage_state(path=str(target))
        finally:
            await browser.close()
