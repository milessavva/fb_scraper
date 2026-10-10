import json

import pandas as pd

from fb_scraper.export import load_posts, to_dataframe, write_exports
from fb_scraper.scraper import normalize


def test_unicode_and_multiline_round_trip(tmp_path):
    texts = ['Comma, quote "hello"\nNew line\r\nEmoji 😊 café 漢字', "NA", "", "=SUM(A1:A2)"]
    posts = [normalize({"url": f"https://www.facebook.com/alice/posts/{i}", "text": text, "reaction_raw": "0 reactions", "comment_raw": None}, "https://www.facebook.com/alice") for i, text in enumerate(texts)]
    write_exports(posts, {"complete": False}, tmp_path)
    for name in ("posts.json", "posts.csv"):
        frame = load_posts(tmp_path / name)
        assert frame.text.tolist() == texts
        assert frame.post_id.tolist() == [str(i) for i in range(4)]
        assert frame.reaction_count.tolist() == [0] * 4
        assert frame.comment_count.isna().all()
    assert json.loads((tmp_path / "report.json").read_text())["complete"] is False


def test_empty_export_has_schema(tmp_path):
    write_exports([], {"posts_collected": 0}, tmp_path)
    assert load_posts(tmp_path / "posts.csv").empty
    assert to_dataframe([]).reaction_count.dtype == pd.Int64Dtype()
