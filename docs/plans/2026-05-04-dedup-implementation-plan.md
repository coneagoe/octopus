# 去重实现计划

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** 实现 URL 去重机制，SQLite 存储，新增文章只出现一次

**Architecture:** fetch 层负责增量写入 SQLite 并过滤重复 URL，summarize 层消费纯新条目列表生成日报

**Tech Stack:** SQLAlchemy (ORM), SQLite, pytest (monkeypatch)

---

## Task 1: 创建 `scripts/db.py` — 模型 + 连接管理

**Files:**
- Create: `scripts/db.py`
- Test: `test/test_db.py`

**Step 1: Write the failing test**

```python
# test/test_db.py
import pytest
import sys, os, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts import db

class TestArticleModel:
    def test_article_url_is_primary_key(self, monkeypatch):
        from scripts.db import Article
        assert Article.__tablename__ == 'articles'

    def test_article_has_expected_columns(self, monkeypatch):
        from scripts.db import Article
        cols = [c.name for c in Article.__table__.columns]
        assert 'url' in cols
        assert 'title' in cols
        assert 'source' in cols
        assert 'source_type' in cols
        assert 'first_fetched' in cols

class TestDbSession:
    def test_get_session_returns_session(self, tmp_path):
        db_path = tmp_path / "test.db"
        sess = db.get_session(str(db_path))
        assert sess is not None
        sess.close()
```

**Step 2: Run test — confirm it fails**
```bash
uv run pytest test/test_db.py -v
```
Expected: FAIL — "No module named 'scripts.db'"

**Step 3: Write minimal implementation**

```python
# scripts/db.py
"""数据库管理 — SQLite + SQLAlchemy"""

from datetime import datetime
from sqlalchemy import create_engine, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class Article(Base):
    """文章记录表"""
    __tablename__ = 'articles'

    url = Column(String(2048), primary_key=True)
    title = Column(String(1024), nullable=False)
    source = Column(String(256), nullable=False)
    source_type = Column(String(32))  # 'rss' / 'web' / 'feishu' / 'email'
    published = Column(String(256))
    summary = Column(Text)
    first_fetched = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyEntry(Base):
    """日报条目表"""
    __tablename__ = 'daily_entries'

    date = Column(String(10), primary_key=True)  # YYYY-MM-DD
    url = Column(String(2048), primary_key=True)
    commentary = Column(Text, default='')

    # 联合主键 (date, url)


_engine = None
_Session = None


def init(db_path: str):
    """初始化数据库连接"""
    global _engine, _Session
    _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    _Session = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)


def get_session():
    """获取数据库会话"""
    if _Session is None:
        db_path = os.path.join(os.path.dirname(__file__), '..', 'output', 'octopus.db')
        init(db_path)
    return _Session()
```

**Step 4: Run test — confirm it passes**
```bash
uv run pytest test/test_db.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/db.py test/test_db.py && git commit -m "feat: add SQLAlchemy db module with Article/DailyEntry models"
```

---

## Task 2: 迁移脚本 `scripts/migrate.py` — JSON → SQLite

**Files:**
- Create: `scripts/migrate.py`
- Modify: `scripts/config.yaml`（加入迁移配置，可选）
- Test: `test/test_migrate.py`

**Step 1: Write the failing test**

```python
# test/test_migrate.py
import pytest, sys, os, json, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class TestMigrateJsonToDb:
    def test_migrate_rss_cache_inserts_all_entries(self, tmp_path, monkeypatch):
        # Create fake rss_cache.json
        rss_cache = tmp_path / "rss_cache.json"
        rss_cache.write_text(json.dumps([
            {"title": "Test", "url": "https://example.com/1", "source": "TestSrc", "summary": "", "published": ""},
            {"title": "Test2", "url": "https://example.com/2", "source": "TestSrc", "summary": "", "published": ""}
        ]))

        # Mock load_config to return test paths
        monkeypatch.setattr("scripts.migrate.load_json", lambda p: json.loads(rss_cache.read_text()))

        # Run migration and verify db has 2 records
        # (具体验证逻辑看实现)
```

**Step 2: Run test — confirm it fails**
```bash
uv run pytest test/test_migrate.py -v
```
Expected: FAIL

**Step 3: Write minimal implementation**

[按 TDD 流程执行]

**Step 4: Run test — confirm it passes**

**Step 5: Commit**

---

## Task 3: 修改 `fetch_rss.py` — 集成去重逻辑

**Files:**
- Modify: `scripts/fetch_rss.py`
- Test: `test/test_fetch_rss.py`（重写）
- Remove: `test/test_fetch_rss.py` 的旧测试（改用真实 DB）

**Step 1: Write the failing test**

```python
# test/test_fetch_rss.py
import pytest, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class TestFetchRssWithDedup:
    def test_fetch_rss_returns_only_new_entries(self, monkeypatch, tmp_path):
        from scripts.db import init as db_init, Article
        from scripts.fetch_rss import fetch_rss

        # Initialize test DB
        db_path = tmp_path / "test.db"
        db_init(str(db_path))

        # Pre-insert an existing URL
        sess = db.get_session()
        existing = Article(url="https://example.com/existing", title="Existing", source="Test", source_type="rss")
        sess.add(existing)
        sess.commit()

        # Mock feedparser to return one old + one new
        fake_feed = type("F", (), {
            "entries": [
                {"title": "Existing", "link": "https://example.com/existing", "published": "", "summary": ""},
                {"title": "New Article", "link": "https://example.com/new", "published": "", "summary": ""}
            ]
        })()
        monkeypatch.setattr("feedparser.parse", lambda url: fake_feed)

        entries = fetch_rss("https://example.com/rss", "TestSource", db_path=str(db_path))

        # Should only return the new one
        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.com/new"
```

**Step 2: Run test — confirm it fails**

**Step 3: Write minimal implementation**

修改 `fetch_rss.py` 的 `fetch_rss()` 函数，增加 `db_path` 参数，写入 SQLite 并过滤重复。

**Step 4: Run test — confirm it passes**

**Step 5: Commit**

---

## Task 4: 修改 `summarize.py` — 适配新的 cache 结构

**Files:**
- Modify: `scripts/summarize.py`
- Test: `test/test_summarize.py`（已有，验证仍然通过即可）

此任务主要是确保 `load_cache()` 能正常工作，cache 文件格式不变（仍然是 JSON）。

**Step 1: 运行现有 UT 确认功能未破坏**
```bash
uv run pytest test/test_summarize.py -v
```
Expected: PASS

**Step 2: 如需调整，修改后重新运行**

**Step 3: Commit**

---

## Task 5: 修改 `fetch_web.py` — 同上去重逻辑

**Files:**
- Modify: `scripts/fetch_web.py`
- Test: `test/test_fetch_web.py`（重写）
- Test: `test/test_db.py`（补充 fetch_web 相关 UT）

**Step 1-5: 同 Task 3 流程**

---

## Task 6: 修改 `run.sh` — 适配新的 DB 路径

**Files:**
- Modify: `scripts/run.sh`

确保 `run.sh` 不需要大改（fetch/summarize 的调用方式不变），但检查 DB 文件路径正确。

**Step 1: 验证 run.sh 能正常执行**
```bash
cd /home/admin/octopus && bash scripts/run.sh 2>&1 | head -20
```

**Step 2: 如有问题，修复**

**Step 3: Commit**

---

## 执行选项

Plan saved to `docs/plans/2026-05-04-dedup-implementation-plan.md`. Two execution options:

1. **Subagent-Driven** — 我 dispatch 一个 sub-agent 按 Task 顺序执行，TDD 模式，完成一个 review 一个
2. **Manual** — 你自己按 Task 顺序执行

选哪个？