#!/usr/bin/env python3
"""RSS 采集器 — 带去重功能"""

import json
import os

import feedparser

from scripts.db import Article, get_session, init, utcnow_naive
from scripts.url_normalize import make_entry_hash, normalize_url

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_rss(url, name, db_path=None):
    """抓取单个 RSS 源，返回新增条目列表（已去重）"""
    print(f"  抓取: {name} ({url})")
    sess = None
    try:
        feed = feedparser.parse(url)
        new_entries = []

        if db_path:
            init(db_path)
            sess = get_session()

        for entry in feed.entries[:10]:  # 最新10条
            raw_url = str(entry.get('link') or '')
            if not raw_url:
                continue

            try:
                normalized_url = normalize_url(raw_url)
            except ValueError:
                print(f"    -> 跳过非法 URL: {raw_url}")
                continue

            entry_hash = make_entry_hash(normalized_url)

            if sess is not None:
                existing = sess.get(Article, entry_hash)
                if existing:
                    existing.last_seen = utcnow_naive()
                    continue

                now = utcnow_naive()
                title = str(entry.get('title') or '')
                published = str(entry.get('published') or '')
                summary = str(entry.get('summary') or '')[:500]
                article = Article(
                    entry_hash=entry_hash,
                    normalized_url=normalized_url,
                    url=raw_url,
                    author='',
                    title=title,
                    source=name,
                    source_type='rss',
                    published=published,
                    summary=summary,
                    first_fetched=now,
                    last_seen=now,
                )
                sess.add(article)

            new_entries.append({
                'source': name,
                'source_type': 'rss',
                'title': str(entry.get('title') or ''),
                'url': raw_url,
                'normalized_url': normalized_url,
                'entry_hash': entry_hash,
                'published': str(entry.get('published') or ''),
                'summary': str(entry.get('summary') or '')[:500],
            })

        if sess is not None:
            sess.commit()

        print(f"    -> 获取 {len(new_entries)} 条新条目")
        return new_entries
    except Exception as e:
        print(f"    -> 错误: {e}")
        return []
    finally:
        if sess is not None:
            sess.close()


def main():
    config = load_config()
    all_entries = []

    rss_sources = config.get('sources', {}).get('rss', [])
    print(f"[RSS 采集] 共 {len(rss_sources)} 个源")

    # 获取 DB 路径（用于去重）
    db_path = os.environ.get('OCTOPUS_DB', None)
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), '..', 'output', 'octopus.db')

    for source in rss_sources:
        entries = fetch_rss(source['url'], source.get('name', source['url']), db_path=db_path)
        all_entries.extend(entries)

    # 保存到临时文件，供 summarize.py 读取
    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'rss_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"[RSS 采集] 完成，共 {len(all_entries)} 条新条目")


if __name__ == '__main__':
    main()
