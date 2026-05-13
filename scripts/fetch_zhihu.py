#!/usr/bin/env python3
"""知乎用户回答抓取器 — Playwright 渲染"""

import asyncio
import json
import os
import re
from datetime import date
from typing import Optional, Tuple, TypedDict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scripts.db import Article, get_session, init, utcnow_naive
from scripts.playwright_setup import is_chromium_ready
from scripts.url_normalize import make_entry_hash, normalize_url

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


class FetchZhihuError(RuntimeError):
    """知乎抓取失败。"""


class ZhihuPageContent(TypedDict):
    status_code: Optional[int]
    final_url: str
    html: str


def _build_cookie_expired_error(detail: str) -> str:
    return f"知乎 cookie 已过期或失效，{detail}；请重新导入 ZHIHU_COOKIES"


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


def _parse_cookie_header(header: str) -> list:
    """把 'name1=val1; name2=val2' 格式的 cookie 请求头解析为 Playwright cookie 列表"""
    import time
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


def _sync_storage_state_from_env(storage_state_path: str) -> bool:
    """
    若环境变量 ZHIHU_COOKIES 已设置，则将其解析并写入 storage state 文件。
    返回 True 表示写入成功，False 表示环境变量未设置。
    """
    cookie_header = os.environ.get("ZHIHU_COOKIES", "").strip()
    if not cookie_header:
        return False
    cookies = _parse_cookie_header(cookie_header)
    if not cookies:
        return False
    state = {"cookies": cookies, "origins": []}
    os.makedirs(os.path.dirname(storage_state_path), exist_ok=True)
    with open(storage_state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return True


async def _login_and_save_state(username: str, password: str, storage_state_path: str) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        try:
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
            await page.goto("https://www.zhihu.com/signin", timeout=30000)
            await page.get_by_text("密码登录").click()
            await page.locator("input[name='username']").fill(username)
            await page.locator("input[type='password']").fill(password)
            await page.get_by_role("button", name="登录", exact=True).click()
            try:
                await page.wait_for_url(
                    lambda url: not any(
                        t in url for t in ("/signin", "/captcha", "/account/unhuman")
                    ),
                    timeout=15000,
                )
            except Exception:
                pass  # 超时或验证码，下面再判断 URL

            if any(token in page.url for token in ("/signin", "/captcha", "/account/unhuman")):
                raise FetchZhihuError("知乎登录未完成，可能需要人工处理验证")

            os.makedirs(os.path.dirname(storage_state_path), exist_ok=True)
            await context.storage_state(path=storage_state_path)
        finally:
            await browser.close()


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

    if any(
        token in normalized_url
        for token in ("/signin", "/login", "/captcha", "/account/unhuman")
    ):
        return True

    auth_markers = (
        "请先登录",
        "请登录后",
        "登录后继续",
        "登录后可见",
        "密码登录",
        "扫码登录",
        "安全验证",
        "请完成验证",
        "验证码",
        "人机验证",
        "访问受限",
    )
    content_markers = (
        "list-item",
        "profile-main",
        "answeritem-time",
        "answeritem-summary",
        "/question/",
    )
    return any(marker in page_text for marker in auth_markers) and not any(
        marker in page_text for marker in content_markers
    )


def _coerce_page_content(page_result, fallback_url: str) -> ZhihuPageContent:
    if isinstance(page_result, dict):
        html = page_result.get("html", "")
        final_url = page_result.get("final_url") or fallback_url
        status_code = page_result.get("status_code")
        if not isinstance(html, str):
            html = ""
        if not isinstance(final_url, str):
            final_url = fallback_url
        if not isinstance(status_code, (int, type(None))):
            status_code = None
        return {
            "status_code": status_code,
            "final_url": final_url,
            "html": html,
        }

    if isinstance(page_result, str):
        return {
            "status_code": None,
            "final_url": fallback_url,
            "html": page_result,
        }

    raise FetchZhihuError("获取页面内容失败")


def _is_invalid_storage_state_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "storage state" not in message:
        return False
    return any(
        token in message
        for token in ("error reading", "invalid", "malformed", "json", "unexpected token")
    )


async def _fetch_page_content(url: str, storage_state_path: Optional[str] = None) -> ZhihuPageContent:
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
        has_saved_storage_state = bool(storage_state_path and os.path.exists(storage_state_path))
        if has_saved_storage_state:
            context_kwargs["storage_state"] = storage_state_path
        try:
            try:
                context = await browser.new_context(**context_kwargs)
            except Exception as exc:
                if not has_saved_storage_state or not _is_invalid_storage_state_error(exc):
                    raise
                print("  -> 检测到损坏的知乎登录态缓存，改用未登录会话重试")
                try:
                    if storage_state_path is not None:
                        os.remove(storage_state_path)
                except OSError:
                    pass
                context_kwargs.pop("storage_state", None)
                context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            async def _abort(route):
                await route.abort()

            await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,webp}", _abort)
            await page.route("**/analytics/**", _abort)
            response = await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(5000)
            for offset in (0, 500, 1000):
                try:
                    await page.evaluate(f"window.scrollTo(0, {offset})")
                    await page.wait_for_timeout(300)
                except Exception:
                    break
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

    storage_state_path = _get_storage_state_path()
    _sync_storage_state_from_env(storage_state_path)
    page_result = asyncio.run(_fetch_page_content(url, storage_state_path=storage_state_path))
    page_content = _coerce_page_content(page_result, url)
    html = page_content["html"]

    if _page_requires_login(page_content["status_code"], page_content["final_url"], html):
        username, password = _load_zhihu_credentials()
        try:
            asyncio.run(_login_and_save_state(username, password, storage_state_path))
        except FetchZhihuError as exc:
            raise FetchZhihuError(
                _build_cookie_expired_error("且自动登录未完成，可能需要人工处理验证")
            ) from exc
        page_result = asyncio.run(_fetch_page_content(url, storage_state_path=storage_state_path))
        page_content = _coerce_page_content(page_result, url)
        html = page_content["html"]
        if _page_requires_login(page_content["status_code"], page_content["final_url"], html):
            raise FetchZhihuError(_build_cookie_expired_error("自动登录后仍无法访问用户主页"))

    if not isinstance(html, str) or not html:
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
    had_success = False
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
        had_success = True
        all_entries.extend(entries)

    cache_file = os.path.join(os.path.dirname(__file__), "..", "output", "zhihu_cache.json")
    if had_success:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(all_entries, f, ensure_ascii=False, indent=2)
    else:
        print("  -> 本轮知乎抓取全部失败，保留旧缓存")

    print(f"[知乎采集] 完成，共 {len(all_entries)} 条新条目")
    if had_failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
