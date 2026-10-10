import csv
import json
from pathlib import Path

import pandas as pd

COLUMNS = ["post_id", "profile_url", "post_url", "timestamp", "date", "time", "text", "reaction_count", "comment_count", "reaction_count_raw", "comment_count_raw", "timestamp_raw", "collected_at", "warnings"]


def to_dataframe(posts: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(posts, columns=COLUMNS)
    for column in ("reaction_count", "comment_count"):
        frame[column] = pd.array(frame[column], dtype="Int64")
    return frame


def write_exports(posts: list[dict], report: dict, directory: str | Path) -> None:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    frame = to_dataframe(posts)
    frame["warnings"] = frame["warnings"].map(json.dumps)
    frame.to_csv(target / "posts.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_ALL, lineterminator="\n")
    (target / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def load_posts(path: str | Path) -> pd.DataFrame:
    """Load either format without converting text such as 'NA' into null."""
    source = Path(path)
    if source.suffix == ".json":
        return to_dataframe(json.loads(source.read_text(encoding="utf-8")))
    frame = pd.read_csv(source, dtype=str, keep_default_na=False, encoding="utf-8")
    for column in ("reaction_count", "comment_count"):
        frame[column] = pd.array([int(value) if value else None for value in frame[column]], dtype="Int64")
    frame["warnings"] = frame["warnings"].map(json.loads)
    return frame
