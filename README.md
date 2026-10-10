# Facebook personal-profile post collector

Collect posts visible to your browser session from a specified personal profile, then analyze them in pandas. This is an initial browser-based implementation, not a guarantee of all historical posts. Facebook can hide history, show a login wall, change markup, or display rounded counts. Live Facebook extraction has not yet been validated against an authenticated profile.

## Install

Python 3.11+ is required (cloud environment: Python 3.12).

```bash
cd /workspace/fb_scraper
UV_CACHE_DIR=/tmp/fb-scraper-uv-cache uv sync --frozen --extra dev
source .venv/bin/activate
```

The cloud environment already has Chromium at `/usr/bin/chromium`. On another machine, install Playwright's browser with `python -m playwright install chromium`, then omit `--browser` from commands below. Run `pytest -q` to validate parsers, exports, and Chromium collection against a controlled HTML feed.

## Authentication and collection

For posts requiring login, run this on a machine with a graphical display:

```bash
fb-scraper login --state .auth/facebook.json --browser /usr/bin/chromium
```

Log in manually in the opened browser, finish any Facebook challenges, then press Enter in the terminal. The cloud environment has no interactive browser login UI; create a session locally and provide it securely if you need cloud collection. Treat the session file as a password: do not commit it, paste it into chat, or share it. `.auth/` is ignored by Git and login saves the file with owner-only permissions. Use only profiles and posts you are authorized to access. The collector does not bypass privacy controls or login challenges.

```bash
fb-scraper scrape 'https://www.facebook.com/PROFILE_NAME' \
  --state .auth/facebook.json --browser /usr/bin/chromium \
  --output output --max-scrolls 200 --idle-rounds 5 --pause-ms 2000
```

Numeric profiles also work: `https://www.facebook.com/profile.php?id=123456`. Omit `--state` to attempt public posts. Collection expands message "See more" controls, scrolls the profile feed, and deduplicates posts by permalink ID. Increase scroll limits for long histories. The URL alone does not distinguish personal profiles from pages; supply the personal profile you intend to analyze.

The command writes `posts.json`, `posts.csv`, and `report.json`. Zero posts or a navigation error produces a nonzero exit code. A successful nonempty collection still does **not** certify completeness: inspect the stop reason, counts, and per-post warnings. Facebook may load slowly enough to trigger the idle limit before the end of history. The collector includes feed entries exposed on that profile (including pinned/shared entries); it does not establish original authorship.

## DataFrame and export format

```python
from fb_scraper import load_posts
import pandas as pd

df = load_posts("output/posts.json")  # or output/posts.csv
known_timezone = ~df["warnings"].map(lambda w: "timestamp_timezone_unknown" in w)
df["timestamp_parsed"] = pd.to_datetime(df.loc[known_timezone, "timestamp"], errors="coerce", utc=True)
# Choose the source timezone before converting the remaining timestamps.
```

For direct collection from Python, `posts, report = await scrape_profile(url, storage_state=".auth/facebook.json", executable="/usr/bin/chromium")`, then `df = to_dataframe(posts)`.

Each row contains:

| Field | Meaning |
| --- | --- |
| `post_id`, `post_url`, `profile_url` | Stable post identifier, permalink, and requested source profile |
| `timestamp`, `date`, `time` | Parsed publication time and its components, when exposed; time offset only when available |
| `text` | Expanded message text, including Unicode and newlines; no OCR, image text, or comments |
| `reaction_count`, `comment_count` | Nullable integer counts; unknown is missing, never assumed zero |
| `reaction_count_raw`, `comment_count_raw`, `timestamp_raw` | Original labels for auditing |
| `collected_at` | UTC collection timestamp |
| `warnings` | Missing fields, rounded counts, unknown timezone, or potentially truncated text |

English browser labels are required by the current extraction rules. Message containers and timestamp metadata may be unavailable in Facebook's current markup; those fields remain null and get warnings. Relative labels such as `2h` are not converted into invented publication times. A label such as `1.2K` becomes an estimated 1200 with a warning. Counts are snapshots at collection time.

JSON is recommended as the analysis source: it preserves nulls and text exactly. CSV is UTF-8 with **every field quoted**; embedded quotes are doubled, and embedded newlines remain inside the quoted field. Use `load_posts()` rather than splitting CSV lines manually. It preserves literal text such as `NA`, numeric IDs, and nullable integer counts. CSV cannot distinguish a missing text value from an empty string; JSON can. Opening raw post text in spreadsheet software can interpret leading `=`, `+`, `-`, or `@` as formulas; use pandas or import text columns explicitly as text.

## Validation scope

Tests exercise browser startup, navigation through an intercepted profile response, message expansion, permalink deduplication, nested-post exclusion, count/date parsing, login redirects, empty schemas, and Unicode/multiline export round trips. They do not prove that Facebook's live DOM matches these selectors. Before sentiment analysis, inspect a sample against the source and check `report.json` and warnings for coverage and missing fields.
