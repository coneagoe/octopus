#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$REPO_DIR/output/daily"
DB_PATH="$REPO_DIR/output/octopus.db"
LOG_FILE="$REPO_DIR/logs/$(basename "$0" .sh)_$(date '+%Y%m%d_%H%M%S').log"

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$OUTPUT_DIR"

echo "[$(date)] 开始运行: $1" | tee -a "$LOG_FILE"

# 加载 .env
if [ -f "$REPO_DIR/.env" ]; then
    set -a
    . "$REPO_DIR/.env"
    set +a
fi

# 设置 DB 路径（供 fetch 脚本去重用）
export OCTOPUS_DB="$DB_PATH"
# 设置 PYTHONPATH（使 scripts 模块可导入）
export PYTHONPATH="$REPO_DIR"

# 定位 uv（cron 环境下 PATH 可能不完整）
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
if [ -z "$UV_BIN" ] && [ -x "$HOME/.local/bin/uv" ]; then
    UV_BIN="$HOME/.local/bin/uv"
fi
if [ -z "$UV_BIN" ]; then
    echo "[$(date)] 错误：未找到 uv，请先安装 uv 或设置 UV_BIN" | tee -a "$LOG_FILE"
    exit 1
fi

# 采集
echo "[$(date)] 采集 RSS..." | tee -a "$LOG_FILE"
"$UV_BIN" run python "$SCRIPT_DIR/fetch_rss.py" >> "$LOG_FILE" 2>&1

echo "[$(date)] 采集知乎..." | tee -a "$LOG_FILE"
if ! "$UV_BIN" run python "$SCRIPT_DIR/fetch_zhihu.py" >> "$LOG_FILE" 2>&1; then
    echo "[$(date)] 警告：知乎采集失败，继续执行后续流程" | tee -a "$LOG_FILE"
fi

echo "[$(date)] 采集网站..." | tee -a "$LOG_FILE"
"$UV_BIN" run python "$SCRIPT_DIR/fetch_web.py" >> "$LOG_FILE" 2>&1

echo "[$(date)] 采集飞书..." | tee -a "$LOG_FILE"
"$UV_BIN" run python "$SCRIPT_DIR/fetch_feishu.py" >> "$LOG_FILE" 2>&1

echo "[$(date)] 采集邮件..." | tee -a "$LOG_FILE"
"$UV_BIN" run python "$SCRIPT_DIR/fetch_email.py" >> "$LOG_FILE" 2>&1

# 合并数据生成今日摘要
TODAY=$(date '+%Y-%m-%d')
OUTPUT_FILE="$OUTPUT_DIR/${TODAY}.md"

echo "[$(date)] 生成摘要: $OUTPUT_FILE" | tee -a "$LOG_FILE"
"$UV_BIN" run python "$SCRIPT_DIR/summarize.py" --date "$TODAY" --output "$OUTPUT_FILE" >> "$LOG_FILE" 2>&1

# Git push
cd "$REPO_DIR"
echo "[$(date)] Git push..." | tee -a "$LOG_FILE"

if [ -z "${GITHUB_PAT:-}" ]; then
    echo "[$(date)] 错误：缺少 GITHUB_PAT，无法执行 Git push" | tee -a "$LOG_FILE"
    exit 1
fi

GIT_ASKPASS_SCRIPT="$SCRIPT_DIR/git_askpass.sh"
if [ ! -x "$GIT_ASKPASS_SCRIPT" ]; then
    echo "[$(date)] 错误：缺少可执行的 Git 认证脚本: $GIT_ASKPASS_SCRIPT" | tee -a "$LOG_FILE"
    exit 1
fi

REMOTE_URL="$(git remote get-url origin)"
case "$REMOTE_URL" in
    https://*)
        ;;
    *)
        echo "[$(date)] 错误：origin 远程地址必须为 HTTPS 才能使用 GITHUB_PAT" | tee -a "$LOG_FILE"
        exit 1
        ;;
esac

git add output/daily/
git commit -m "Daily update: $TODAY" || echo "Nothing to commit"
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="$GIT_ASKPASS_SCRIPT" git push origin main

echo "[$(date)] 完成!" | tee -a "$LOG_FILE"
