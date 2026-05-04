# 去重设计文档 — 2026-05-04

## 目标

解决 RSS 和网页抓取重复采集问题：同一 URL 的文章只出现在它首次被抓到的那个日期，之后不再出现。

## 设计决策

| 决策项 | 选择 |
|--------|------|
| 去重粒度 | 严格去重：同一 URL 只首次出现 |
| 去重逻辑位置 | 混合：fetch 层快速过滤 + summarize 层最终兜底 |
| 存储 | SQLite（SQLAlchemy ORM） |
| 历史数据迁移 | 保留 JSON cache 逐步迁移，不再新增 JSON 文件 |

## 架构概览

```
fetch_rss.py / fetch_web.py
       │
       ▼
   SQLite DB ◄── 增量写入，只 insert 新 URL
       │
       ▼
   返回新条目列表（不重复）
       │
       ▼
summarize.py ──► output/daily/YYYY-MM-DD.md
```

## 数据库设计

### SQLite + SQLAlchemy

DB 文件路径：`output/octopus.db`

#### articles 表（去重 + 全量记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| url | String(2048) | 主键，URL 唯一 |
| title | String(1024) | 文章标题 |
| source | String(256) | 来源名称（36氪、爱范儿等） |
| source_type | String(32) | 'rss' / 'web' / 'feishu' / 'email' |
| published | String(256) | 发布时间（RSS 原始时间） |
| summary | Text | 摘要内容 |
| first_fetched | DateTime | 首次抓取时间 |
| last_seen | DateTime | 最后出现时间 |

#### daily_entries 表（日报记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| date | String(10) | YYYY-MM-DD |
| url | String(2048) | 关联 articles.url |
| commentary | Text | AI 生成点评 |
| primary_key | (date, url) | 联合主键 |

## 数据流

### fetch_rss.py（RSS 采集）

1. 读取 config.yaml 中的 RSS 源列表
2. 对每个源，feedparser.parse(url) 获取最新条目
3. **去重检查**：对每条 entry.url，查 SQLite 是否有记录
   - 有记录 → 更新 last_seen，跳过（不返回）
   - 无记录 → INSERT into articles，设置 first_fetched
4. **返回新条目列表**：`[{url, title, source, source_type, published, summary, is_new}]`
5. 采集完成后，将新条目写入 `output/rss_cache.json`（供 summarize 消费）
6. 同时写 daily_entries（date=今天, url, commentary 暂时留空，等 summarize 填充）

### fetch_web.py（网页抓取）

同上逻辑，source_type='web'，其余一致。

### summarize.py（日报生成）

1. 读取 `*_cache.json`（已是纯新条目，无需额外去重）
2. 对每条条目调用 MiniMax API 生成点评
3. 填充 daily_entries 的 commentary 字段
4. 生成 Markdown 日报

### migration（一次性）

首次部署时运行，把现有的 `*_cache.json` 内容迁移进 SQLite：
- 读取 `output/rss_cache.json`、`output/web_cache.json` 等
- INSERT 全部（URL 重复的由 DB 主键拦截）
- 迁移后保留 JSON 文件（不退删除，作为备份）

## 依赖

新增：
- `sqlalchemy`（加入 pyproject.toml dependencies）

## 目录结构

```
output/
├── octopus.db          # SQLite 数据库
├── daily/
│   ├── 2026-05-03.md
│   └── 2026-05-04.md
└── rss_cache.json      # fetch 输出，仅含新条目，summarize 消费后不清空（保留作日志）
```

## 测试策略

- fetch 去重：UT 用 monkeypatch 模拟 feedparser + 假 DB，验证新 URL 才 insert
- summarize 去重：UT 用 monkeypatch 模拟 cache 内容，验证生成的 md 只含预期条目
- migration：读取现有 JSON 文件，验证全部写入 DB，URL 重复的不会报错

## 实现顺序

1. 新增 `scripts/db.py` — SQLAlchemy 模型 + 连接管理
2. 修改 `fetch_rss.py` — 集成去重逻辑 + SQLite 写入
3. 新增迁移脚本 `scripts/migrate.py` — 一次性迁移现有 JSON → DB
4. 修改 `fetch_web.py` — 同上去重逻辑
5. 修改 `summarize.py` — 适配新的数据流
6. 更新 UT（新增 db UT 文件）
7. 更新 `docs/coding_rule.md`（如有必要）

## 不做

- 不删除现有的 `*_cache.json`（备份用途）
- 不引入 Redis 或独立数据库服务
- 不做 RSS 时间窗口过滤（已有严格去重够了）