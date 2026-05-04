"""Test cases for fetch_feishu.py"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestFetchFeishu:
    def test_returns_empty_list_when_no_chat_ids(self, monkeypatch):
        from scripts import fetch_feishu
        monkeypatch.setattr(fetch_feishu, "load_config", lambda: {"sources": {"feishu": {"chat_ids": []}}})
        result = fetch_feishu.fetch_feishu()
        assert result == []

    def test_returns_empty_list_when_feishu_not_configured(self, monkeypatch):
        from scripts import fetch_feishu
        monkeypatch.setattr(fetch_feishu, "load_config", lambda: {"sources": {}})
        result = fetch_feishu.fetch_feishu()
        assert result == []