"""Test cases for fetch_email.py"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestDecodeStr:
    def test_returns_empty_string_for_none(self, monkeypatch):
        from scripts import fetch_email
        assert fetch_email.decode_str(None) == ""

    def test_returns_empty_string_for_empty(self, monkeypatch):
        from scripts import fetch_email
        assert fetch_email.decode_str("") == ""

    def test_passthrough_plain_string(self, monkeypatch):
        from scripts import fetch_email
        assert fetch_email.decode_str("hello") == "hello"


class TestFetchEmail:
    def test_returns_empty_list_when_email_not_configured(self, monkeypatch):
        from scripts import fetch_email
        monkeypatch.setattr(fetch_email, "load_config", lambda: {"sources": {}})
        result = fetch_email.fetch_email()
        assert result == []

    def test_returns_empty_list_when_imap_unavailable(self, monkeypatch):
        from scripts import fetch_email
        monkeypatch.setattr(fetch_email, "load_config", lambda: {
            "sources": {"email": {"imap": "imap.example.com", "username": "user", "password": "pass"}}
        })
        monkeypatch.setattr("imaplib.IMAP4_SSL", lambda host: (_ for _ in ()).throw(Exception("connection refused")))
        result = fetch_email.fetch_email()
        assert result == []