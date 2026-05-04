# 知乎抓取实现计划

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** 通过 Playwright 抓取指定知乎用户的当天回答，写入 SQLite（复用现有去重系统）

**Architecture:** `fetch_zhihu.py` 负责 Playwright 渲染 + 提取当天条目，复用现有 `db.py` 去重，写入 `articles` 表

**Tech Stack:** Playwright (async), SQLAlchemy, pytest (monkeypatch)

---

## Task 1: 创建 `scripts/fetch_zhihu.py` — Playwright 渲染 + 提取逻辑

**Files:**
- Create: `scripts/fetch_zhihu.py`
- Modify: `scripts/config.yaml`（新增 zhihu 配置节）
- Test: `test/test_fetch_zhihu.py`

### Step 1: Write the failing test

```python
# test/test_fetch_zhihu.py
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class TestExtractAnswersFromProfile:
    def test_extracts_answer_items_from_html(self, monkeypatch):
        from scripts.fetch_zhihu import _extract_answer_items
        
        # Fake HTML with one today's answer
        today = "2026-05-04"
        fake_html = """
        <div class="Profile-main">
            <div class="List-item">
                <a href="/question/123/answer/456">测试问题</a>
                <span class="AnswerItem-time">2026-05-04</span>
                <p class="AnswerItem-summary">这是回答摘要</p>
            </div>
        </div>
        """
        
        items = _extract_answer_items(fake_html, today)
        assert len(items) == 1
        assert items[0]["title"] == "测试问题"
        assert items[0]["url"] == "https://www.zhihu.com/question/123/answer/456"
        assert items[0]["published"] == "2026-05-04"

    def test_filters_out_non_today_answers(self, monkeypatch):
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

    def test_handles_empty_html(self, monkeypatch):
        from scripts.fetch_zhihu import _extract_answer_items
        items = _extract_answer_items("", "2026-05-04")
        assert items == []
```

**Step 2: Run test — confirm it fails**
```bash
uv run pytest test/test_fetch_zhihu.py -v
```
Expected: FAIL — "No module named 'scripts.fetch_zhihu'"

### Step 3: Write minimal implementation

实现 `fetch_zhihu.py`，包含：
- `_extract_answer_items(html, today_date)` — 从 HTML 中用正则/字符串提取当天回答
- `fetch_zhihu_user(user_id, name, db_path=None)` — Playwright 打开主页，提取当天条目，写入 DB（复用现有去重）
- `main()` — 读取 config.yaml，遍历 zhihu 用户列表

### Step 4: Run test — confirm it passes

### Step 5: Commit
```bash
git add scripts/fetch_zhihu.py scripts/config.yaml test/test_fetch_zhihu.py && git commit -m "feat: add zhihu fetcher with Playwright (5 tests passing)"
```

---

## Task 2: 修改 `scripts/run.sh` — 加入知乎采集步骤

**Files:**
- Modify: `scripts/run.sh`

在 RSS/网站采集之后，飞书/邮件之前，加入知乎采集：
```bash
echo "[$(date)] 采集知乎..." | tee -a "$LOG_FILE"
uv run python "$SCRIPT_DIR/fetch_zhihu.py" >> "$LOG_FILE" 2>&1
```

**Step 1:** 修改 `run.sh`

**Step 2:** 验证不报错
```bash
bash scripts/run.sh 2>&1 | head -20
```

**Step 3:** Commit

---

## 执行选项

Plan saved. Two execution options:

1. **Subagent-Driven** — 我 dispatch sub-agent 按 Task 顺序执行
2. **Manual** — 你自己执行

选哪个？