#!/usr/bin/env python3
"""
知乎 Session 导入工具

使用方法：
  1. 在浏览器中登录 https://www.zhihu.com
  2. 打开 DevTools → Application → Cookies → https://www.zhihu.com
  3. 安装 Chrome 扩展 "EditThisCookie" 或 "Cookie-Editor"，导出 JSON 格式的 cookies
  4. 把导出的 JSON 内容保存到文件（例如 /tmp/zhihu_cookies.json）
  5. 运行本脚本：
       uv run python scripts/zhihu_import_cookies.py --input /tmp/zhihu_cookies.json

  或者，可以直接粘贴浏览器 DevTools 里 Network 面板的 Cookie 请求头：
       uv run python scripts/zhihu_import_cookies.py --cookie-header "z_c0=xxx; _xsrf=yyy; ..."

   导入后，ZHIHU_COOKIES 会自动写入 .env，下次运行无需重复导入。
"""

from __future__ import annotations

import argparse
import json
import os
import time


OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "zhihu_storage_state.json")
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def _update_env_file(env_path: str, cookie_header: str) -> None:
    """在 .env 文件中写入或更新 ZHIHU_COOKIES=... 行"""
    key = "ZHIHU_COOKIES"
    new_line = f'{key}={cookie_header}\n'

    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                lines[i] = new_line
                updated = True
                break
        if not updated:
            lines.append(new_line)
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    else:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(new_line)


def _parse_cookie_header(header: str) -> list[dict]:
    """把 'name1=val1; name2=val2' 格式的请求头转为 cookie 列表"""
    cookies = []
    for part in header.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".zhihu.com",
            "path": "/",
            "expires": int(time.time()) + 86400 * 30,
            "httpOnly": False,
            "secure": True,
            "sameSite": "None",
        })
    return cookies


def _parse_extension_export(data: list[dict]) -> list[dict]:
    """
    把 EditThisCookie / Cookie-Editor 导出的 JSON 转换为 Playwright 格式。
    两种扩展的字段名略有不同，这里做兼容处理。
    """
    cookies = []
    for c in data:
        # EditThisCookie 用 expirationDate，Cookie-Editor 用 expires
        expires = c.get("expirationDate") or c.get("expires") or (time.time() + 86400 * 30)
        same_site = c.get("sameSite", "None")
        # Playwright 要求 sameSite 为 "Strict" | "Lax" | "None"
        if same_site not in ("Strict", "Lax", "None"):
            same_site = "None"
        cookies.append({
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ".zhihu.com"),
            "path": c.get("path", "/"),
            "expires": int(expires),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
            "sameSite": same_site,
        })
    return cookies


def main():
    parser = argparse.ArgumentParser(description="将浏览器 Cookies 导入为知乎 Playwright session")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", metavar="FILE", help="Cookie-Editor / EditThisCookie 导出的 JSON 文件路径")
    group.add_argument("--cookie-header", metavar="STR", help="浏览器 Network 面板中 Cookie 请求头的值")
    parser.add_argument("--output", default=OUTPUT_PATH, help=f"输出路径（默认 {OUTPUT_PATH}）")
    parser.add_argument("--env-file", default=ENV_PATH, help=f".env 文件路径（默认 {ENV_PATH}）")
    parser.add_argument("--no-env", action="store_true", help="不更新 .env 文件")
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            parser.error("--input 文件必须是 JSON 数组（cookie 列表）")
        cookies = _parse_extension_export(raw)
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    else:
        cookie_header = args.cookie_header
        cookies = _parse_cookie_header(cookie_header)

    if not cookies:
        print("错误：未解析到任何 cookie，请检查输入格式")
        raise SystemExit(1)

    # 确保包含关键登录 cookie
    names = {c["name"] for c in cookies}
    key_cookies = {"z_c0", "_xsrf"}
    missing = key_cookies - names
    if missing:
        print(f"警告：未找到关键 cookie：{missing}，session 可能无效")

    state = {"cookies": cookies, "origins": []}
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"已写入 {len(cookies)} 个 cookie 到 {args.output}")

    if not args.no_env:
        _update_env_file(args.env_file, cookie_header)
        print(f"已更新 ZHIHU_COOKIES 到 {args.env_file}")

    print("建议立即运行 bash run_zhihu.sh 验证 session 是否有效")


if __name__ == "__main__":
    main()
