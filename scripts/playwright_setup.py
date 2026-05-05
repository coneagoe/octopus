#!/usr/bin/env python3
"""Playwright Chromium 环境检查与安装。"""

import argparse
import subprocess
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - exercised via behavior, not import mechanics
    sync_playwright = None


def missing_browser_message() -> str:
    return (
        "Chromium 浏览器未安装，请先执行："
        "uv run python scripts/playwright_setup.py --install-if-missing"
    )


def missing_package_message() -> str:
    return "Playwright Python 依赖未安装，请先执行：uv sync"


def is_chromium_ready():
    if sync_playwright is None:
        return False, missing_package_message()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True, ""
    except Exception as exc:
        return False, f"{missing_browser_message()}（原始错误: {exc}）"


def install_chromium() -> None:
    print("开始安装 Playwright Chromium...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )
    print("Playwright Chromium 安装完成")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="检查或安装 Playwright Chromium")
    parser.add_argument("--check", action="store_true", help="仅检查 Chromium 是否可用")
    parser.add_argument(
        "--install-if-missing",
        action="store_true",
        help="Chromium 缺失时自动安装",
    )
    args = parser.parse_args(argv)

    ready, message = is_chromium_ready()
    if ready:
        print("Playwright Chromium 已就绪")
        return 0

    print(message)
    if args.install_if_missing:
        try:
            install_chromium()
            return 0
        except subprocess.CalledProcessError:
            print("安装 Chromium 失败")
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
