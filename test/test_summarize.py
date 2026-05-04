"""Test cases for summarize.py"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts import summarize


class TestStripHtml:
    def test_strips_basic_html_tags(self, monkeypatch):
        assert summarize.strip_html("<p>hello</p>") == "hello"

    def test_strips_html_entities(self, monkeypatch):
        # &lt; becomes space, then whitespace collapse removes it -> empty in the middle
        assert summarize.strip_html("&lt;tag&gt;") == "tag"
        assert summarize.strip_html("&nbsp;hello&nbsp;") == "hello"

    def test_removes_promotional_trailer(self, monkeypatch):
        assert summarize.strip_html("some text\n#欢迎关注微信abc") == "some text"

    def test_collapse_whitespace(self, monkeypatch):
        assert summarize.strip_html("a   b\t\nc") == "a b c"

    def test_empty_input(self, monkeypatch):
        assert summarize.strip_html("") == ""
        assert summarize.strip_html(None) == ""


class TestLoadCache:
    def test_returns_empty_list_when_file_missing(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        result = summarize.load_cache("rss")
        assert result == []

    def test_returns_parsed_json_when_file_exists(self, monkeypatch):
        fake_entries = [{'title': 'test'}]
        fake_file = type("F", (), {"read.return_value": '{"test": 1}', "__enter__": lambda s: s, "__exit__": lambda *a: None})()
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        monkeypatch.setattr("builtins.open", lambda p, mode=None, encoding=None: fake_file)
        monkeypatch.setattr("json.load", lambda f: fake_entries)
        result = summarize.load_cache("rss")
        assert result == fake_entries


class TestGenerateCommentary:
    def test_returns_commentary_on_success(self, monkeypatch):
        fake_resp = {
            "choices": [{"message": {"content": "【利多】这是测试点评"}}]
        }
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return fake_resp
        monkeypatch.setattr("requests.post", lambda *a, **kw: FakeResp())
        result = summarize.generate_commentary("标题", "摘要", "来源", "fake-key")
        assert result == "【利多】这是测试点评"

    def test_returns_fallback_on_error(self, monkeypatch):
        monkeypatch.setattr("requests.post", lambda *a, **kw: (_ for _ in ()).throw(Exception("fail")))
        result = summarize.generate_commentary("标题", "摘要", "来源", "fake-key")
        assert result == "（AI 点评生成失败）"