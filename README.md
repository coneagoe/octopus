# Octopus - 信息聚合系统

每天自动采集 RSS、知乎、网站、飞书、邮件等来源，生成带摘要的每日笔记。

## 目录结构

```
octopus/
├── scripts/
│   ├── run.sh              # 入口脚本（cron 调用）
│   ├── fetch_rss.py        # RSS 采集
│   ├── fetch_zhihu.py      # 知乎回答采集
│   ├── fetch_web.py        # 网站抓取
│   ├── fetch_feishu.py     # 飞书消息
│   ├── fetch_email.py      # 邮件
│   ├── summarize.py        # AI 摘要生成
│   ├── playwright_setup.py # Playwright Chromium 检查与安装
│   └── config.yaml         # 信息源配置
├── output/
│   └── daily/              # 每日输出
├── .env                     # 敏感信息（不在 Git 中）
├── .gitignore
└── README.md
```

## 配置

1. 复制 `.env.example` 为 `.env`，填入：
   - `GITHUB_PAT`：GitHub Personal Access Token
   - `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书应用凭证（如需）
   - `ZHIHU_USERNAME` / `ZHIHU_PASSWORD`：知乎登录凭证，用于首次登录和会话刷新

2. 在 `scripts/config.yaml` 中配置要采集的信息源

## 初始化

安装 Python 依赖后，如需启用知乎抓取，请额外执行：

```bash
uv run python scripts/playwright_setup.py --install-if-missing
```

如果 Playwright Chromium 尚未安装，知乎抓取会输出清晰错误提示，并指向上面的 setup 命令；日常 `scripts/run.sh` 不会自动下载安装浏览器。
知乎的 Playwright 登录状态会保存到 `output/zhihu_storage_state.json`，仅保留在本地，不会提交到 Git。状态过期或需要额外验证时，脚本会重试登录一次；只有当本次知乎抓取完全失败、没有任何用户成功拉取时，才会保留旧的 `output/zhihu_cache.json` 并记录错误原因。

## 定时任务

```bash
# 每天早 8 点和晚 8 点运行
0 8 * * * /home/admin/octopus/scripts/run.sh morning >> /home/admin/octopus/logs/morning.log 2>&1
0 20 * * * /home/admin/octopus/scripts/run.sh evening >> /home/admin/octopus/logs/evening.log 2>&1
```

## 信息源配置说明

详见 `scripts/config.yaml` 中的注释。
