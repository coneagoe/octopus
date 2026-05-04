# Octopus Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the reviewed production issues in website URL deduplication, database timestamp consistency, and `.env` loading without changing the current pipeline scope.

**Architecture:** Keep the repair narrow and local. `scripts/fetch_web.py` will canonicalize links before deduplication and output, while all SQLite writers (`scripts/db.py`, `scripts/fetch_rss.py`, `scripts/fetch_web.py`, and `scripts/migrate.py`) will share the same naive-UTC timestamp behavior so existing rows and new writes stay consistent. `scripts/run.sh` will switch to shell-native `.env` loading. Tests stay in the existing `test/` layout and validate the repaired behaviors directly.

**Tech Stack:** Python 3.8+, pytest, SQLAlchemy, requests, BeautifulSoup, Bash, uv, Ruff, Pyright

---

## File structure

- Modify: `scripts/fetch_web.py` — normalize extracted article URLs before DB lookup and cache output.
- Modify: `test/test_fetch_web.py` — add regression tests for absolute URL normalization and cross-site dedup safety.
- Modify: `scripts/db.py` — expose a shared naive-UTC helper and use it for `Article` defaults.
- Modify: `scripts/fetch_rss.py` — use the shared naive-UTC helper for inserted and updated article rows.
- Modify: `scripts/migrate.py` — use the shared naive-UTC helper when backfilling rows.
- Modify: `test/test_db.py` — add naive-UTC helper/default regression coverage.
- Modify: `test/test_fetch_rss.py` — assert RSS writes remain naive UTC.
- Modify: `test/test_migrate.py` — assert migration writes remain naive UTC.
- Modify: `scripts/run.sh` — replace fragile `.env` parsing with shell-native sourcing.

### Task 1: Lock in website URL normalization with failing tests

**Files:**
- Modify: `test/test_fetch_web.py`
- Uses: `scripts/fetch_web.py`

- [ ] **Step 1: Write the failing test for relative URL normalization**

```python
def test_fetch_web_normalizes_relative_link_before_return_and_insert(self, monkeypatch, tmp_path):
    from scripts.db import Article, get_session, init
    from scripts.fetch_web import fetch_web

    db_path = tmp_path / "test.db"
    init(str(db_path))

    class FakeResponse:
        text = "<html></html>"

        def raise_for_status(self):
            pass

    class FakeTitle:
        def __init__(self, text):
            self.text = text

        def get_text(self, strip=True):
            return self.text

    class FakeLink:
        def __init__(self, href):
            self.href = href

        def __getitem__(self, key):
            assert key == "href"
            return self.href

    class FakeSummary:
        def __init__(self, text):
            self.text = text

        def get_text(self, strip=True):
            return self.text

    class FakeItem:
        def find(self, tag, href=False):
            if tag == ["h1", "h2", "h3"]:
                return FakeTitle("Test Article")
            if tag == "a" and href:
                return FakeLink("/article1")
            if tag == "p":
                return FakeSummary("summary text")
            return None

    class FakeSoup:
        def select(self, selector):
            return [FakeItem()]

        def find(self, tag):
            return None

    monkeypatch.setattr("requests.get", lambda url, headers, timeout: FakeResponse())
    monkeypatch.setattr("scripts.fetch_web.BeautifulSoup", lambda text, parser: FakeSoup())

    entries = fetch_web("https://example.com/news", "TestSource", db_path=str(db_path))

    assert entries[0]["url"] == "https://example.com/article1"

    sess = get_session()
    article = sess.get(Article, "https://example.com/article1")
    assert article is not None
    sess.close()
```

- [ ] **Step 2: Run the single test to verify it fails**

Run: `uv run pytest test/test_fetch_web.py::TestFetchWebDedup::test_fetch_web_normalizes_relative_link_before_return_and_insert -v`

Expected: FAIL because the code still returns and stores `/article1`.

- [ ] **Step 3: Write the failing test for cross-site dedup safety**

```python
def test_fetch_web_same_relative_path_on_different_sites_is_not_deduplicated(self, monkeypatch, tmp_path):
    from scripts.db import Article, get_session, init
    from scripts.fetch_web import fetch_web

    db_path = tmp_path / "test.db"
    init(str(db_path))

    class FakeResponse:
        text = "<html></html>"

        def raise_for_status(self):
            pass

    class FakeTitle:
        def __init__(self, text):
            self.text = text

        def get_text(self, strip=True):
            return self.text

    class FakeLink:
        def __init__(self, href):
            self.href = href

        def __getitem__(self, key):
            assert key == "href"
            return self.href

    class FakeItem:
        def __init__(self, title):
            self.title = title

        def find(self, tag, href=False):
            if tag == ["h1", "h2", "h3"]:
                return FakeTitle(self.title)
            if tag == "a" and href:
                return FakeLink("/shared-path")
            if tag == "p":
                return None
            return None

    class FakeSoup:
        def __init__(self, title):
            self.title = title

        def select(self, selector):
            return [FakeItem(self.title)]

        def find(self, tag):
            return None

    monkeypatch.setattr("requests.get", lambda url, headers, timeout: FakeResponse())
    soups = iter([FakeSoup("First"), FakeSoup("Second")])
    monkeypatch.setattr("scripts.fetch_web.BeautifulSoup", lambda text, parser: next(soups))

    first_entries = fetch_web("https://site-one.example/news", "SiteOne", db_path=str(db_path))
    second_entries = fetch_web("https://site-two.example/news", "SiteTwo", db_path=str(db_path))

    assert first_entries[0]["url"] == "https://site-one.example/shared-path"
    assert second_entries[0]["url"] == "https://site-two.example/shared-path"

    sess = get_session()
    assert sess.get(Article, "https://site-one.example/shared-path") is not None
    assert sess.get(Article, "https://site-two.example/shared-path") is not None
    sess.close()
```

- [ ] **Step 4: Run the second single test to verify it fails**

Run: `uv run pytest test/test_fetch_web.py::TestFetchWebDedup::test_fetch_web_same_relative_path_on_different_sites_is_not_deduplicated -v`

Expected: FAIL because the second fetch currently collides on `/shared-path`.

- [ ] **Step 5: Commit the failing tests**

```bash
git add test/test_fetch_web.py
git commit -m "test: cover web url normalization regressions"
```

### Task 2: Implement website URL normalization and make the tests pass

**Files:**
- Modify: `scripts/fetch_web.py`
- Verify: `test/test_fetch_web.py`

- [ ] **Step 1: Import `urljoin` and normalize extracted article URLs**

```python
import json
import os
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
```

```python
article_url = urljoin(url, link_elem['href']) if link_elem else url
```

- [ ] **Step 2: Keep the normalized URL as the shared value for dedup and output**

```python
existing = sess.get(Article, article_url)
```

```python
article = Article(
    url=article_url,
    title=title_elem.get_text(strip=True),
    source=name,
    source_type='web',
    published='',
    summary=summary_elem.get_text(strip=True)[:500] if summary_elem else '',
    first_fetched=now,
    last_seen=now,
)
```

```python
articles.append({
    'source': name,
    'source_type': 'web',
    'title': title_elem.get_text(strip=True),
    'url': article_url,
    'summary': summary_elem.get_text(strip=True)[:500] if summary_elem else '',
})
```

- [ ] **Step 3: Run the targeted web tests and make sure they pass**

Run: `uv run pytest test/test_fetch_web.py -v`

Expected: PASS for the new normalization tests and the existing request-error/duplicate coverage.

- [ ] **Step 4: Commit the implementation**

```bash
git add scripts/fetch_web.py test/test_fetch_web.py
git commit -m "fix: normalize web article urls"
```

### Task 3: Lock in naive UTC timestamp behavior with failing tests

**Files:**
- Modify: `test/test_db.py`
- Modify: `test/test_fetch_rss.py`
- Modify: `test/test_migrate.py`
- Uses: `scripts/db.py`
- Uses: `scripts/fetch_rss.py`
- Uses: `scripts/migrate.py`

- [ ] **Step 1: Add a failing DB-helper regression test**

```python
def test_utcnow_naive_returns_naive_datetime(self):
    from scripts.db import utcnow_naive

    timestamp = utcnow_naive()

    assert timestamp.tzinfo is None
```

- [ ] **Step 2: Add a failing RSS-write regression test**

```python
def test_fetch_rss_inserts_naive_utc_timestamps(self, monkeypatch, tmp_path):
    from scripts.db import Article, get_session, init
    from scripts.fetch_rss import fetch_rss

    db_path = tmp_path / "test.db"
    init(str(db_path))

    fake_feed = type("F", (), {
        "entries": [
            {"title": "Brand New", "link": "https://example.com/brandnew", "published": "2026-05-04", "summary": "content"},
        ]
    })()
    monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)

    fetch_rss("https://example.com/rss", "TestSource", db_path=str(db_path))

    sess = get_session()
    article = sess.get(Article, "https://example.com/brandnew")
    assert article.first_fetched.tzinfo is None
    assert article.last_seen.tzinfo is None
    sess.close()
```

- [ ] **Step 3: Add a failing migration-write regression test**

```python
def test_migrate_entries_writes_naive_utc_timestamps(self, tmp_path):
    from scripts.db import Article, get_session, init
    from scripts.migrate import migrate_entries

    db_path = tmp_path / "test.db"
    init(str(db_path))

    entries = [
        {"title": "A", "url": "https://a.com", "source": "src", "summary": "", "published": "", "source_type": "rss"}
    ]

    migrate_entries(entries, str(db_path))

    sess = get_session()
    article = sess.get(Article, "https://a.com")
    assert article.first_fetched.tzinfo is None
    assert article.last_seen.tzinfo is None
    sess.close()
```

- [ ] **Step 4: Run the targeted tests to verify they fail**

Run: `uv run pytest test/test_db.py::TestArticleModel::test_utcnow_naive_returns_naive_datetime test/test_fetch_rss.py::TestFetchRssDedup::test_fetch_rss_inserts_naive_utc_timestamps test/test_migrate.py::TestMigrateFromJson::test_migrate_entries_writes_naive_utc_timestamps -v`

Expected: FAIL because the helper does not exist yet and current writes still use timezone-aware UTC datetimes.

- [ ] **Step 5: Commit the failing tests**

```bash
git add test/test_db.py test/test_fetch_rss.py test/test_migrate.py
git commit -m "test: cover naive utc timestamp writes"
```

### Task 4: Restore naive UTC timestamp defaults and pass the DB tests

**Files:**
- Modify: `scripts/db.py`
- Modify: `scripts/fetch_rss.py`
- Modify: `scripts/fetch_web.py`
- Modify: `scripts/migrate.py`
- Verify: `test/test_db.py`
- Verify: `test/test_fetch_rss.py`
- Verify: `test/test_fetch_web.py`
- Verify: `test/test_migrate.py`

- [ ] **Step 1: Add a shared naive-UTC helper in `scripts/db.py`**

```python
import os
from datetime import datetime
from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
```

```python
def utcnow_naive():
    return datetime.utcnow()
```

- [ ] **Step 2: Use the helper for `Article` defaults**

```python
first_fetched = Column(DateTime, default=utcnow_naive)
last_seen = Column(DateTime, default=utcnow_naive)
```

- [ ] **Step 3: Update RSS writes to use the shared helper**

```python
from scripts.db import Article, get_session, init, utcnow_naive
```

```python
now = utcnow_naive()
```

- [ ] **Step 4: Update web writes to use the shared helper**

```python
from scripts.db import Article, get_session, init, utcnow_naive
```

```python
now = utcnow_naive()
```

- [ ] **Step 5: Update migration writes to use the shared helper**

```python
from scripts.db import Article, get_session, init, utcnow_naive
```

```python
now = utcnow_naive()
```

- [ ] **Step 6: Run the targeted timestamp tests and make sure they pass**

Run: `uv run pytest test/test_db.py test/test_fetch_rss.py test/test_fetch_web.py test/test_migrate.py -v`

Expected: PASS including the new naive-UTC assertions and the web tests from Tasks 1-2.

- [ ] **Step 7: Commit the timestamp fix**

```bash
git add scripts/db.py scripts/fetch_rss.py scripts/fetch_web.py scripts/migrate.py test/test_db.py test/test_fetch_rss.py test/test_migrate.py
git commit -m "fix: keep sqlite timestamp writes naive utc"
```

### Task 5: Repair `.env` loading in `run.sh`

**Files:**
- Modify: `scripts/run.sh`

- [ ] **Step 1: Replace the fragile `xargs` export with shell-native sourcing**

```bash
# 加载 .env
if [ -f "$REPO_DIR/.env" ]; then
    set -a
    . "$REPO_DIR/.env"
    set +a
fi
```

- [ ] **Step 2: Validate the shell script syntax**

Run: `bash -n scripts/run.sh`

Expected: no output and exit code `0`.

- [ ] **Step 3: Run a focused shell smoke check for values with spaces**

Run:

```bash
tmp_env="$(mktemp)" && \
printf 'TEST_VALUE="hello world"\n' > "$tmp_env" && \
bash -lc 'set -a; . "'"$tmp_env"'"; set +a; [ "$TEST_VALUE" = "hello world" ]'
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Commit the shell fix**

```bash
git add scripts/run.sh
git commit -m "fix: load env file safely in run script"
```

### Task 6: Run full verification

**Files:**
- Verify: `scripts/fetch_web.py`
- Verify: `scripts/db.py`
- Verify: `scripts/fetch_rss.py`
- Verify: `scripts/run.sh`
- Verify: `test/test_fetch_web.py`
- Verify: `test/test_db.py`
- Verify: `test/test_fetch_rss.py`
- Verify: `test/test_migrate.py`

- [ ] **Step 1: Run Ruff**

Run: `uv run ruff check scripts/`

Expected: `All checks passed!`

- [ ] **Step 2: Run the full pytest suite**

Run: `uv run pytest test/`

Expected: all repository tests pass, including the new web and DB regressions.

- [ ] **Step 3: Run Pyright**

Run: `uv run pyright scripts test`

Expected: `0 errors, 0 warnings, 0 informations`

- [ ] **Step 4: Commit any final follow-up adjustments from verification**

```bash
git add scripts/fetch_web.py scripts/db.py scripts/run.sh test/test_fetch_web.py test/test_db.py
git commit -m "chore: finalize review fixes verification"
```
