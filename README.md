# Octopus - 信息聚合系统

每天自动采集 RSS、网站、飞书、邮件等来源，生成带摘要的每日笔记。

## 目录结构

```
octopus/
├── scripts/
│   ├── run.sh              # 入口脚本（cron 调用）
│   ├── fetch_rss.py        # RSS 采集
│   ├── fetch_web.py        # 网站抓取
│   ├── fetch_feishu.py     # 飞书消息
│   ├── fetch_email.py      # 邮件
│   ├── summarize.py        # AI 摘要生成
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

2. 在 `scripts/config.yaml` 中配置要采集的信息源

## 定时任务

```bash
# 每天早 8 点和晚 8 点运行
0 8 * * * /home/admin/octopus/scripts/run.sh morning >> /home/admin/octopus/logs/morning.log 2>&1
0 20 * * * /home/admin/octopus/scripts/run.sh evening >> /home/admin/octopus/logs/evening.log 2>&1
```

## 信息源配置说明

详见 `scripts/config.yaml` 中的注释。