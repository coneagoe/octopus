"""Test cases for fetch_rss.py"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestFetchRss:
    def test_fetch_rss_returns_entries_on_success(self, monkeypatch):
        from scripts import fetch_rss

        fake_feed = type("F", (), {
            "entries": [
                {
                    "title": "Test Article",
                    "link": "https://example.com/article",
                    "published": "2026-05-01",
                    "summary": "This is a test summary"
                }
            ]
        })()
        monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)

        entries = fetch_rss.fetch_rss("https://example.com/rss", "TestSource")
        assert len(entries) == 1
        assert entries[0]["title"] == "Test Article"
        assert entries[0]["source"] == "TestSource"
        assert entries[0]["source_type"] == "rss"
        assert entries[0]["url"] == "https://example.com/article"

    def test_fetch_rss_returns_empty_on_error(self, monkeypatch):
        from scripts import fetch_rss
        monkeypatch.setattr("feedparser.parse", lambda url: (_ for _ in ()).throw(Exception("network error")))
        entries = fetch_rss.fetch_rss("https://example.com/rss", "TestSource")
        assert entries == []