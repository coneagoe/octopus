# Octopus 信息聚合系统 — 设计文档
**日期:** 2026-05-03
**状态:** 进行中

---

## 1. 项目概述

**目标:** 每天自动从多个信息来源抓取内容，生成带 AI 摘要和点评的 Markdown 格式日报，保存到 GitHub 仓库，Obsidian 本地通过 Git 插件同步。

**核心价值:**
- 单一入口看到所有信息源汇总
- AI 辅助过滤噪音，快速判断内容价值
- 持久化存档，回溯方便

---

## 2. 信息源（按优先级）

### P0 — 必须实现
| 类别 | 方式 | 说明 |
|------|------|------|
| RSS 订阅 | 定时抓取 feed | 用户配置 URL 列表 |
| 网站文章 | HTTP 抓取 + CSS 提取 | 支持 selector 配置 |

### P1 — 可选，后续实现
| 类别 | 方式 | 说明 |
|------|------|------|
| 飞书群消息 | 飞书开放 API | 需要应用凭证 |
| 邮件 | IMAP | 需要邮箱 + App Password |

---

## 3. 每日运行流程

```
06:00 / 18:00 (可选早晚各一次)
    │
    ├─ git pull（拉最新脚本）
    │
    ├─ fetch_rss.py      → output/rss_cache.json
    ├─ fetch_web.py       → output/web_cache.json
    ├─ fetch_feishu.py    → output/feishu_cache.json （可选）
    ├─ fetch_email.py    → output/email_cache.json  （可选）
    │
    ├─ summarize.py      → output/daily/YYYY-MM-DD.md
    │
    └─ git push          → GitHub
                              ↓
                         Obsidian Git 插件自动拉取
```

---

## 4. 输出格式

每天一个文件: `output/daily/YYYY-MM-DD.md`

```markdown
# 信息聚合日报 2026-05-03

> 生成时间: 2026-05-03 06:00:00

## RSS 订阅

### [文章标题](url)
- 来源: 博客名
- 摘要: 文章摘要...
- 点评: 我觉得这篇文章...

## 网站精选

### [文章标题](url)
- 来源: 网站名
- 摘要: ...
- 点评: ...

---

*由 Octopus 信息聚合系统自动生成*
```

---

## 5. 关键技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 定时任务 | cron | 服务器已内置，无需额外安装 |
| RSS 解析 | `feedparser` | Python 标准库，轻量 |
| 网页抓取 | `requests` + `BeautifulSoup` | 成熟稳定 |
| AI 摘要 | OpenClaw 内置模型 (MiniMax) | 无需额外 API Key |
| 存储 | JSON 缓存 + Markdown 输出 | 简单透明，易于调试 |
| Git 推送 | 直接 git CLI | 轻量，无需 GitHub API 封装 |

---

## 6. 仓库结构

```
octopus/
├── scripts/
│   ├── run.sh              # 入口，cron 调用
│   ├── fetch_rss.py        # RSS 采集
│   ├── fetch_web.py        # 网站抓取
│   ├── fetch_feishu.py     # 飞书（可选）
│   ├── fetch_email.py      # 邮件（可选）
│   ├── summarize.py        # 汇总 + AI 摘要
│   └── config.yaml         # 信息源配置
├── output/
│   ├── *.json              # 采集缓存
│   └── daily/              # 每日输出
├── docs/plans/             # 设计文档
├── .env                    # 敏感信息（PAT 等）
├── .gitignore
└── README.md
```

---

## 7. 安全考量

- `.env` 不提交 Git（已在 `.gitignore`）
- PAT 只用于 git push，不写死在脚本里
- 飞书/邮件凭证按需提供，最小权限原则

---

## 8. 待确认事项

1. ✅ 信息流向：定时采集，非实时监控
2. ✅ AI 点评风格：带观点
3. ⬜ 飞书群具体是哪些？（群 ID 列表）
4. ⬜ 邮件的 IMAP 配置（如果需要）
5. ⬜ RSS 订阅源列表（初期有哪些？）

---

## 9. 后续扩展方向（YAGNI，暂时不做）

- 全文搜索
- 按来源/时间过滤
- 推送通知（不止每日笔记）
- 增量更新（对比昨天新增加了哪些）