"""Test cases for scripts/migrate.py"""

import pytest
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestMigrateFromJson:
    def test_load_cache_json_returns_list(self, tmp_path):
        cache = tmp_path / "rss_cache.json"
        cache.write_text(json.dumps([{"title": "t", "url": "u", "source": "s", "summary": "", "published": ""}]))
        from scripts.migrate import load_cache_json
        result = load_cache_json(str(cache))
        assert isinstance(result, list)
        assert len(result) == 1

    def test_load_cache_json_returns_empty_on_missing_file(self):
        from scripts.migrate import load_cache_json
        result = load_cache_json("/nonexistent/path.json")
        assert result == []

    def test_migrate_entries_inserts_all_into_db(self, tmp_path, monkeypatch):
        from scripts.db import init, get_session, Article
        from scripts.migrate import migrate_entries

        db_path = tmp_path / "test.db"
        init(str(db_path))

        entries = [
            {"title": "A", "url": "https://a.com", "source": "src", "summary": "", "published": "", "source_type": "rss"}
        ]
        count = migrate_entries(entries, str(db_path))
        assert count == 1

        sess = get_session()
        articles = sess.query(Article).all()
        assert len(articles) == 1
        assert articles[0].url == "https://a.com"
        sess.close()

    def test_migrate_entries_skips_duplicates(self, tmp_path, monkeypatch):
        from scripts.db import init, get_session, Article
        from scripts.migrate import migrate_entries

        db_path = tmp_path / "test.db"
        init(str(db_path))

        # Pre-insert
        sess = get_session()
        sess.add(Article(url="https://a.com", title="Old", source="src", source_type="rss"))
        sess.commit()
        sess.close()

        entries = [
            {"title": "A", "url": "https://a.com", "source": "src", "summary": "", "published": "", "source_type": "rss"}
        ]
        count = migrate_entries(entries, str(db_path))
        assert count == 0  # duplicate skipped

    def test_migrate_from_output_dir_migrates_all_caches(self, tmp_path, monkeypatch):
        """Integration test: migrate all existing JSON caches to DB"""
        from scripts.db import init, get_session, Article
        from scripts.migrate import migrate_from_output_dir

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Write fake RSS cache
        rss_cache = output_dir / "rss_cache.json"
        rss_cache.write_text(json.dumps([
            {"title": "A", "url": "https://a.com", "source": "SrcA", "summary": "", "published": "", "source_type": "rss"}
        ]))

        # Mock output dir
        monkeypatch.setattr("scripts.migrate.OUTPUT_DIR", str(output_dir))

        db_path = tmp_dir = tmp_path / "test.db"

        count = migrate_from_output_dir(str(db_path))
        assert count >= 1

    def test_migrate_entries_writes_naive_utc_timestamps(self, monkeypatch):
        from datetime import datetime
        import scripts.migrate as migrate_module

        created_articles = []
        expected_now = datetime(2026, 5, 4, 12, 0, 0)

        class FakeArticle:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                created_articles.append(self)

        class FakeSession:
            def get(self, model, url):
                return None

            def add(self, article):
                self.article = article

            def commit(self):
                return None

            def close(self):
                return None

        fake_session = FakeSession()

        monkeypatch.setattr(migrate_module, "init", lambda db_path: None)
        monkeypatch.setattr(migrate_module, "get_session", lambda: fake_session)
        monkeypatch.setattr(migrate_module, "Article", FakeArticle)
        monkeypatch.setattr(migrate_module, "utcnow_naive", lambda: expected_now)

        count = migrate_module.migrate_entries([
            {"title": "A", "url": "https://a.com", "source": "src", "summary": "", "published": "", "source_type": "rss"}
        ], "ignored.db")

        assert count == 1
        assert len(created_articles) == 1
        assert created_articles[0].first_fetched == expected_now
        assert created_articles[0].last_seen == expected_now
        assert created_articles[0].first_fetched.tzinfo is None
        assert created_articles[0].last_seen.tzinfo is None
