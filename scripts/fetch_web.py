#!/usr/bin/env python3
"""网站抓取器 — 带去重功能"""

import json
import os
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_web(url, name, selector='article', db_path=None):
    """抓取单个网页，返回新增条目列表（已去重）"""
    print(f"  抓取: {name} ({url})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Octopus/1.0; +https://github.com/coneagoe/octopus)'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        articles = []
        now = datetime.now(timezone.utc)

        # 尝试提取文章列表
        for item in soup.select(selector)[:10]:
            title_elem = item.find(['h1', 'h2', 'h3'])
            link_elem = item.find('a', href=True)
            summary_elem = item.find('p')

            if not title_elem:
                continue

            article_url = urljoin(url, link_elem['href']) if link_elem else url

            # 去重检查
            if db_path:
                from scripts.db import init, get_session, Article
                init(db_path)
                sess = get_session()
                existing = sess.get(Article, article_url)
                if existing:
                    existing.last_seen = now
                    sess.commit()
                    sess.close()
                    continue

                article = Article(
                    url=article_url,
                    title=title_elem.get_text(strip=True),
                    source=name,
                    source_type='web',
                    published='',
                    summary=summary_elem.get_text(strip=True)[:500] if summary_elem else '',
                    first_fetched=now,
                    last_seen=now,
                )
                sess.add(article)
                sess.commit()
                sess.close()
            else:
                # 无 db_path 时走旧逻辑
                pass

            articles.append({
                'source': name,
                'source_type': 'web',
                'title': title_elem.get_text(strip=True),
                'url': article_url,
                'summary': summary_elem.get_text(strip=True)[:500] if summary_elem else '',
            })

        # 如果 selector 没找到，回退到整页提取
        if not articles:
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else name
            article_url = url

            if db_path:
                from scripts.db import init, get_session, Article
                init(db_path)
                sess = get_session()
                existing = sess.get(Article, article_url)
                if not existing:
                    article = Article(
                        url=article_url,
                        title=title_text,
                        source=name,
                        source_type='web',
                        published='',
                        summary='',
                        first_fetched=now,
                        last_seen=now,
                    )
                    sess.add(article)
                    sess.commit()
                    sess.close()
                else:
                    existing.last_seen = now
                    sess.commit()
                    sess.close()
            else:
                pass

            articles.append({
                'source': name,
                'source_type': 'web',
                'title': title_text,
                'url': article_url,
                'summary': '',
            })

        print(f"    -> 获取 {len(articles)} 条新条目")
        return articles
    except Exception as e:
        print(f"    -> 错误: {e}")
        return []


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
            db_path=db_path
        )
        all_entries.extend(entries)

    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'web_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"[网站抓取] 完成，共 {len(all_entries)} 条新条目")


if __name__ == '__main__':
    main()
