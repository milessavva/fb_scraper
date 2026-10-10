import pytest

from fb_scraper.parsing import parse_count, parse_timestamp, post_identity, profile_url


@pytest.mark.parametrize("raw, expected", [("1,234 comments", 1234), ("All reactions: 1.2K", 1200), ("0 comments", 0), ("2M reactions", 2000000), (None, None), ("Like", None)])
def test_counts(raw, expected):
    assert parse_count(raw) == expected


@pytest.mark.parametrize("raw", ["2h", "Yesterday", "January 2, 2024", None])
def test_incomplete_dates_are_not_invented(raw):
    assert parse_timestamp(raw) is None


def test_dates():
    assert parse_timestamp("2024-01-02T03:04:05Z") == "2024-01-02T03:04:05+00:00"
    assert parse_timestamp("Tuesday, January 2, 2024 at 3:04 PM") == "2024-01-02T15:04:00"
    assert parse_timestamp("1704164645") == "2024-01-02T03:04:05+00:00"


@pytest.mark.parametrize("url", ["http://www.facebook.com/alice", "https://evil.test/alice", "https://www.facebook.com/groups/123", "https://www.facebook.com/marketplace", "https://www.facebook.com/profile.php", "https://www.facebook.com/alice/posts/1"])
def test_invalid_profiles(url):
    with pytest.raises(ValueError):
        profile_url(url)


def test_urls():
    assert profile_url("https://m.facebook.com/profile.php?id=123&tracking=x") == "https://www.facebook.com/profile.php?id=123"
    assert post_identity("https://www.facebook.com/alice/posts/pfbidABC?tracking=x") == ("pfbidABC", "https://www.facebook.com/alice/posts/pfbidABC")
    assert post_identity("https://www.facebook.com/story.php?story_fbid=45&id=123&tracking=x") == ("45", "https://www.facebook.com/story.php?story_fbid=45&id=123")
    assert post_identity("https://evil.test/alice/posts/123") is None
