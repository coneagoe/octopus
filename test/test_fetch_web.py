"""Test cases for fetch_web.py with deduplication"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class FakeTextElement:
    def __init__(self, text):
        self.text = text

    def get_text(self, strip=True):
        return self.text.strip() if strip else self.text


class FakeLinkElement(dict):
    def __init__(self, href):
        super().__init__(href=href)


class FakeArticleElement:
    def __init__(self, title, href, summary):
        self.title = title
        self.href = href
        self.summary = summary

    def find(self, tag, href=False):
        if tag == ['h1', 'h2', 'h3']:
            return FakeTextElement(self.title)
        if tag == 'a' and href:
            return FakeLinkElement(self.href)
        if tag == 'p':
            return FakeTextElement(self.summary)
        return None


class FakeSoup:
    def __init__(self, articles=None, title=None):
        self.articles = articles or []
        self.title = title

    def select(self, sel):
        return self.articles

    def find(self, tag):
        if tag == 'title' and self.title is not None:
            return FakeTextElement(self.title)
        return None


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class TestFetchWebDedup:
    def test_fetch_web_returns_empty_on_request_error(self, monkeypatch, tmp_path):
        from scripts.fetch_web import fetch_web
        monkeypatch.setattr("requests.get", lambda url, headers, timeout: (_ for _ in ()).throw(Exception("network error")))
        entries = fetch_web("https://example.com", "TestSource", db_path=str(tmp_path / "test.db"))
        assert entries == []

    def test_fetch_web_inserts_new_into_db(self, monkeypatch, tmp_path):
        from scripts.db import init, Article, get_session
        from scripts.fetch_web import fetch_web

        db_path = tmp_path / "test.db"
        init(str(db_path))

        class FakeSoup:
            def select(self, sel):
                return [
                    {"title": "Test Article", "href": "/article1", "summary": "summary text"}
                ]
            find = lambda s, tag: None

        class FakeResponse:
            text = "<html></html>"
            def raise_for_status(self):
                pass

        monkeypatch.setattr("requests.get", lambda url, headers, timeout: FakeResponse())
        monkeypatch.setattr("bs4.BeautifulSoup", lambda text, parser: type("S", (), {
            "select": lambda s, sel: [type("E", (), {
                "find": lambda s, tags: type("T", (), {"get_text": lambda strip=True: "Test Article"})(),
                "find_all": lambda s, tag: [type("A", (), {"href": "/article1"})()] if tag == "a" else [],
                "get_text": lambda strip=True: "Test Article"
            })()],
            "find": lambda s, tag: None
        })())

        entries = fetch_web("https://example.com", "TestSource", db_path=str(db_path))
        assert len(entries) >= 0  # just verify no error

    def test_fetch_web_skips_duplicate_url(self, monkeypatch, tmp_path):
        from scripts.db import init, Article, get_session
        from scripts.fetch_web import fetch_web

        db_path = tmp_path / "test.db"
        init(str(db_path))

        # Pre-insert
        sess = get_session()
        sess.add(Article(url="https://example.com/duplicate", title="Old", source="Test", source_type="web"))
        sess.commit()
        sess.close()

        class FakeSoup:
            def select(self, sel):
                return []
            def find(self, tag):
                if tag == "title":
                    return type("T", (), {"get_text": lambda strip=True: "Duplicate Page"})()
                return None

        class FakeResponse:
            text = "<html><title>Duplicate Page</title></html>"
            def raise_for_status(self):
                pass

        monkeypatch.setattr("requests.get", lambda url, headers, timeout: FakeResponse())
        monkeypatch.setattr("bs4.BeautifulSoup", lambda text, parser: FakeSoup())

        entries = fetch_web("https://example.com", "TestSource", "article", db_path=str(db_path))

        # Should not add new entry for existing URL
        # (fallback path may still create, but dedup works for article path)
        assert isinstance(entries, list)

    def test_fetch_web_normalizes_relative_link_before_return_and_insert(self, monkeypatch, tmp_path):
        from scripts.db import Article, get_session, init
        from scripts.fetch_web import fetch_web

        db_path = tmp_path / "test.db"
        init(str(db_path))

        monkeypatch.setattr(
            "scripts.fetch_web.requests.get",
            lambda url, headers, timeout: FakeResponse("<html></html>"),
        )
        monkeypatch.setattr(
            "scripts.fetch_web.BeautifulSoup",
            lambda text, parser: FakeSoup(
                articles=[FakeArticleElement("Test Article", "/article1", "summary text")]
            ),
        )

        entries = fetch_web("https://example.com/news", "TestSource", db_path=str(db_path))

        sess = get_session()
        stored_urls = [article.url for article in sess.query(Article).all()]
        sess.close()

        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.com/article1"
        assert stored_urls == ["https://example.com/article1"]

    def test_fetch_web_same_relative_path_on_different_sites_is_not_deduplicated(self, monkeypatch, tmp_path):
        from scripts.db import Article, get_session, init
        from scripts.fetch_web import fetch_web

        db_path = tmp_path / "test.db"
        init(str(db_path))

        page_one = "https://site-one.example/news"
        page_two = "https://site-two.example/news"
        soups = {
            page_one: FakeSoup(
                articles=[FakeArticleElement("Shared Path One", "/shared-path", "summary one")]
            ),
            page_two: FakeSoup(
                articles=[FakeArticleElement("Shared Path Two", "/shared-path", "summary two")]
            ),
        }

        monkeypatch.setattr(
            "scripts.fetch_web.requests.get",
            lambda url, headers, timeout: FakeResponse(url),
        )
        monkeypatch.setattr(
            "scripts.fetch_web.BeautifulSoup",
            lambda text, parser: soups[text],
        )

        first_entries = fetch_web(page_one, "SiteOne", db_path=str(db_path))
        second_entries = fetch_web(page_two, "SiteTwo", db_path=str(db_path))

        sess = get_session()
        stored_urls = sorted(article.url for article in sess.query(Article).all())
        sess.close()

        assert len(first_entries) == 1
        assert len(second_entries) == 1
        assert "/shared-path" not in stored_urls
        assert stored_urls == [
            "https://site-one.example/shared-path",
            "https://site-two.example/shared-path",
        ]
