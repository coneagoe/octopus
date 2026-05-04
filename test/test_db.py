"""Test cases for scripts/db.py"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestArticleModel:
    def test_article_tablename_is_articles(self):
        from scripts.db import Article
        assert Article.__tablename__ == 'articles'

    def test_article_has_url_as_primary_key(self):
        from scripts.db import Article
        url_col = Article.__table__.columns['url']
        assert url_col.primary_key

    def test_article_has_expected_columns(self):
        from scripts.db import Article
        cols = {c.name for c in Article.__table__.columns}
        required = {'url', 'title', 'source', 'source_type', 'published', 'summary', 'first_fetched', 'last_seen'}
        assert required.issubset(cols), f"missing: {required - cols}"


class TestDailyEntryModel:
    def test_daily_entry_tablename_is_daily_entries(self):
        from scripts.db import DailyEntry
        assert DailyEntry.__tablename__ == 'daily_entries'

    def test_daily_entry_has_date_and_url_pk(self):
        from scripts.db import DailyEntry
        cols = DailyEntry.__table__.columns
        assert 'date' in cols and 'url' in cols


class TestDbSession:
    def test_get_session_returns_session_with_article_table(self, tmp_path):
        from scripts.db import init, get_session
        db_path = tmp_path / "test.db"
        init(str(db_path))
        sess = get_session()
        from sqlalchemy import text
        result = sess.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"))
        assert result.fetchone() is not None
        sess.close()

    def test_init_creates_tables(self, tmp_path):
        from scripts.db import init, get_session
        db_path = tmp_path / "test.db"
        init(str(db_path))
        sess = get_session()
        from sqlalchemy import text
        r1 = sess.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"))
        r2 = sess.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_entries'"))
        assert r1.fetchone() is not None
        assert r2.fetchone() is not None
        sess.close()