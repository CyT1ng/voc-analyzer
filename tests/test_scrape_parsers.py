from datetime import UTC, datetime
from pathlib import Path

from voc_analyzer.scrape import reddit, youtube
from voc_analyzer.scrape._browser import parse_count, relative_time, stable_id

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_youtube_parse_extracts_comments():
    html = (SAMPLES / "youtube_comments.html").read_text(encoding="utf-8")
    comments = youtube.parse(html, "https://youtube.com/watch?v=abc")
    # the third comment has empty text and is skipped
    assert len(comments) == 2
    first = comments[0]
    assert first.source == "youtube"
    assert first.author == "@user_one"
    assert first.likes == 1200
    assert "amazing" in first.text


def test_reddit_parse_extracts_comments():
    html = (SAMPLES / "reddit_comments.html").read_text(encoding="utf-8")
    comments = reddit.parse(html)
    # the [deleted] comment is skipped
    assert len(comments) == 2
    first = comments[0]
    assert first.source_id == "t1_aaa"
    assert first.author == "redditor1"
    assert first.likes == 84
    assert first.timestamp.year == 2026
    assert first.url.startswith("https://old.reddit.com/")


def test_parse_count_handles_suffixes():
    assert parse_count("1.2K") == 1200
    assert parse_count("3,400") == 3400
    assert parse_count("5 likes") == 5
    assert parse_count(None) is None


def test_relative_time_subtracts_from_now():
    now = datetime(2026, 5, 10, tzinfo=UTC)
    assert relative_time("3 days ago", now).date().isoformat() == "2026-05-07"
    assert relative_time("nonsense", now) == now


def test_stable_id_is_deterministic():
    assert stable_id("a", "b") == stable_id("a", "b")
    assert stable_id("a", "b") != stable_id("a", "c")
