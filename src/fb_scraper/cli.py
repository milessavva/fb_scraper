import argparse
import asyncio
import json
import sys

from playwright.async_api import Error as BrowserError

from .export import write_exports
from .scraper import login, scrape_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Export accessible Facebook personal-profile posts for pandas.")
    commands = parser.add_subparsers(dest="command", required=True)
    auth = commands.add_parser("login", help="Save a manually authenticated session on a machine with a display")
    auth.add_argument("--state", default=".auth/facebook.json")
    auth.add_argument("--browser", help="Path to system Chromium; omit to use Playwright's browser")
    scrape = commands.add_parser("scrape")
    scrape.add_argument("profile_url")
    scrape.add_argument("--state", help="Private Playwright storage-state file; omit for public posts")
    scrape.add_argument("--output", default="output")
    scrape.add_argument("--browser")
    scrape.add_argument("--headed", action="store_true")
    scrape.add_argument("--max-scrolls", type=int, default=200)
    scrape.add_argument("--idle-rounds", type=int, default=5)
    scrape.add_argument("--pause-ms", type=int, default=2000)
    args = parser.parse_args()
    try:
        if args.command == "login":
            asyncio.run(login(args.state, args.browser))
            return 0
        posts, report = asyncio.run(scrape_profile(args.profile_url, storage_state=args.state, executable=args.browser, headed=args.headed, max_scrolls=args.max_scrolls, idle_rounds=args.idle_rounds, pause_ms=args.pause_ms))
        write_exports(posts, report, args.output)
        print(json.dumps(report, indent=2))
        if not posts:
            print("No posts collected. Check login, profile visibility, and current Facebook markup; see report.json.", file=sys.stderr)
            return 2
        return 0
    except (ValueError, OSError, BrowserError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
