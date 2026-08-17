from src.scraper.main import dedupe_by_url
from src.scraper.sources.base import RawPosting


def test_dedupe_removes_duplicate_urls():
    postings = [
        RawPosting(source="a", url="https://x.com/1", title="First"),
        RawPosting(source="b", url="https://x.com/1", title="Duplicate"),
        RawPosting(source="a", url="https://x.com/2", title="Unique"),
    ]
    result = dedupe_by_url(postings)
    assert len(result) == 2
    urls = {p.url for p in result}
    assert urls == {"https://x.com/1", "https://x.com/2"}


def test_dedupe_empty_list():
    assert dedupe_by_url([]) == []
