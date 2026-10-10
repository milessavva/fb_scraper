import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse, urlunparse

from dateutil.parser import parse


def profile_url(value: str) -> str:
    url = urlparse(value)
    if url.scheme != "https" or url.hostname not in {"facebook.com", "www.facebook.com", "m.facebook.com"} or url.username or url.password:
        raise ValueError("Use an HTTPS facebook.com personal-profile URL.")
    path = url.path.strip("/")
    if not path or path.split("/")[0] in {"groups", "marketplace", "pages", "watch", "reel", "reels", "login", "posts", "photo", "story.php"}:
        raise ValueError("Expected a personal-profile URL, not a feed or post URL.")
    if path == "profile.php" and not parse_qs(url.query).get("id", [""])[0].isdigit():
        raise ValueError("profile.php requires a numeric id.")
    if path != "profile.php" and "/" in path:
        raise ValueError("Use the profile root URL.")
    query = "id=" + parse_qs(url.query)["id"][0] if path == "profile.php" else ""
    return urlunparse(("https", "www.facebook.com", "/" + path, "", query, ""))


def post_identity(value: str) -> tuple[str, str] | None:
    url = urlparse(value)
    if url.hostname not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return None
    match = re.search(r"/posts/([^/?]+)", url.path)
    query = parse_qs(url.query)
    post_id = match.group(1) if match else query.get("story_fbid", [None])[0]
    if not post_id:
        return None
    clean_query = ""
    if not match:
        clean_query = "story_fbid=" + post_id
        if query.get("id"):
            clean_query += "&id=" + query["id"][0]
    return post_id, urlunparse(("https", "www.facebook.com", url.path, "", clean_query, ""))


def parse_count(value: str | None) -> int | None:
    if not value:
        return None
    # The browser is explicitly configured for English labels. Rounded K/M
    # counts remain estimates; retain the source labels alongside the numbers.
    match = re.search(r"(?<![\w.])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*([KMB])?\b", value, re.I)
    if not match:
        return None
    multiplier = {None: 1, "K": 1000, "M": 1000000, "B": 1000000000}[match.group(2).upper() if match.group(2) else None]
    return round(float(match.group(1).replace(",", "")) * multiplier)


def parse_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{10}", value):
            return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
        if re.match(r"^\d{4}-\d{2}-\d{2}T", value):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        # Relative labels and date-only labels cannot establish a post time.
        if not re.search(r"\b\d{4}\b", value) or not re.search(r"\d{1,2}:\d{2}", value):
            return None
        if not re.search(r"January|February|March|April|May|June|July|August|September|October|November|December", value, re.I):
            return None
        return parse(value, fuzzy=True).isoformat()
    except (ValueError, OverflowError):
        return None
