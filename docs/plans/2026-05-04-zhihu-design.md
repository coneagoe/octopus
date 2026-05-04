# 知乎用户回答抓取设计文档 — 2026-05-04

## 目标

抓取指定知乎用户当天的回答，生成带 AI 点评的日报条目。

## 设计决策

| 决策项 | 选择 |
|--------|------|
| 抓取方式 | Playwright（浏览器自动化，JS 渲染内容） |
| 目标页面 | 用户主页（`https://www.zhihu.com/people/{user_id}`） |
| 抓取范围 | 当天（00:00 ~ 23:59）的回答，精确到日期 |
| 是否需要登录 | 否 — 主页面公开内容可用 |
| 反爬对策 | 伪装 UA、禁用自动化检测、跳过图片/字体等无关资源 |

## 技术方案

### 为什么不用 requests

知乎页面是 **JS 渲染**的，直接 `requests.get()` 返回的是空壳 HTML（内容在 JS 执行后才注入）。必须用无头浏览器。

### 为什么选 Playwright

- 支持 Python async，资源消耗比 Selenium 低
- `networkidle` 等待机制比固定 `sleep` 更稳定
- 支持拦截请求（跳过图片/字体/CDN 资源，大幅提速）
- 社区活跃、文档完善

### 抓取流程

```
1. Playwright 打开用户主页（等待 JS 渲染完成）
2. 解析页面 HTML，提取"当天"的回答条目：
   - 回答的问题标题
   - 回答的链接（/question/xxx/answer/yyy）
   - 回答摘要（页面可见的预览文本）
   - 发布时间（精确到日期）
3. 对每个回答 URL，发起新请求获取回答正文（可选，看需求）
4. 与现有去重系统对接：URL → normalized → hash → DB 查重
5. 通过现有 fetch_rss/fetch_web 的去重流程写入 DB
```

### 字段映射

从知乎主页提取的字段，映射到 `articles` 表：

| 知乎字段 | articles 字段 | 说明 |
|----------|--------------|------|
| 主页 URL 中的 user_id | entry_hash 的一部分 | `hash(normalized_url + '')` |
| 回答的问题标题 | title | |
| 回答链接 | url | 原始 zhihu URL |
| 页面可见摘要 | summary | 前 500 字 |
| 回答时间（当天） | published | YYYY-MM-DD |
| 'zhihu' | source | |
| 'zhihu' | source_type | |

### 配置文件格式

```yaml
sources:
  zhihu:
    - user_id: "yang-lei-96-72"   # 知乎 URL 中的 user_id 部分
      name: "Deep Van"              # 显示名称
```

## 数据库设计（无需新增字段）

复用现有的 `articles` 表，source_type='zhihu'，其余字段不变。

## 性能优化

- 拦截图片、CSS、字体、广告 CDN：约节省 60-70% 加载时间
- 只抓主页，不进入每个回答详情（摘要已在主页可见）
- 如需正文，通过 `?share=1` 等免登录短格式获取（可选）

## 限制

- 只能抓取用户主页**当前可见范围**的回答（知乎默认展示最近 20-30 条）
- 回答详情正文需要额外请求，但摘要已足够用于投资判断
- 频率限制：单用户 2-3 次/分钟以内安全

## 实现顺序

1. `scripts/fetch_zhihu.py` — Playwright 抓取逻辑
2. `config.yaml` — 新增 zhihu 配置节
3. `scripts/run.sh` — 加入知乎采集步骤
4. UT：`test/test_fetch_zhihu.py`

## 不做

- 不做深度历史爬取（只当天）
- 不登录
- 不抓评论/私信
- 不抓回答正文（摘要已够用）