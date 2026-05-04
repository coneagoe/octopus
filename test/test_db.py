"""Test cases for scripts/db.py"""

from datetime import datetime, timezone
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestArticleModel:
    def test_utcnow_naive_returns_naive_datetime(self):
        from scripts.db import utcnow_naive

        timestamp = utcnow_naive()

        assert timestamp.tzinfo is None

    def test_article_tablename_is_articles(self):
        from scripts.db import Article
        assert Article.__tablename__ == 'articles'

    def test_article_uses_entry_hash_as_primary_key(self):
        from scripts.db import Article
        entry_hash_col = Article.__table__.columns['entry_hash']
        assert entry_hash_col.primary_key

    def test_article_url_is_not_primary_key(self):
        from scripts.db import Article
        url_col = Article.__table__.columns['url']
        assert not url_col.primary_key

    def test_article_normalized_url_is_unique_and_not_null(self):
        from scripts.db import Article

        normalized_url_col = Article.__table__.columns['normalized_url']

        assert normalized_url_col.unique
        assert not normalized_url_col.nullable

    def test_article_has_expected_columns(self):
        from scripts.db import Article
        cols = {c.name for c in Article.__table__.columns}
        required = {
            'entry_hash',
            'normalized_url',
            'url',
            'author',
            'title',
            'source',
            'source_type',
            'published',
            'summary',
            'first_fetched',
            'last_seen',
        }
        assert required.issubset(cols), f"missing: {required - cols}"


class TestDailyEntryModel:
    def test_daily_entry_tablename_is_daily_entries(self):
        from scripts.db import DailyEntry
        assert DailyEntry.__tablename__ == 'daily_entries'

    def test_daily_entry_uses_date_and_entry_hash_as_primary_key(self):
        from scripts.db import DailyEntry
        cols = DailyEntry.__table__.columns
        assert cols['date'].primary_key
        assert cols['entry_hash'].primary_key

    def test_daily_entry_no_longer_has_url_column(self):
        from scripts.db import DailyEntry
        cols = DailyEntry.__table__.columns

        assert 'url' not in cols


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

    def test_init_migrates_legacy_raw_url_schema_to_normalized_identity(self, tmp_path):
        from scripts.db import init, get_session
        from scripts.url_normalize import make_entry_hash, normalize_url

        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE articles (
                url VARCHAR(2048) PRIMARY KEY,
                title VARCHAR(1024) NOT NULL,
                source VARCHAR(256) NOT NULL,
                source_type VARCHAR(32),
                published VARCHAR(256),
                summary TEXT,
                first_fetched DATETIME,
                last_seen DATETIME
            );

            CREATE TABLE daily_entries (
                date VARCHAR(10) NOT NULL,
                url VARCHAR(2048) NOT NULL,
                commentary TEXT,
                PRIMARY KEY (date, url)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO articles
                (url, title, source, source_type, published, summary, first_fetched, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com/post?utm_source=rss",
                "Old title",
                "Example",
                "rss",
                "",
                "old summary",
                "2024-01-01 08:00:00",
                "2024-01-01 08:30:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO articles
                (url, title, source, source_type, published, summary, first_fetched, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com/post",
                "Canonical title",
                "Example",
                "rss",
                "",
                "new summary",
                "2024-01-02 09:00:00",
                "2024-01-03 10:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO daily_entries (date, url, commentary) VALUES (?, ?, ?)",
            ("2024-01-01", "https://example.com/post?utm_source=rss", "first commentary"),
        )
        conn.execute(
            "INSERT INTO daily_entries (date, url, commentary) VALUES (?, ?, ?)",
            ("2024-01-01", "https://example.com/post", "second commentary"),
        )
        conn.commit()
        conn.close()

        init(str(db_path))
        sess = get_session()
        from sqlalchemy import text

        rows = sess.execute(
            text(
                """
                SELECT entry_hash, normalized_url, url, first_fetched, last_seen
                FROM articles
                """
            )
        ).fetchall()

        normalized_url = normalize_url("https://example.com/post?utm_source=rss")
        assert len(rows) == 1
        assert rows[0].entry_hash == make_entry_hash(normalized_url)
        assert rows[0].normalized_url == normalized_url
        assert datetime.fromisoformat(rows[0].first_fetched) == datetime(2024, 1, 1, 8, 0, 0)
        assert datetime.fromisoformat(rows[0].last_seen) == datetime(2024, 1, 3, 10, 0, 0)

        daily_rows = sess.execute(
            text(
                """
                SELECT date, entry_hash, commentary
                FROM daily_entries
                ORDER BY date, entry_hash
                """
            )
        ).fetchall()

        assert daily_rows == [
            ("2024-01-01", make_entry_hash(normalized_url), "first commentary"),
        ]
        sess.close()

    def test_init_skips_malformed_legacy_article_with_warning(self, tmp_path, capsys):
        from scripts.db import init, get_session

        db_path = tmp_path / "legacy-bad-article.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE articles (
                url VARCHAR(2048) PRIMARY KEY,
                title VARCHAR(1024) NOT NULL,
                source VARCHAR(256) NOT NULL,
                source_type VARCHAR(32),
                published VARCHAR(256),
                summary TEXT,
                first_fetched DATETIME,
                last_seen DATETIME
            );

            CREATE TABLE daily_entries (
                date VARCHAR(10) NOT NULL,
                url VARCHAR(2048) NOT NULL,
                commentary TEXT,
                PRIMARY KEY (date, url)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO articles
                (url, title, source, source_type, published, summary, first_fetched, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("not-a-url", "Broken", "Example", "rss", "", "", "2024-01-01 08:00:00", "2024-01-01 08:30:00"),
        )
        conn.execute(
            """
            INSERT INTO articles
                (url, title, source, source_type, published, summary, first_fetched, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com/good",
                "Good",
                "Example",
                "rss",
                "",
                "",
                "2024-01-02 09:00:00",
                "2024-01-02 09:30:00",
            ),
        )
        conn.commit()
        conn.close()

        init(str(db_path))
        captured = capsys.readouterr()

        assert "跳过格式错误的旧文章 URL: not-a-url" in captured.err

        sess = get_session()
        from sqlalchemy import text

        rows = sess.execute(text("SELECT url FROM articles ORDER BY url")).fetchall()
        assert rows == [("https://example.com/good",)]
        sess.close()

    def test_init_skips_malformed_legacy_daily_entry_with_warning(self, tmp_path, capsys):
        from scripts.db import init, get_session

        db_path = tmp_path / "legacy-bad-daily.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE articles (
                url VARCHAR(2048) PRIMARY KEY,
                title VARCHAR(1024) NOT NULL,
                source VARCHAR(256) NOT NULL,
                source_type VARCHAR(32),
                published VARCHAR(256),
                summary TEXT,
                first_fetched DATETIME,
                last_seen DATETIME
            );

            CREATE TABLE daily_entries (
                date VARCHAR(10) NOT NULL,
                url VARCHAR(2048) NOT NULL,
                commentary TEXT,
                PRIMARY KEY (date, url)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO articles
                (url, title, source, source_type, published, summary, first_fetched, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com/good",
                "Good",
                "Example",
                "rss",
                "",
                "",
                "2024-01-02 09:00:00",
                "2024-01-02 09:30:00",
            ),
        )
        conn.execute(
            "INSERT INTO daily_entries (date, url, commentary) VALUES (?, ?, ?)",
            ("2024-01-02", "not-a-url", "broken commentary"),
        )
        conn.execute(
            "INSERT INTO daily_entries (date, url, commentary) VALUES (?, ?, ?)",
            ("2024-01-02", "https://example.com/good", "good commentary"),
        )
        conn.commit()
        conn.close()

        init(str(db_path))
        captured = capsys.readouterr()

        assert "跳过格式错误的旧日报 URL: not-a-url" in captured.err

        sess = get_session()
        from sqlalchemy import text

        daily_rows = sess.execute(
            text("SELECT date, commentary FROM daily_entries ORDER BY date, entry_hash")
        ).fetchall()
        assert daily_rows == [("2024-01-02", "good commentary")]
        sess.close()

    def test_get_session_requires_entry_hash_for_article_lookup(self, tmp_path):
        from scripts.db import Article, get_session, init
        from scripts.url_normalize import make_entry_hash, normalize_url

        db_path = tmp_path / "session-get.db"
        init(str(db_path))
        sess = get_session()
        article = Article(
            url="https://example.com/post?utm_source=rss",
            title="Title",
            source="Example",
            source_type="rss",
        )
        sess.add(article)
        sess.commit()

        normalized_url = normalize_url("https://example.com/post?utm_source=rss")
        entry_hash = make_entry_hash(normalized_url)

        assert sess.get(Article, "https://example.com/post?utm_source=rss") is None
        found = sess.get(Article, entry_hash)
        assert found is not None
        assert found.url == "https://example.com/post?utm_source=rss"
        sess.close()


class TestTimestampHelpers:
    def test_utcnow_naive_returns_naive_utc_datetime(self):
        from scripts.db import utcnow_naive

        value = utcnow_naive()

        assert value.tzinfo is None
        offset = value.replace(tzinfo=timezone.utc).utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 0
