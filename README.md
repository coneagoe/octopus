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
│   └── daily/              # 每日输出（按运行时刻拆分为 YYYY-MM-DD-AM.md / YYYY-MM-DD-PM.md）
├── .env                     # 敏感信息（不在 Git 中）
├── .gitignore
└── README.md
```

## 配置

1. 复制 `.env.example` 为 `.env`，填入：
   - `GITHUB_PAT`：GitHub Personal Access Token
   - `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书应用凭证（如需）
   - `ZHIHU_USERNAME` / `ZHIHU_PASSWORD`：知乎登录凭证，用于首次登录和会话刷新
   - `TZ`：时区，例如 `Asia/Shanghai`。Docker 模式下，AM/PM 路由会跟随容器内的 `date` 结果，因此这里要设置为你期望的本地时区。

2. 在 `scripts/config.yaml` 中配置要采集的信息源

## 初始化

安装 Python 依赖后，如需启用知乎抓取，请额外执行：

```bash
uv run python scripts/playwright_setup.py --install-if-missing
```

如果 Playwright Chromium 尚未安装，知乎抓取会输出清晰错误提示，并指向上面的 setup 命令；日常 `scripts/run.sh` 不会自动下载安装浏览器。
知乎的 Playwright 登录状态会保存到 `output/zhihu_storage_state.json`，仅保留在本地，不会提交到 Git。状态过期或需要额外验证时，脚本会重试登录一次；只有当本次知乎抓取完全失败、没有任何用户成功拉取时，才会保留旧的 `output/zhihu_cache.json` 并记录错误原因。

## 定时任务

`output/daily/` 下的日报按运行时刻拆分为 `YYYY-MM-DD-AM.md` 和 `YYYY-MM-DD-PM.md`。现有 `scripts/run.sh morning` / `scripts/run.sh evening` 示例继续可用；文件写入目标由实际运行时刻决定：12:00 前写 `AM`，12:00 及以后写 `PM`。

### 方式 A：直接运行（无 Docker）

```bash
# 每天早 8 点和晚 8 点运行
0 8 * * * /home/admin/octopus/scripts/run.sh morning >> /home/admin/octopus/logs/morning.log 2>&1
0 20 * * * /home/admin/octopus/scripts/run.sh evening >> /home/admin/octopus/logs/evening.log 2>&1
```

### 方式 B：使用 Docker 运行（推荐）

Docker 封装了所有 Python 依赖和 Playwright Chromium，环境更一致，换机时只需迁移仓库、`.env` 和 cron 配置。
注意：Docker 模式下，`scripts/run.sh` 通过容器内的 `date` 判断上午/下午，因此必须确保 `/home/admin/octopus/.env` 里的 `TZ` 已设置正确；`docker run --env-file /home/admin/octopus/.env` 会把它传入容器。

**首次构建镜像（仅需一次，更新依赖后重新构建）：**

```bash
cd /home/admin/octopus
docker build -t octopus:latest .
```

**cron 配置：**

```bash
# 每天早 8 点和晚 8 点运行（Docker 模式）
0 8 * * * docker run --rm --env-file /home/admin/octopus/.env -v /home/admin/octopus:/app -w /app --user "$(id -u):$(id -g)" octopus:latest bash scripts/run.sh morning >> /home/admin/octopus/logs/morning.log 2>&1
0 20 * * * docker run --rm --env-file /home/admin/octopus/.env -v /home/admin/octopus:/app -w /app --user "$(id -u):$(id -g)" octopus:latest bash scripts/run.sh evening >> /home/admin/octopus/logs/evening.log 2>&1
```

> `--user "$(id -u):$(id -g)"` 使容器以宿主用户身份写文件，避免 `output/` 和 `logs/` 产生 root 属主文件。
> cron 中无法展开 `$(id -u)`，建议提前查好 UID/GID（`id -u && id -g`）后直接填入数字，例如 `--user 1000:1000`。

**手动验证一次运行：**

```bash
docker run --rm \
  --env-file /home/admin/octopus/.env \
  -v /home/admin/octopus:/app \
  -w /app \
  --user "$(id -u):$(id -g)" \
  octopus:latest bash scripts/run.sh morning
```

**换机迁移步骤：**

1. 在新机器上安装 Docker
2. `git clone` 仓库并配置 `.env`
3. 执行 `docker build -t octopus:latest .` 重新构建镜像
4. 设置 cron（参照上方配置）

## 信息源配置说明

详见 `scripts/config.yaml` 中的注释。
