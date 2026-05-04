"""数据库管理 — SQLite + SQLAlchemy ORM"""

import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

from sqlalchemy import DateTime, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from scripts.url_normalize import make_entry_hash, normalize_url


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Article(Base):
    """文章记录表 — 规范化 URL 唯一，用于去重"""

    __tablename__ = 'articles'

    entry_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalized_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    author: Mapped[str] = mapped_column(String(256), default='')
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32))  # 'rss' / 'web' / 'feishu' / 'email'
    published: Mapped[str] = mapped_column(String(256), default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    first_fetched: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    def __init__(self, **kwargs):
        url = kwargs.get('url')
        normalized_url = kwargs.get('normalized_url')
        if url and not normalized_url:
            normalized_url = normalize_url(url)
            kwargs['normalized_url'] = normalized_url
        if normalized_url and 'entry_hash' not in kwargs:
            kwargs['entry_hash'] = make_entry_hash(normalized_url)
        kwargs.setdefault('author', '')
        super().__init__(**kwargs)


class DailyEntry(Base):
    """日报条目表 — 记录每天写了哪些文章"""

    __tablename__ = 'daily_entries'

    date: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    entry_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    commentary: Mapped[str] = mapped_column(Text, default='')


_engine = None
_Session = None


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = :table_name
            """
        ),
        {'table_name': table_name},
    ).fetchone()
    return row is not None


def _table_columns(conn, table_name: str) -> Set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _parse_sqlite_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f'Unsupported datetime format: {value}')


def _warn_skipped_legacy_url(kind: str, url: str, error: ValueError):
    print(f"警告：跳过格式错误的旧{kind} URL: {url} ({error})", file=sys.stderr)


def _choose_canonical_row(existing: dict, candidate: dict) -> Tuple[dict, dict]:
    def sort_key(row: dict):
        first_fetched = row['first_fetched']
        return (
            first_fetched if first_fetched is not None else datetime.max,
            row['url'],
        )

    if sort_key(candidate) < sort_key(existing):
        return candidate, existing
    return existing, candidate


def _merge_article_rows(existing: dict, candidate: dict) -> dict:
    preferred, alternate = _choose_canonical_row(existing, candidate)
    merged = dict(preferred)

    for field in ('url', 'author', 'title', 'source', 'source_type', 'published', 'summary'):
        if not merged.get(field):
            merged[field] = alternate.get(field, '')

    first_fetched_values = [row for row in (existing['first_fetched'], candidate['first_fetched']) if row is not None]
    merged['first_fetched'] = min(first_fetched_values) if first_fetched_values else None

    last_seen_values = [row for row in (existing['last_seen'], candidate['last_seen']) if row is not None]
    merged['last_seen'] = max(last_seen_values) if last_seen_values else None

    return merged


def _load_legacy_articles(conn) -> List[dict]:
    rows = conn.execute(
        text(
            """
            SELECT url, title, source, source_type, published, summary, first_fetched, last_seen
            FROM articles
            ORDER BY url
            """
        )
    ).mappings().all()

    merged_rows: Dict[str, dict] = {}
    for row in rows:
        try:
            normalized_url = normalize_url(row['url'])
        except ValueError as error:
            _warn_skipped_legacy_url('文章', row['url'], error)
            continue
        entry_hash = make_entry_hash(normalized_url)
        candidate = {
            'entry_hash': entry_hash,
            'normalized_url': normalized_url,
            'url': row['url'],
            'author': '',
            'title': row['title'],
            'source': row['source'],
            'source_type': row['source_type'],
            'published': row['published'] or '',
            'summary': row['summary'] or '',
            'first_fetched': _parse_sqlite_datetime(row['first_fetched']),
            'last_seen': _parse_sqlite_datetime(row['last_seen']),
        }
        existing = merged_rows.get(entry_hash)
        if existing is None:
            merged_rows[entry_hash] = candidate
            continue
        merged_rows[entry_hash] = _merge_article_rows(existing, candidate)

    return [merged_rows[key] for key in sorted(merged_rows)]


def _load_legacy_daily_entries(conn, canonical_urls: Dict[str, str]) -> List[dict]:
    if not _table_exists(conn, 'daily_entries'):
        return []

    columns = _table_columns(conn, 'daily_entries')
    if 'entry_hash' in columns and 'url' not in columns:
        rows = conn.execute(
            text(
                """
                SELECT date, entry_hash, commentary
                FROM daily_entries
                ORDER BY date, entry_hash
                """
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    rows = conn.execute(
        text(
            """
            SELECT date, url, commentary
            FROM daily_entries
            ORDER BY date, url
            """
        )
    ).mappings().all()

    merged_rows: Dict[Tuple[str, str], dict] = {}
    for row in rows:
        try:
            normalized_url = normalize_url(row['url'])
        except ValueError as error:
            _warn_skipped_legacy_url('日报', row['url'], error)
            continue
        entry_hash = make_entry_hash(normalized_url)
        key = (row['date'], entry_hash)
        commentary = row['commentary'] or ''
        existing = merged_rows.get(key)
        if existing is None:
            merged_rows[key] = {
                'date': row['date'],
                'entry_hash': entry_hash,
                'commentary': commentary,
                'url': row['url'],
            }
            continue
        canonical_url = canonical_urls.get(entry_hash)
        if canonical_url and row['url'] == canonical_url and existing.get('url') != canonical_url:
            existing['commentary'] = commentary
            existing['url'] = row['url']
        elif not existing['commentary'] and commentary:
            existing['commentary'] = commentary

    return [
        {
            'date': row['date'],
            'entry_hash': row['entry_hash'],
            'commentary': row['commentary'],
        }
        for _, row in sorted(merged_rows.items())
    ]


def _recreate_v2_tables(conn, articles: List[dict], daily_entries: List[dict]):
    conn.execute(text("DROP TABLE IF EXISTS daily_entries_v2"))
    conn.execute(text("DROP TABLE IF EXISTS articles_v2"))

    conn.execute(
        text(
            """
            CREATE TABLE articles_v2 (
                entry_hash VARCHAR(64) PRIMARY KEY NOT NULL,
                normalized_url VARCHAR(2048) NOT NULL UNIQUE,
                url VARCHAR(2048) NOT NULL,
                author VARCHAR(256) NOT NULL DEFAULT '',
                title VARCHAR(1024) NOT NULL,
                source VARCHAR(256) NOT NULL,
                source_type VARCHAR(32),
                published VARCHAR(256),
                summary TEXT,
                first_fetched DATETIME,
                last_seen DATETIME
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE daily_entries_v2 (
                date VARCHAR(10) NOT NULL,
                entry_hash VARCHAR(64) NOT NULL,
                commentary TEXT,
                PRIMARY KEY (date, entry_hash)
            )
            """
        )
    )

    for article in articles:
        conn.execute(
            text(
                """
                INSERT INTO articles_v2 (
                    entry_hash, normalized_url, url, author, title, source,
                    source_type, published, summary, first_fetched, last_seen
                ) VALUES (
                    :entry_hash, :normalized_url, :url, :author, :title, :source,
                    :source_type, :published, :summary, :first_fetched, :last_seen
                )
                """
            ),
            article,
        )

    for daily_entry in daily_entries:
        conn.execute(
            text(
                """
                INSERT INTO daily_entries_v2 (date, entry_hash, commentary)
                VALUES (:date, :entry_hash, :commentary)
                """
            ),
            daily_entry,
        )

    if _table_exists(conn, 'daily_entries'):
        conn.execute(text("DROP TABLE daily_entries"))
    if _table_exists(conn, 'articles'):
        conn.execute(text("DROP TABLE articles"))
    conn.execute(text("ALTER TABLE articles_v2 RENAME TO articles"))
    conn.execute(text("ALTER TABLE daily_entries_v2 RENAME TO daily_entries"))


def _upgrade_legacy_schema(engine):
    with engine.begin() as conn:
        if not _table_exists(conn, 'articles'):
            return
        if 'normalized_url' in _table_columns(conn, 'articles'):
            return

        articles = _load_legacy_articles(conn)
        canonical_urls = {article['entry_hash']: article['url'] for article in articles}
        daily_entries = _load_legacy_daily_entries(conn, canonical_urls)
        _recreate_v2_tables(conn, articles, daily_entries)


def init(db_path: str):
    """初始化数据库（创建 engine + 建表）"""
    global _engine, _Session
    _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    _upgrade_legacy_schema(_engine)
    _Session = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)


def get_session():
    """获取数据库会话（延迟初始化）"""
    global _Session
    if _Session is None:
        db_path = os.path.join(os.path.dirname(__file__), '..', 'output', 'octopus.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        init(db_path)
    assert _Session is not None
    return _Session()
