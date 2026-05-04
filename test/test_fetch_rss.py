"""Test cases for fetch_rss.py with deduplication"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestFetchRssDedup:
    def test_fetch_rss_returns_only_new_entries(self, monkeypatch, tmp_path):
        from scripts.db import Article, get_session, init
        from scripts.fetch_rss import fetch_rss
        from scripts.url_normalize import make_entry_hash, normalize_url

        db_path = tmp_path / "test.db"
        init(str(db_path))

        existing_raw_url = "https://example.com/existing?id=1&utm_source=old"
        duplicate_raw_url = "https://example.com/existing?utm_medium=new&id=1#section"
        new_raw_url = "https://example.com/new?id=2&utm_campaign=rss"

        sess = get_session()
        sess.add(Article(url=existing_raw_url, title="Old", source="Test", source_type="rss"))
        sess.commit()
        sess.close()

        fake_feed = type("F", (), {
            "entries": [
                {"title": "Existing", "link": duplicate_raw_url, "published": "2026-05-01", "summary": "old content"},
                {"title": "New Article", "link": new_raw_url, "published": "2026-05-04", "summary": "new content"},
            ]
        })()
        monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)

        entries = fetch_rss("https://example.com/rss", "TestSource", db_path=str(db_path))

        assert len(entries) == 1
        assert entries[0]["url"] == new_raw_url
        assert entries[0]["title"] == "New Article"
        assert entries[0]["normalized_url"] == "https://example.com/new?id=2"
        assert entries[0]["entry_hash"] == make_entry_hash(normalize_url(new_raw_url))

        sess = get_session()
        existing_article = sess.get(Article, make_entry_hash(normalize_url(existing_raw_url)))
        assert existing_article is not None
        assert existing_article.normalized_url == normalize_url(existing_raw_url)
        sess.close()

    def test_fetch_rss_inserts_new_entries_into_db(self, monkeypatch, tmp_path):
        from scripts.db import Article, get_session, init
        from scripts.fetch_rss import fetch_rss
        from scripts.url_normalize import make_entry_hash, normalize_url

        db_path = tmp_path / "test.db"
        init(str(db_path))

        raw_url = "https://example.com/brandnew?utm_source=feed&id=7#top"
        fake_feed = type("F", (), {
            "entries": [
                {"title": "Brand New", "link": raw_url, "published": "2026-05-04", "summary": "content"},
            ]
        })()
        monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)

        fetch_rss("https://example.com/rss", "TestSource", db_path=str(db_path))

        sess = get_session()
        article = sess.get(Article, make_entry_hash(normalize_url(raw_url)))
        assert article is not None
        assert article.title == "Brand New"
        assert article.source_type == "rss"
        assert article.url == raw_url
        assert article.normalized_url == "https://example.com/brandnew?id=7"
        sess.close()

    def test_fetch_rss_all_new_returns_all(self, monkeypatch, tmp_path):
        from scripts.db import init, get_session
        from scripts.fetch_rss import fetch_rss

        db_path = tmp_path / "test.db"
        init(str(db_path))

        fake_feed = type("F", (), {
            "entries": [
                {"title": f"Article {i}", "link": f"https://example.com/{i}", "published": "2026-05-04", "summary": ""}
                for i in range(5)
            ]
        })()
        monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)

        entries = fetch_rss("https://example.com/rss", "TestSource", db_path=str(db_path))
        assert len(entries) == 5

    def test_fetch_rss_empty_on_exception(self, monkeypatch, tmp_path):
        from scripts.fetch_rss import fetch_rss
        monkeypatch.setattr("feedparser.parse", lambda url: (_ for _ in ()).throw(Exception("network error")))
        entries = fetch_rss("https://example.com/rss", "TestSource", db_path=str(tmp_path / "test.db"))
        assert entries == []

    def test_fetch_rss_inserts_naive_utc_timestamps(self, monkeypatch, tmp_path):
        from scripts.fetch_rss import fetch_rss

        created_articles = []

        class FakeArticle:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                created_articles.append(self)

        class FakeSession:
            def get(self, model, entry_hash):
                return None

            def add(self, article):
                self.article = article

            def commit(self):
                return None

            def close(self):
                return None

        fake_feed = type("F", (), {
            "entries": [
                {"title": "Brand New", "link": "https://example.com/brandnew", "published": "2026-05-04", "summary": "content"},
            ]
        })()
        monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)
        monkeypatch.setattr("scripts.fetch_rss.init", lambda db_path: None)
        monkeypatch.setattr("scripts.fetch_rss.get_session", lambda: FakeSession())
        monkeypatch.setattr("scripts.fetch_rss.Article", FakeArticle)

        entries = fetch_rss("https://example.com/rss", "TestSource", db_path=str(tmp_path / "test.db"))

        assert len(entries) == 1
        assert len(created_articles) == 1
        assert created_articles[0].author == ""
        assert created_articles[0].first_fetched.tzinfo is None
        assert created_articles[0].last_seen.tzinfo is None
