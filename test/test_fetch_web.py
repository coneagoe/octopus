"""Test cases for fetch_web.py"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestFetchWeb:
    def test_fetch_web_returns_empty_on_request_error(self, monkeypatch):
        from scripts import fetch_web
        monkeypatch.setattr("requests.get", lambda url, headers, timeout: (_ for _ in ()).throw(Exception("network error")))
        entries = fetch_web.fetch_web("https://example.com", "TestSource")
        assert entries == []

    def test_fetch_web_returns_empty_on_beautifulsoup_error(self, monkeypatch):
        """Test fallback when BeautifulSoup parsing fails."""
        from scripts import fetch_web

        class FakeResponse:
            text = "<html></html>"
            def raise_for_status(self):
                pass

        def fake_bs_parse(html, parser):
            raise Exception("parsing failed")

        monkeypatch.setattr("requests.get", lambda url, headers, timeout: FakeResponse())
        monkeypatch.setattr("bs4.BeautifulSoup", fake_bs_parse)

        entries = fetch_web.fetch_web("https://example.com", "TestSource", "article")
        assert entries == []