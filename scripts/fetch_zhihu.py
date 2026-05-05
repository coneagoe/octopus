#!/usr/bin/env python3
"""知乎用户回答抓取器 — Playwright 渲染"""

import asyncio
import json
import os
import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scripts.db import Article, get_session, init, utcnow_naive
from scripts.playwright_setup import is_chromium_ready
from scripts.url_normalize import make_entry_hash, normalize_url

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _extract_answer_items(html: str, today: str) -> list:
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

        # 提取时间：找 YYYY-MM-DD 格式
        text = block.get_text()
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if not date_match:
            continue
        item_date = date_match.group(1)
        if item_date != today:
            continue

        # 提取标题
        title = link.get_text(strip=True)

        # 提取摘要：取链接后面跟随的文本
        summary = block.get_text(strip=True)
        # 去掉时间部分和标题，得到正文摘要
        summary = re.sub(r'\d{4}-\d{2}-\d{2}.*', '', summary)
        summary = re.sub(r'^' + re.escape(title), '', summary)
        summary = summary[:500].strip()

        items.append({
            "title": title,
            "url": answer_url,
            "published": item_date,
            "summary": summary,
            "source": "zhihu",
            "source_type": "zhihu",
        })

    return items


async def _fetch_page_content(url: str) -> str:
    """用 Playwright 获取渲染后的页面 HTML"""
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
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = await context.new_page()
        await page.route(
            "**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,webp}",
            lambda route: route.abort()
        )
        await page.route("**/analytics/**", lambda route: route.abort())
        try:
            response = await page.goto(url, timeout=30000)
            print(f"    -> 状态码: {response.status if response else 'None'}")
        except Exception as e:
            print(f"    -> 导航错误: {e}")
            await browser.close()
            return ""

        # 等待 JS 渲染
        await page.wait_for_timeout(5000)

        # 滚动触发懒加载
        for i in range(3):
            try:
                await page.evaluate(f"window.scrollTo(0, {i * 500})")
                await page.wait_for_timeout(500)
            except Exception:
                break

        try:
            content = await page.content()
            return content
        except Exception as e:
            print(f"    -> 获取内容错误: {e}")
            return ""
        finally:
            await browser.close()


def fetch_zhihu_user(user_id: str, name: str, db_path: Optional[str] = None) -> list:
    """抓取指定知乎用户的当天回答，返回新增条目列表"""
    ready, message = is_chromium_ready()
    if not ready:
        print(f"    -> {message}")
        return []

    url = f"https://www.zhihu.com/people/{user_id}"
    print(f"  抓取知乎用户: {name} ({url})")

    html = asyncio.run(_fetch_page_content(url))
    if not html:
        print("    -> 获取页面内容失败")
        return []

    today = date.today().isoformat()
    items = _extract_answer_items(html, today)
    print(f"    -> 当天({today})回答: {len(items)} 条")

    if db_path and items:
        init(db_path)
        sess = get_session()
        now = utcnow_naive()
        new_items = []

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
    for user in zhihu_users:
        user_id = user.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            continue
        name = user.get("name")
        if not isinstance(name, str) or not name:
            name = user_id
        entries = fetch_zhihu_user(user_id, name, db_path=db_path)
        all_entries.extend(entries)

    cache_file = os.path.join(os.path.dirname(__file__), "..", "output", "zhihu_cache.json")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"[知乎采集] 完成，共 {len(all_entries)} 条新条目")


if __name__ == "__main__":
    main()
