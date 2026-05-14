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


class TestGenerateMarkdown:
    def test_renders_non_empty_zhihu_entries_with_commentary_and_total(self, monkeypatch):
        monkeypatch.setattr(
            summarize,
            "generate_commentary",
            lambda title, summary, source, api_key: "【利多】知乎点评",
        )

        md = summarize.generate_markdown(
            "2026-05-13",
            {
                "rss": [],
                "zhihu": [
                    {
                        "title": "知乎热议",
                        "url": "https://www.zhihu.com/question/1",
                        "source": "知乎",
                        "summary": "<p>这是回答摘要</p>",
                    }
                ],
                "web": [],
                "feishu": [],
                "email": [],
            },
            "fake-key",
            zhihu_fetch_succeeded=True,
        )

        assert "## 知乎回答" in md
        assert "### [知乎热议](https://www.zhihu.com/question/1)" in md
        assert "- 摘要: 这是回答摘要" in md
        assert "- 点评: 【利多】知乎点评" in md
        assert "_知乎 0条_" not in md
        assert "共 1 条内容" in md

    def test_includes_zhihu_zero_count_when_fetch_succeeded_with_no_entries(self, monkeypatch):
        monkeypatch.setattr(
            summarize,
            "generate_commentary",
            lambda title, summary, source, api_key: "不会被调用",
        )

        md = summarize.generate_markdown(
            "2026-05-13",
            {
                "rss": [],
                "zhihu": [],
                "web": [],
                "feishu": [],
                "email": [],
            },
            "fake-key",
            zhihu_fetch_succeeded=True,
        )

        assert "## 知乎回答" in md
        assert "_知乎 0条_" in md
        assert "_今日无新内容_" in md
        assert "共 0 条内容" in md

    def test_omits_zhihu_section_when_fetch_did_not_succeed(self, monkeypatch):
        monkeypatch.setattr(
            summarize,
            "generate_commentary",
            lambda title, summary, source, api_key: "不会被调用",
        )

        md = summarize.generate_markdown(
            "2026-05-13",
            {
                "rss": [],
                "zhihu": [],
                "web": [],
                "feishu": [],
                "email": [],
            },
            "fake-key",
            zhihu_fetch_succeeded=False,
        )

        assert "## 知乎回答" not in md
        assert "_知乎 0条_" not in md
        assert "_今日无新内容_" in md
        assert "共 0 条内容" in md


class TestMainZhihuStatus:
    def test_main_passes_false_when_zhihu_cache_file_is_missing(self, monkeypatch, tmp_path):
        output_path = tmp_path / "daily.md"
        fake_scripts_dir = tmp_path / "scripts"
        fake_scripts_dir.mkdir()

        monkeypatch.setattr(summarize, "__file__", str(fake_scripts_dir / "summarize.py"))
        monkeypatch.setenv("MINIMAX_API_KEY", "fake-key")
        monkeypatch.setattr(
            sys,
            "argv",
            ["summarize.py", "--date", "2026-05-13", "--output", str(output_path)],
        )

        monkeypatch.setattr(summarize, "load_cache", lambda category: [])
        monkeypatch.setattr(os.path, "exists", lambda path: False)

        captured = {}

        def fake_generate_markdown(date, entries_by_source, api_key, zhihu_fetch_succeeded):
            captured["zhihu_fetch_succeeded"] = zhihu_fetch_succeeded
            return "stub markdown"

        monkeypatch.setattr(summarize, "generate_markdown", fake_generate_markdown)

        summarize.main()

        assert captured["zhihu_fetch_succeeded"] is False
        assert output_path.read_text(encoding="utf-8") == "stub markdown"

    def test_main_normalizes_non_list_zhihu_cache_payload(self, monkeypatch, tmp_path):
        output_path = tmp_path / "daily.md"
        fake_scripts_dir = tmp_path / "scripts"
        fake_scripts_dir.mkdir()

        monkeypatch.setattr(summarize, "__file__", str(fake_scripts_dir / "summarize.py"))
        monkeypatch.setenv("MINIMAX_API_KEY", "fake-key")
        monkeypatch.setattr(
            sys,
            "argv",
            ["summarize.py", "--date", "2026-05-13", "--output", str(output_path)],
        )

        def fake_load_cache(category):
            if category == "zhihu":
                return {"title": "bad payload"}
            return []

        monkeypatch.setattr(summarize, "load_cache", fake_load_cache)
        monkeypatch.setattr(os.path, "exists", lambda path: path == summarize.get_cache_path("zhihu"))

        captured = {}

        def fake_generate_markdown(date, entries_by_source, api_key, zhihu_fetch_succeeded):
            captured["entries_by_source"] = entries_by_source
            captured["zhihu_fetch_succeeded"] = zhihu_fetch_succeeded
            return "stub markdown"

        monkeypatch.setattr(summarize, "generate_markdown", fake_generate_markdown)

        summarize.main()

        assert captured["zhihu_fetch_succeeded"] is False
        assert captured["entries_by_source"]["zhihu"] == []
        assert output_path.read_text(encoding="utf-8") == "stub markdown"

    def test_main_normalizes_non_list_rss_cache_payload(self, monkeypatch, tmp_path, capsys):
        output_path = tmp_path / "daily.md"
        fake_scripts_dir = tmp_path / "scripts"
        fake_scripts_dir.mkdir()

        monkeypatch.setattr(summarize, "__file__", str(fake_scripts_dir / "summarize.py"))
        monkeypatch.setenv("MINIMAX_API_KEY", "fake-key")
        monkeypatch.setattr(
            sys,
            "argv",
            ["summarize.py", "--date", "2026-05-13", "--output", str(output_path)],
        )

        def fake_load_cache(category):
            if category == "rss":
                return {"title": "bad payload"}
            return []

        monkeypatch.setattr(summarize, "load_cache", fake_load_cache)
        monkeypatch.setattr(
            summarize,
            "generate_commentary",
            lambda *args, **kwargs: pytest.fail("不应为畸形 RSS 载荷生成点评"),
        )

        real_exists = os.path.exists
        monkeypatch.setattr(
            os.path,
            "exists",
            lambda path: False if path == summarize.get_cache_path("zhihu") else real_exists(path),
        )

        summarize.main()

        captured = capsys.readouterr()
        assert "RSS: 0 条" in captured.out
        assert output_path.read_text(encoding="utf-8").startswith("# 信息聚合日报 2026-05-13")
        assert "_今日无新内容_" in output_path.read_text(encoding="utf-8")
