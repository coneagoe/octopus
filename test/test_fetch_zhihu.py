"""Test cases for fetch_zhihu.py"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestExtractAnswerItems:
    def test_extracts_answer_items_from_html(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">测试问题标题</a>
            <span class="AnswerItem-time">2026-05-04</span>
            <p class="AnswerItem-summary">这是回答摘要内容</p>
        </div>
        """
        items = _extract_answer_items(fake_html, "2026-05-04")
        assert len(items) == 1
        assert items[0]["title"] == "测试问题标题"
        assert items[0]["url"] == "https://www.zhihu.com/question/123/answer/456"
        assert items[0]["published"] == "2026-05-04"

    def test_filters_out_non_today_answers(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">今天的问题</a>
            <span class="AnswerItem-time">2026-05-04</span>
        </div>
        <div class="List-item">
            <a href="/question/789/answer/012">昨天的问题</a>
            <span class="AnswerItem-time">2026-05-03</span>
        </div>
        """
        items = _extract_answer_items(fake_html, "2026-05-04")
        assert len(items) == 1
        assert "今天的问题" in items[0]["title"]

    def test_handles_empty_html(self):
        from scripts.fetch_zhihu import _extract_answer_items
        items = _extract_answer_items("", "2026-05-04")
        assert items == []

    def test_handles_no_matching_items(self):
        from scripts.fetch_zhihu import _extract_answer_items
        fake_html = "<div>no content here</div>"
        items = _extract_answer_items(fake_html, "2026-05-04")
        assert items == []

    def test_extracts_multiple_today_answers(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/1/answer/1">问题A</a>
            <span class="AnswerItem-time">2026-05-04</span>
            <p class="AnswerItem-summary">摘要A</p>
        </div>
        <div class="List-item">
            <a href="/question/2/answer/2">问题B</a>
            <span class="AnswerItem-time">2026-05-04</span>
            <p class="AnswerItem-summary">摘要B</p>
        </div>
        """
        items = _extract_answer_items(fake_html, "2026-05-04")
        assert len(items) == 2

    def test_treats_relative_time_answers_as_today(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">刚刚的问题</a>
            <span class="AnswerItem-time">刚刚</span>
            <p class="AnswerItem-summary">这是刚刚发布的回答</p>
        </div>
        <div class="List-item">
            <a href="/question/789/answer/012">三小时前的问题</a>
            <span class="AnswerItem-time">3 小时前</span>
            <p class="AnswerItem-summary">这是三小时前发布的回答</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04")

        assert len(items) == 2
        assert items[0]["published"] == "2026-05-04"
        assert items[1]["published"] == "2026-05-04"

    def test_treats_minutes_ago_answers_as_today(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">十分钟前的问题</a>
            <span class="AnswerItem-time">10 分钟前</span>
            <p class="AnswerItem-summary">这是十分钟前发布的回答</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04")

        assert len(items) == 1
        assert items[0]["published"] == "2026-05-04"

    def test_treats_today_clock_time_answers_as_today(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">今天时间的问题</a>
            <span class="AnswerItem-time">今天 15:30</span>
            <p class="AnswerItem-summary">这是今天下午发布的回答</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04")

        assert len(items) == 1
        assert items[0]["published"] == "2026-05-04"

    def test_filters_out_yesterday_relative_answers(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">昨天的问题</a>
            <span class="AnswerItem-time">昨天 15:30</span>
            <p class="AnswerItem-summary">这是昨天的回答</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04")

        assert items == []

    def test_uses_configured_source_name_for_cache_entries(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">来源测试</a>
            <span class="AnswerItem-time">刚刚</span>
            <p class="AnswerItem-summary">测试摘要</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04", source_name="Deep Van")

        assert len(items) == 1
        assert items[0]["source"] == "Deep Van"

    def test_preserves_summary_text_that_contains_today_word(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">摘要保留测试</a>
            <span class="AnswerItem-time">刚刚</span>
            <p class="AnswerItem-summary">今天市场有变化</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04")

        assert len(items) == 1
        assert items[0]["summary"] == "今天市场有变化"

    def test_does_not_treat_summary_yesterday_word_as_timestamp(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">污染测试</a>
            <span class="AnswerItem-time">刚刚</span>
            <p class="AnswerItem-summary">我昨天还在想这个问题</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04")

        assert len(items) == 1
        assert items[0]["published"] == "2026-05-04"

    def test_requires_timestamp_element_instead_of_summary_keywords(self):
        from scripts.fetch_zhihu import _extract_answer_items

        fake_html = """
        <div class="List-item">
            <a href="/question/123/answer/456">缺时间测试</a>
            <p class="AnswerItem-summary">今天市场有变化</p>
        </div>
        """

        items = _extract_answer_items(fake_html, "2026-05-04")

        assert items == []


class TestFetchZhihuRuntime:
    def test_fetch_zhihu_user_raises_when_browser_missing(self, monkeypatch):
        from scripts import fetch_zhihu

        monkeypatch.setattr(
            fetch_zhihu,
            "is_chromium_ready",
            lambda: (
                False,
                "Chromium 浏览器未安装，请先执行：uv run python scripts/playwright_setup.py --install-if-missing",
            ),
        )

        with pytest.raises(fetch_zhihu.FetchZhihuError, match="Chromium 浏览器未安装"):
            fetch_zhihu.fetch_zhihu_user("demo-user", "Demo")

    def test_main_writes_empty_cache_when_browser_missing(self, monkeypatch, tmp_path):
        from scripts import fetch_zhihu

        fake_scripts_dir = tmp_path / "scripts"
        fake_scripts_dir.mkdir()

        monkeypatch.setattr(
            fetch_zhihu,
            "load_config",
            lambda: {"sources": {"zhihu": [{"user_id": "demo-user", "name": "Demo"}]}},
        )
        monkeypatch.setattr(
            fetch_zhihu,
            "fetch_zhihu_user",
            lambda user_id, name, db_path=None: (_ for _ in ()).throw(
                fetch_zhihu.FetchZhihuError("Chromium 浏览器未安装，请先执行 setup")
            ),
        )
        monkeypatch.setattr(fetch_zhihu, "__file__", str(fake_scripts_dir / "fetch_zhihu.py"))

        with pytest.raises(SystemExit, match="1"):
            fetch_zhihu.main()

        cache_path = tmp_path / "output" / "zhihu_cache.json"
        assert json.loads(cache_path.read_text(encoding="utf-8")) == []

    def test_main_keeps_partial_results_and_exits_nonzero_when_one_user_fails(self, monkeypatch, tmp_path):
        from scripts import fetch_zhihu

        fake_scripts_dir = tmp_path / "scripts"
        fake_scripts_dir.mkdir()

        monkeypatch.setattr(
            fetch_zhihu,
            "load_config",
            lambda: {
                "sources": {
                    "zhihu": [
                        {"user_id": "ok-user", "name": "OK"},
                        {"user_id": "bad-user", "name": "BAD"},
                    ]
                }
            },
        )

        def fake_fetch(user_id, name, db_path=None):
            if user_id == "bad-user":
                raise fetch_zhihu.FetchZhihuError("bad user")
            return [
                {
                    "title": "保留条目",
                    "url": "https://www.zhihu.com/question/1/answer/1",
                    "published": "2026-05-05",
                    "summary": "摘要",
                    "source": name,
                    "source_type": "zhihu",
                }
            ]

        monkeypatch.setattr(fetch_zhihu, "fetch_zhihu_user", fake_fetch)
        monkeypatch.setattr(fetch_zhihu, "__file__", str(fake_scripts_dir / "fetch_zhihu.py"))

        with pytest.raises(SystemExit, match="1"):
            fetch_zhihu.main()

        cache_path = tmp_path / "output" / "zhihu_cache.json"
        assert json.loads(cache_path.read_text(encoding="utf-8")) == [
            {
                "title": "保留条目",
                "url": "https://www.zhihu.com/question/1/answer/1",
                "published": "2026-05-05",
                "summary": "摘要",
                "source": "OK",
                "source_type": "zhihu",
            }
        ]

    def test_main_overwrites_stale_cache_with_empty_list_when_no_new_entries(self, monkeypatch, tmp_path):
        from scripts import fetch_zhihu

        fake_scripts_dir = tmp_path / "scripts"
        fake_scripts_dir.mkdir()
        cache_dir = tmp_path / "output"
        cache_dir.mkdir()
        cache_path = cache_dir / "zhihu_cache.json"
        cache_path.write_text(
            json.dumps([{"title": "旧条目"}], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            fetch_zhihu,
            "load_config",
            lambda: {"sources": {"zhihu": [{"user_id": "demo-user", "name": "Demo"}]}},
        )
        monkeypatch.setattr(fetch_zhihu, "fetch_zhihu_user", lambda user_id, name, db_path=None: [])
        monkeypatch.setattr(fetch_zhihu, "__file__", str(fake_scripts_dir / "fetch_zhihu.py"))

        fetch_zhihu.main()

        assert json.loads(cache_path.read_text(encoding="utf-8")) == []

    def test_fetch_zhihu_user_closes_session_when_db_write_fails(self, monkeypatch):
        from scripts import fetch_zhihu

        class FakeSession:
            def __init__(self):
                self.closed = False

            def get(self, model, entry_hash):
                raise RuntimeError("db read failed")

            def close(self):
                self.closed = True

        session = FakeSession()

        async def fake_fetch_page_content(url):
            return "<html></html>"

        monkeypatch.setattr(fetch_zhihu, "is_chromium_ready", lambda: (True, ""))
        monkeypatch.setattr(fetch_zhihu, "_fetch_page_content", fake_fetch_page_content)
        monkeypatch.setattr(
            fetch_zhihu,
            "_extract_answer_items",
            lambda html, today, source_name="zhihu": [
                {
                    "title": "问题",
                    "url": "https://www.zhihu.com/question/1/answer/1",
                    "published": today,
                    "summary": "摘要",
                    "source": source_name,
                    "source_type": "zhihu",
                }
            ],
        )
        monkeypatch.setattr(fetch_zhihu, "init", lambda db_path: None)
        monkeypatch.setattr(fetch_zhihu, "get_session", lambda: session)

        with pytest.raises(RuntimeError, match="db read failed"):
            fetch_zhihu.fetch_zhihu_user("demo-user", "Demo", db_path="test.db")

        assert session.closed is True
