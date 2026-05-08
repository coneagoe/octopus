#!/usr/bin/env python3
"""知乎用户回答抓取器 — Playwright 渲染"""

import asyncio
import json
import os
import re
from datetime import date
from typing import Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scripts.db import Article, get_session, init, utcnow_naive
from scripts.playwright_setup import is_chromium_ready
from scripts.url_normalize import make_entry_hash, normalize_url

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


class FetchZhihuError(RuntimeError):
    """知乎抓取失败。"""


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _load_zhihu_credentials() -> Tuple[str, str]:
    username = os.environ.get("ZHIHU_USERNAME", "").strip()
    password = os.environ.get("ZHIHU_PASSWORD", "").strip()
    if not username:
        raise FetchZhihuError("缺少 ZHIHU_USERNAME，无法自动登录知乎")
    if not password:
        raise FetchZhihuError("缺少 ZHIHU_PASSWORD，无法自动登录知乎")
    return username, password


def _get_storage_state_path() -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "..",
        "output",
        "zhihu_storage_state.json",
    )


def _extract_item_date(text: str, today: str) -> Optional[str]:
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if date_match:
        return date_match.group(1)

    if re.search(r'昨天', text):
        return None

    if re.search(r'(刚刚|今天|\d+\s*分钟前|\d+\s*小时前)', text):
        return today

    return None


def _extract_answer_items(html: str, today: str, source_name: str = "") -> list:
    """从知乎主页 HTML 中提取当天的回答条目"""
    items = []
    soup = BeautifulSoup(html, 'html.parser')

    # 查找所有包含回答的 List-item 块
    for block in soup.select('.List-item'):
        # 提取回答链接
        link = block.select_one('a[href*="/question/"]')
        if not link:
            continue
        href = link.get('href')
        if not isinstance(href, str):
            continue
        if '/answer/' not in href:
            continue
        answer_url = urljoin("https://www.zhihu.com", href)

        # 提取时间：仅使用时间节点，避免标题/摘要文本污染日期判断
        time_elem = block.select_one('.AnswerItem-time')
        if time_elem is None:
            continue
        item_date = _extract_item_date(time_elem.get_text(strip=True), today)
        if item_date is None:
            continue
        if item_date != today:
            continue

        # 提取标题
        title = link.get_text(strip=True)

        summary_elem = block.select_one('.AnswerItem-summary') or block.find('p')
        if summary_elem:
            summary = summary_elem.get_text(strip=True)
            if not summary:
                summary = None
        else:
            summary = None

        if not summary:
            # 实在拿不到摘要就用标题代替
            summary = f"回答了问题：{title}"

        items.append({
            "title": title,
            "url": answer_url,
            "published": item_date,
            "summary": summary,
            "source": source_name,
            "source_type": "zhihu",
        })

    return items


def _page_requires_login(status_code: Optional[int], final_url: str, html: str) -> bool:
    normalized_url = (final_url or "").lower()
    page_text = html.lower()

    if status_code == 403:
        return True

    if any(token in normalized_url for token in ("/signin", "/login", "/captcha")):
        return True

    blocked_markers = [
        "登录",
        "注册",
        "安全验证",
        "请完成验证",
    ]
    return (
        "list-item" not in page_text
        and any(marker in html for marker in blocked_markers)
    )


async def _fetch_page_content(url: str, storage_state_path: Optional[str] = None) -> dict:
    """用 Playwright 获取渲染后的页面内容"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        context_kwargs = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
                "locale": "zh-CN",
        }
        if storage_state_path and os.path.exists(storage_state_path):
            context_kwargs["storage_state"] = storage_state_path
        try:
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            response = await page.goto(url, timeout=30000)
            await page.wait_for_timeout(5000)
            html = await page.content()
            final_url = page.url
            return {
                "status_code": response.status if response else None,
                "final_url": final_url,
                "html": html,
            }
        finally:
            await browser.close()


def fetch_zhihu_user(user_id: str, name: str, db_path: Optional[str] = None) -> list:
    """抓取指定知乎用户的当天回答，返回新增条目列表"""
    ready, message = is_chromium_ready()
    if not ready:
        raise FetchZhihuError(message)

    url = f"https://www.zhihu.com/people/{user_id}"
    print(f"  抓取知乎用户: {name} ({url})")

    page_result = asyncio.run(_fetch_page_content(url))
    if isinstance(page_result, dict):
        html = page_result.get("html", "")
    else:
        html = page_result
    if not html:
        raise FetchZhihuError("获取页面内容失败")

    today = date.today().isoformat()
    items = _extract_answer_items(html, today, source_name=name)
    print(f"    -> 当天({today})回答: {len(items)} 条")

    if db_path and items:
        init(db_path)
        sess = get_session()
        now = utcnow_naive()
        new_items = []
        try:
            for item in items:
                try:
                    normalized = normalize_url(item["url"])
                except ValueError:
                    print(f"    -> 跳过非法URL: {item['url']}")
                    continue

                entry_hash = make_entry_hash(normalized)
                existing = sess.get(Article, entry_hash)
                if existing:
                    existing.last_seen = now
                    sess.commit()
                    continue

                article = Article(
                    entry_hash=entry_hash,
                    normalized_url=normalized,
                    url=item["url"],
                    title=item["title"],
                    author=name,
                    source=name,
                    source_type="zhihu",
                    published=item["published"],
                    summary=item["summary"],
                    first_fetched=now,
                    last_seen=now,
                )
                sess.add(article)
                sess.commit()
                new_items.append(item)
        finally:
            sess.close()

        print(f"    -> 新增条目: {len(new_items)} 条")
        return new_items

    return items


def main():
    config = load_config()
    zhihu_users = config.get("sources", {}).get("zhihu", [])

    if not zhihu_users:
        print("[知乎采集] 未配置用户，跳过")
        return

    print(f"[知乎采集] 共 {len(zhihu_users)} 个用户")

    db_path = os.environ.get("OCTOPUS_DB")
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "..", "output", "octopus.db")

    all_entries = []
    had_failure = False
    for user in zhihu_users:
        user_id = user.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            continue
        name = user.get("name")
        if not isinstance(name, str) or not name:
            name = user_id
        try:
            entries = fetch_zhihu_user(user_id, name, db_path=db_path)
        except FetchZhihuError as exc:
            had_failure = True
            print(f"  抓取知乎用户失败: {name} - {exc}")
            continue
        except Exception as exc:
            had_failure = True
            print(f"  抓取知乎用户异常: {name} - {exc}")
            continue
        all_entries.extend(entries)

    cache_file = os.path.join(os.path.dirname(__file__), "..", "output", "zhihu_cache.json")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"[知乎采集] 完成，共 {len(all_entries)} 条新条目")
    if had_failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
