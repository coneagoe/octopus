#!/usr/bin/env python3
"""网站抓取器 — 带去重功能"""

import json
import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scripts.db import Article, get_session, init, utcnow_naive
from scripts.url_normalize import make_entry_hash, normalize_url

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml

    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_web(url, name, selector='article', db_path=None):
    """抓取单个网页，返回新增条目列表（已去重）"""
    print(f"  抓取: {name} ({url})")
    sess = None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Octopus/1.0; +https://github.com/coneagoe/octopus)'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        articles = []

        if db_path:
            init(db_path)
            sess = get_session()

        def build_article_payload(raw_url, title, summary):
            try:
                normalized_url = normalize_url(raw_url)
            except ValueError:
                print(f"    -> 跳过非法 URL: {raw_url}")
                return None

            entry_hash = make_entry_hash(normalized_url)
            now = utcnow_naive()

            if sess is not None:
                existing = sess.get(Article, entry_hash)
                if existing:
                    existing.last_seen = now
                    return None

                sess.add(Article(
                    entry_hash=entry_hash,
                    normalized_url=normalized_url,
                    url=raw_url,
                    author='',
                    title=title,
                    source=name,
                    source_type='web',
                    published='',
                    summary=summary,
                    first_fetched=now,
                    last_seen=now,
                ))

            return {
                'source': name,
                'source_type': 'web',
                'title': title,
                'url': raw_url,
                'normalized_url': normalized_url,
                'entry_hash': entry_hash,
                'summary': summary,
            }

        # 尝试提取文章列表
        for item in soup.select(selector)[:10]:
            title_elem = item.find(['h1', 'h2', 'h3'])
            link_elem = item.find('a', href=True)
            summary_elem = item.find('p')

            if not title_elem:
                continue

            href = link_elem.get('href') if link_elem else None
            raw_url = urljoin(url, href) if isinstance(href, str) else url
            article = build_article_payload(
                raw_url,
                title_elem.get_text(strip=True),
                summary_elem.get_text(strip=True)[:500] if summary_elem else '',
            )
            if article is not None:
                articles.append(article)

        # 如果 selector 没找到，回退到整页提取
        if not articles:
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else name
            article = build_article_payload(url, title_text, '')
            if article is not None:
                articles.append(article)

        if sess is not None:
            sess.commit()

        print(f"    -> 获取 {len(articles)} 条新条目")
        return articles
    except Exception as e:
        print(f"    -> 错误: {e}")
        return []
    finally:
        if sess is not None:
            sess.close()


def main():
    config = load_config()
    all_entries = []

    web_sources = config.get('sources', {}).get('websites', [])
    print(f"[网站抓取] 共 {len(web_sources)} 个源")

    # 获取 DB 路径（用于去重）
    db_path = os.environ.get('OCTOPUS_DB', None)
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), '..', 'output', 'octopus.db')

    for source in web_sources:
        entries = fetch_web(
            source['url'],
            source.get('name', source['url']),
            source.get('selector', 'article'),
            db_path=db_path,
        )
        all_entries.extend(entries)

    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'web_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"[网站抓取] 完成，共 {len(all_entries)} 条新条目")


if __name__ == '__main__':
    main()
