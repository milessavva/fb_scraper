import asyncio
import shutil
import json

from playwright.async_api import async_playwright

from fb_scraper.scraper import collect_page, scrape_profile

PROFILE = "https://www.facebook.com/alice"
HTML = '''<!doctype html><html><body><main>
<div role="article">
<a href="https://www.facebook.com/alice/posts/101?tracking=x">timestamp</a>
<time datetime="2024-01-02T03:04:05Z"></time>
<div data-ad-preview="message">Hello, café 😊<br>second line<button role="button" onclick="this.parentElement.innerHTML='Full text, café 😊&lt;br&gt;second line'">See more</button></div>
<span aria-label="All reactions: 1.2K"></span><span>23 comments</span>
<div role="article"><a href="https://www.facebook.com/alice/posts/999">shared nested post</a></div>
</div>
<div role="article"><a href="https://www.facebook.com/alice/posts/102">2h</a>
<div data-ad-comet-preview="message">NA</div></div>
</main></body></html>'''


def test_browser_collection_and_expansion():
    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=shutil.which("chromium"))
            try:
                page = await browser.new_page()
                await page.set_content(HTML)
                posts, report = await collect_page(page, PROFILE, max_scrolls=10, idle_rounds=2, pause_ms=0)
                assert [p["post_id"] for p in posts] == ["101", "102"]
                assert posts[0]["text"] == "Full text, café 😊\nsecond line"
                assert posts[0]["reaction_count"] == 1200
                assert posts[0]["comment_count"] == 23
                assert posts[0]["date"] == "2024-01-02"
                assert "reaction_count_rounded" in posts[0]["warnings"]
                assert posts[1]["timestamp"] is None
                assert posts[1]["comment_count"] is None
                assert report["stop_reason"] == "no_new_posts"
                assert report["complete"] is False
            finally:
                await browser.close()
    asyncio.run(run())


def test_scrape_lifecycle_and_cli_export(monkeypatch, tmp_path):
    # Exercise navigation and browser startup without contacting Facebook.
    from playwright.async_api import BrowserContext
    original = BrowserContext.new_page
    async def new_page(self):
        page = await original(self)
        await page.route("https://www.facebook.com/**", lambda route: route.fulfill(status=200, content_type="text/html", body=HTML))
        return page
    monkeypatch.setattr(BrowserContext, "new_page", new_page)
    posts, report = asyncio.run(scrape_profile(PROFILE, executable=shutil.which("chromium"), max_scrolls=3, idle_rounds=1, pause_ms=0))
    assert len(posts) == 2
    assert report["posts_collected"] == 2
    from fb_scraper.cli import main
    monkeypatch.setattr("sys.argv", ["fb-scraper", "scrape", PROFILE, "--browser", shutil.which("chromium"), "--output", str(tmp_path), "--max-scrolls", "3", "--idle-rounds", "1", "--pause-ms", "0"])
    assert main() == 0
    assert len(json.loads((tmp_path / "posts.json").read_text())) == 2
    assert (tmp_path / "posts.csv").exists()


def test_login_gate_report():
    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=shutil.which("chromium"))
            try:
                page = await browser.new_page()
                await page.route("https://www.facebook.com/**", lambda route: route.fulfill(status=200, body="Login"))
                await page.goto("https://www.facebook.com/login")
                posts, report = await collect_page(page, PROFILE, pause_ms=0)
                assert posts == []
                assert report["stop_reason"] == "login_or_checkpoint"
            finally:
                await browser.close()
    asyncio.run(run())


def test_virtualized_feed_keeps_previous_posts():
    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=shutil.which("chromium"))
            try:
                page = await browser.new_page()
                await page.set_content(HTML)
                await page.evaluate("""() => { let n = 0; window.scrollTo = () => {
                    n += 1;
                    if (n === 1) document.body.innerHTML = '<div role="article"><a href="https://www.facebook.com/alice/posts/103">3h</a><div data-ad-preview="message">Third post</div></div>';
                    if (n === 2) document.body.innerHTML = '<div role="article"><a href="https://www.facebook.com/alice/posts/101">4h</a></div>';
                }; }""")
                posts, report = await collect_page(page, PROFILE, max_scrolls=10, idle_rounds=2, pause_ms=0)
                assert [p["post_id"] for p in posts] == ["101", "102", "103"]
                assert posts[0]["reaction_count"] == 1200
                assert posts[0]["timestamp"] == "2024-01-02T03:04:05+00:00"
                assert posts[0]["timestamp_raw"] == "2024-01-02T03:04:05Z"
                assert "reaction_count_rounded" in posts[0]["warnings"]
                assert posts[0]["text"] == "Full text, café 😊\nsecond line"
                assert "text_unavailable" not in posts[0]["warnings"]
                assert report["posts_collected"] == 3
            finally:
                await browser.close()
    asyncio.run(run())
