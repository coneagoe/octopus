"""Test cases for fetch_zhihu.py"""

import pytest
import sys
import os

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