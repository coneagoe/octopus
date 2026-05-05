# Dedup by Normalized URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw-URL deduplication with normalized-URL deduplication across the RSS/web pipeline, while preserving the current cache-driven summarize flow.

**Architecture:** Introduce a shared URL canonicalization helper in `scripts/`, then move SQLite identity from raw `url` to a canonical `normalized_url` plus a derived `entry_hash`. `scripts/db.py` owns the schema upgrade path for existing databases, fetchers deduplicate on canonical identity before emitting cache entries, and `scripts/migrate.py` backfills historical JSON caches using the same normalization rules.

**Tech Stack:** Python 3.8+, pytest, SQLAlchemy 2.x, requests, feedparser, BeautifulSoup, SQLite, uv, Ruff, Pyright

---

## File structure

- Create: `scripts/url_normalize.py` — shared URL normalization and hashing helpers used by DB, fetchers, and migration.
- Modify: `scripts/db.py` — v2 `Article`/`DailyEntry` schema plus legacy-schema upgrade on `init()`.
- Modify: `scripts/fetch_rss.py` — deduplicate by `normalized_url`, emit canonical identity fields in cache payload.
- Modify: `scripts/fetch_web.py` — canonicalize absolute links, deduplicate by `normalized_url`, emit canonical identity fields in cache payload.
- Modify: `scripts/migrate.py` — import cache rows into canonical article rows using the same helper.
- Create: `test/test_url_normalize.py` — unit tests for normalization rules.
- Modify: `test/test_db.py` — schema and legacy-migration regression tests.
- Modify: `test/test_fetch_rss.py` — RSS dedup regression tests for normalized URLs.
- Modify: `test/test_fetch_web.py` — website dedup regression tests for normalized URLs.
- Modify: `test/test_migrate.py` — cache-migration regression tests for normalized URLs.
- Modify: `docs/plans/2026-05-04-dedup-design.md` — align the older design note with the approved normalized-URL model.

## Task 1: Build the shared URL normalization helper

**Files:**
- Create: `scripts/url_normalize.py`
- Create: `test/test_url_normalize.py`

- [ ] **Step 1: Write the failing normalization tests**

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestUrlNormalize:
    def test_normalize_url_removes_tracking_params_and_fragment(self):
        from scripts.url_normalize import normalize_url

        raw = "https://Example.com/p/123?utm_source=weibo&fbclid=abc&x=1#section"

        assert normalize_url(raw) == "https://example.com/p/123?x=1"

    def test_normalize_url_sorts_query_params_and_removes_default_port(self):
        from scripts.url_normalize import normalize_url

        raw = "https://example.com:443/p/123?b=2&a=1"

        assert normalize_url(raw) == "https://example.com/p/123?a=1&b=2"

    def test_normalize_url_preserves_explicit_trailing_slash_choice(self):
        from scripts.url_normalize import normalize_url

        assert normalize_url("https://example.com/path/") == "https://example.com/path/"
        assert normalize_url("https://example.com/path") == "https://example.com/path"

    def test_make_entry_hash_is_stable_for_same_normalized_url(self):
        from scripts.url_normalize import make_entry_hash

        assert make_entry_hash("https://example.com/p/123?x=1") == make_entry_hash(
            "https://example.com/p/123?x=1"
        )
```

- [ ] **Step 2: Run the helper tests to verify they fail**

Run: `uv run pytest test/test_url_normalize.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.url_normalize'`.

- [ ] **Step 3: Implement `normalize_url()` and `make_entry_hash()`**

```python
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAM_NAMES = {
    "fbclid",
    "ref",
    "spm",
    "scene",
    "from",
    "share",
    "channel",
}


def _is_tracking_param(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in TRACKING_PARAM_NAMES


def normalize_url(raw_url: str) -> str:
    parts = urlsplit(raw_url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"invalid absolute url: {raw_url}")

    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port

    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    query_pairs = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    )
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, parts.path or "", query, ""))


def make_entry_hash(normalized_url: str) -> str:
    return sha256(normalized_url.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run the helper tests again**

Run: `uv run pytest test/test_url_normalize.py -v`

Expected: PASS for all four normalization/hash tests.

- [ ] **Step 5: Commit the helper**

```bash
git add scripts/url_normalize.py test/test_url_normalize.py
git commit -m "feat: add normalized url helper" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 2: Upgrade the SQLite schema to canonical article identity

**Files:**
- Modify: `scripts/db.py`
- Modify: `test/test_db.py`
- Uses: `scripts/url_normalize.py`

- [ ] **Step 1: Write the failing schema tests**

```python
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestArticleModel:
    def test_article_uses_entry_hash_primary_key_and_normalized_url_unique(self):
        from scripts.db import Article

        assert Article.__table__.columns["entry_hash"].primary_key
        assert not Article.__table__.columns["url"].primary_key
        assert Article.__table__.columns["normalized_url"].unique


class TestDailyEntryModel:
    def test_daily_entry_uses_date_and_entry_hash_primary_key(self):
        from scripts.db import DailyEntry

        columns = DailyEntry.__table__.columns
        assert columns["date"].primary_key
        assert columns["entry_hash"].primary_key
        assert "url" not in columns


class TestDbSession:
    def test_init_migrates_legacy_articles_into_normalized_rows(self, tmp_path):
        from scripts.db import Article, get_session, init

        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE articles (url TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT, published TEXT, summary TEXT, first_fetched TEXT, last_seen TEXT)"
        )
        conn.execute(
            "CREATE TABLE daily_entries (date TEXT NOT NULL, url TEXT NOT NULL, commentary TEXT DEFAULT '', PRIMARY KEY (date, url))"
        )
        conn.execute(
            "INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "https://example.com/p/1?utm_source=feed",
                "Old",
                "Src",
                "rss",
                "",
                "",
                "2026-05-01 00:00:00",
                "2026-05-01 00:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "https://example.com/p/1",
                "New",
                "Src",
                "rss",
                "",
                "",
                "2026-05-02 00:00:00",
                "2026-05-03 00:00:00",
            ),
        )
        conn.commit()
        conn.close()

        init(str(db_path))

        sess = get_session()
        rows = sess.query(Article).all()
        sess.close()

        assert len(rows) == 1
        assert rows[0].normalized_url == "https://example.com/p/1"
        assert rows[0].first_fetched.isoformat(sep=" ") == "2026-05-01 00:00:00"
```

- [ ] **Step 2: Run the DB tests to verify they fail**

Run: `uv run pytest test/test_db.py -v`

Expected: FAIL because `Article` still uses `url` as the primary key and `init()` does not migrate legacy tables.

- [ ] **Step 3: Implement the v2 models and schema-upgrade path**

```python
class Article(Base):
    __tablename__ = "articles"

    entry_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalized_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    author: Mapped[str] = mapped_column(String(256), default="")
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32))
    published: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    first_fetched: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class DailyEntry(Base):
    __tablename__ = "daily_entries"

    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    entry_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    commentary: Mapped[str] = mapped_column(Text, default="")
```

```python
def init(db_path: str):
    global _engine, _Session
    _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    _Session = sessionmaker(bind=_engine)
    _upgrade_legacy_schema(_engine)
    Base.metadata.create_all(_engine)
```

```python
def _upgrade_legacy_schema(engine) -> None:
    with engine.begin() as conn:
        article_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(articles)"))}
        if not article_columns or "normalized_url" in article_columns:
            return

        legacy_rows = conn.execute(
            text(
                "SELECT url, title, source, source_type, published, summary, first_fetched, last_seen FROM articles"
            )
        ).mappings()

        merged = {}
        for row in legacy_rows:
            normalized_url = normalize_url(row["url"])
            entry_hash = make_entry_hash(normalized_url)
            current = merged.get(entry_hash)
            if current is None:
                merged[entry_hash] = {
                    "entry_hash": entry_hash,
                    "normalized_url": normalized_url,
                    "url": row["url"],
                    "author": "",
                    "title": row["title"],
                    "source": row["source"],
                    "source_type": row["source_type"],
                    "published": row["published"],
                    "summary": row["summary"],
                    "first_fetched": row["first_fetched"],
                    "last_seen": row["last_seen"],
                }
                continue
            current["first_fetched"] = min(current["first_fetched"], row["first_fetched"])
            current["last_seen"] = max(current["last_seen"], row["last_seen"])

        conn.execute(text("ALTER TABLE articles RENAME TO articles_legacy"))
        conn.execute(text("ALTER TABLE daily_entries RENAME TO daily_entries_legacy"))
        Base.metadata.create_all(conn)
        for row in merged.values():
            conn.execute(
                text(
                    "INSERT INTO articles (entry_hash, normalized_url, url, author, title, source, source_type, published, summary, first_fetched, last_seen) VALUES (:entry_hash, :normalized_url, :url, :author, :title, :source, :source_type, :published, :summary, :first_fetched, :last_seen)"
                ),
                row,
            )
        conn.execute(text("DROP TABLE articles_legacy"))
        conn.execute(text("DROP TABLE daily_entries_legacy"))
```

- [ ] **Step 4: Run the DB tests again**

Run: `uv run pytest test/test_db.py -v`

Expected: PASS for the new canonical-schema and legacy-upgrade tests.

- [ ] **Step 5: Commit the schema work**

```bash
git add scripts/db.py test/test_db.py
git commit -m "feat: migrate db to normalized url identity" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 3: Move RSS and website fetchers to canonical deduplication

**Files:**
- Modify: `scripts/fetch_rss.py`
- Modify: `scripts/fetch_web.py`
- Modify: `test/test_fetch_rss.py`
- Modify: `test/test_fetch_web.py`
- Uses: `scripts/url_normalize.py`
- Uses: `scripts/db.py`

- [ ] **Step 1: Write the failing RSS/web dedup tests**

```python
def test_fetch_rss_skips_entry_when_normalized_url_exists(self, monkeypatch, tmp_path):
    from scripts.db import Article, get_session, init
    from scripts.fetch_rss import fetch_rss
    from scripts.url_normalize import make_entry_hash

    db_path = tmp_path / "test.db"
    init(str(db_path))

    normalized_url = "https://example.com/p/1"
    sess = get_session()
    sess.add(
        Article(
            entry_hash=make_entry_hash(normalized_url),
            normalized_url=normalized_url,
            url="https://example.com/p/1",
            author="",
            title="Old",
            source="Src",
            source_type="rss",
        )
    )
    sess.commit()
    sess.close()

    fake_feed = type(
        "Feed",
        (),
        {
            "entries": [
                {
                    "title": "Tracked",
                    "link": "https://example.com/p/1?utm_source=feed",
                    "published": "2026-05-04",
                    "summary": "content",
                }
            ]
        },
    )()
    monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)

    assert fetch_rss("https://example.com/rss", "Src", db_path=str(db_path)) == []
```

```python
def test_fetch_web_returns_canonical_identity_fields(self, monkeypatch, tmp_path):
    from scripts.db import init
    from scripts.fetch_web import fetch_web

    db_path = tmp_path / "test.db"
    init(str(db_path))

    monkeypatch.setattr(
        "scripts.fetch_web.requests.get",
        lambda url, headers, timeout: FakeResponse("<html></html>"),
    )
    monkeypatch.setattr(
        "scripts.fetch_web.BeautifulSoup",
        lambda text, parser: FakeSoup(
            articles=[FakeArticleElement("Test Article", "/article1?utm_source=site", "summary text")]
        ),
    )

    entries = fetch_web("https://example.com/news", "TestSource", db_path=str(db_path))

    assert entries[0]["url"] == "https://example.com/article1?utm_source=site"
    assert entries[0]["normalized_url"] == "https://example.com/article1"
    assert len(entries[0]["entry_hash"]) == 64
```

- [ ] **Step 2: Run the targeted fetcher tests to verify they fail**

Run: `uv run pytest test/test_fetch_rss.py test/test_fetch_web.py -v`

Expected: FAIL because fetchers still look up rows by raw `url` and do not emit `normalized_url` or `entry_hash`.

- [ ] **Step 3: Implement canonical lookup and cache payload fields in both fetchers**

```python
from scripts.url_normalize import make_entry_hash, normalize_url
```

```python
raw_url = str(entry.get("link") or "")
normalized_url = normalize_url(raw_url)
entry_hash = make_entry_hash(normalized_url)
existing = sess.get(Article, entry_hash)
if existing:
    existing.last_seen = utcnow_naive()
    sess.commit()
    sess.close()
    continue

article = Article(
    entry_hash=entry_hash,
    normalized_url=normalized_url,
    url=raw_url,
    author="",
    title=title,
    source=name,
    source_type="rss",
    published=published,
    summary=summary,
    first_fetched=now,
    last_seen=now,
)
```

```python
new_entries.append(
    {
        "entry_hash": entry_hash,
        "normalized_url": normalized_url,
        "source": name,
        "source_type": "rss",
        "title": title,
        "url": raw_url,
        "published": published,
        "summary": summary,
    }
)
```

```python
raw_url = urljoin(url, href) if isinstance(href, str) else url
normalized_url = normalize_url(raw_url)
entry_hash = make_entry_hash(normalized_url)
existing = sess.get(Article, entry_hash)
```

```python
articles.append(
    {
        "entry_hash": entry_hash,
        "normalized_url": normalized_url,
        "source": name,
        "source_type": "web",
        "title": title_elem.get_text(strip=True),
        "url": raw_url,
        "summary": summary_elem.get_text(strip=True)[:500] if summary_elem else "",
    }
)
```

- [ ] **Step 4: Handle malformed URLs per-entry instead of failing the whole source**

```python
try:
    normalized_url = normalize_url(raw_url)
except ValueError as exc:
    print(f"    -> 跳过非法 URL: {raw_url} ({exc})")
    continue
```

- [ ] **Step 5: Run the fetcher tests again**

Run: `uv run pytest test/test_fetch_rss.py test/test_fetch_web.py -v`

Expected: PASS for the new normalized-URL dedup tests and existing fetcher coverage.

- [ ] **Step 6: Commit the fetcher changes**

```bash
git add scripts/fetch_rss.py scripts/fetch_web.py test/test_fetch_rss.py test/test_fetch_web.py
git commit -m "feat: deduplicate fetchers by normalized url" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 4: Canonicalize JSON-cache backfill in `scripts/migrate.py`

**Files:**
- Modify: `scripts/migrate.py`
- Modify: `test/test_migrate.py`
- Uses: `scripts/url_normalize.py`
- Uses: `scripts/db.py`

- [ ] **Step 1: Write the failing migration tests**

```python
def test_migrate_entries_deduplicates_by_normalized_url(self, tmp_path):
    from scripts.db import Article, get_session, init
    from scripts.migrate import migrate_entries

    db_path = tmp_path / "test.db"
    init(str(db_path))

    count = migrate_entries(
        [
            {"title": "A", "url": "https://example.com/p/1?utm_source=feed", "source": "src", "summary": "", "published": "", "source_type": "rss"},
            {"title": "B", "url": "https://example.com/p/1", "source": "src", "summary": "", "published": "", "source_type": "rss"},
        ],
        str(db_path),
    )

    sess = get_session()
    rows = sess.query(Article).all()
    sess.close()

    assert count == 1
    assert len(rows) == 1
    assert rows[0].normalized_url == "https://example.com/p/1"
```

```python
def test_migrate_entries_skips_invalid_urls_without_aborting(self, tmp_path, capsys):
    from scripts.db import Article, get_session, init
    from scripts.migrate import migrate_entries

    db_path = tmp_path / "test.db"
    init(str(db_path))

    count = migrate_entries(
        [
            {"title": "Bad", "url": "not-a-url", "source": "src", "summary": "", "published": "", "source_type": "rss"},
            {"title": "Good", "url": "https://example.com/p/2", "source": "src", "summary": "", "published": "", "source_type": "rss"},
        ],
        str(db_path),
    )

    sess = get_session()
    rows = sess.query(Article).all()
    sess.close()

    out = capsys.readouterr().out
    assert count == 1
    assert len(rows) == 1
    assert "跳过非法 URL" in out
```

- [ ] **Step 2: Run the migration tests to verify they fail**

Run: `uv run pytest test/test_migrate.py -v`

Expected: FAIL because migration still keys rows by raw `url` and aborts malformed canonicalization implicitly.

- [ ] **Step 3: Implement canonical migration behavior**

```python
from scripts.url_normalize import make_entry_hash, normalize_url
```

```python
for entry in entries:
    raw_url = entry.get("url", "")
    if not raw_url:
        continue
    try:
        normalized_url = normalize_url(raw_url)
    except ValueError as exc:
        print(f"  跳过非法 URL: {raw_url} ({exc})")
        continue

    entry_hash = make_entry_hash(normalized_url)
    existing = sess.get(Article, entry_hash)
    if existing:
        existing.last_seen = now
        continue

    article = Article(
        entry_hash=entry_hash,
        normalized_url=normalized_url,
        url=raw_url,
        author="",
        title=entry.get("title", ""),
        source=entry.get("source", ""),
        source_type=entry.get("source_type", "rss"),
        published=entry.get("published", ""),
        summary=entry.get("summary", ""),
        first_fetched=now,
        last_seen=now,
    )
    sess.add(article)
    count += 1
```

- [ ] **Step 4: Run the migration tests again**

Run: `uv run pytest test/test_migrate.py -v`

Expected: PASS for normalized-URL deduplication and invalid-URL skip coverage.

- [ ] **Step 5: Commit the migration update**

```bash
git add scripts/migrate.py test/test_migrate.py
git commit -m "feat: canonicalize cache migration" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 5: Sync the older design note with the approved model

**Files:**
- Modify: `docs/plans/2026-05-04-dedup-design.md`
- Reference: `docs/superpowers/specs/2026-05-04-dedup-normalized-url-design.md`

- [ ] **Step 1: Rewrite the key-design sections to remove `+ author` semantics**

```md
| 当前实现 | `url` 作为 PK | 简单、直观、实现成本低 | tracking 参数会把同一文章拆成多条 |
| **推荐方案** | `normalized_url` 唯一约束，`entry_hash = SHA256(normalized_url)` | 与“同一 canonical URL 只出现一次”的目标一致 | 需要补充归一化和迁移逻辑 |
| 候选方案（不推荐） | `normalized_url + author` | 看起来能区分转载 | 偏离本次范围，且 author 不稳定 |
```

- [ ] **Step 2: Update schema and migration text to match implementation**

```md
| entry_hash | String(64) | 主键，SHA256(normalized_url) |
| normalized_url | String(2048) | 唯一约束，用于去重 |
| url | String(2048) | 原始 URL，保留用于外链和排查 |
| author | String(256) | 普通字段，不参与唯一性 |
```

- [ ] **Step 3: Save the doc and inspect the diff**

Run: `git --no-pager diff -- docs/plans/2026-05-04-dedup-design.md`

Expected: the plan note now consistently describes normalized-URL deduplication rather than `normalize_url(url) + author`.

- [ ] **Step 4: Commit the doc sync**

```bash
git add docs/plans/2026-05-04-dedup-design.md
git commit -m "docs: align dedup design with normalized url model" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 6: Run the full repository checks

**Files:**
- Verify: `scripts/url_normalize.py`
- Verify: `scripts/db.py`
- Verify: `scripts/fetch_rss.py`
- Verify: `scripts/fetch_web.py`
- Verify: `scripts/migrate.py`
- Verify: `test/test_url_normalize.py`
- Verify: `test/test_db.py`
- Verify: `test/test_fetch_rss.py`
- Verify: `test/test_fetch_web.py`
- Verify: `test/test_migrate.py`

- [ ] **Step 1: Run Ruff**

Run: `uv run ruff check scripts/`

Expected: PASS with no lint errors.

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest test/`

Expected: PASS for existing tests plus the new normalization/schema/migration coverage.

- [ ] **Step 3: Run Pyright**

Run: `uv run pyright scripts test`

Expected: PASS with no new type-checking errors.

- [ ] **Step 4: Inspect the final diff before the last commit**

Run: `git --no-pager diff --stat && git --no-pager status --short`

Expected: only the planned files are modified and the worktree is clean after commits.

- [ ] **Step 5: Create the final integration commit if needed**

```bash
git add scripts/url_normalize.py scripts/db.py scripts/fetch_rss.py scripts/fetch_web.py scripts/migrate.py test/test_url_normalize.py test/test_db.py test/test_fetch_rss.py test/test_fetch_web.py test/test_migrate.py docs/plans/2026-05-04-dedup-design.md
git commit -m "feat: deduplicate articles by normalized url" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
