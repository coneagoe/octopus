#!/usr/bin/env python3
"""RSS 采集器 — 带去重功能"""

import json
import os
from datetime import datetime

import feedparser

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_rss(url, name, db_path=None):
    """抓取单个 RSS 源，返回新增条目列表（已去重）"""
    print(f"  抓取: {name} ({url})")
    try:
        feed = feedparser.parse(url)
        new_entries = []

        for entry in feed.entries[:10]:  # 最新10条
            entry_url = entry.get('link', '')
            if not entry_url:
                continue

            # 如果提供了 db_path，进行去重检查
            if db_path:
                from scripts.db import init, get_session, Article, utcnow_naive
                init(db_path)
                sess = get_session()
                existing = sess.get(Article, entry_url)
                if existing:
                    # 已存在：更新 last_seen 但不返回
                    existing.last_seen = utcnow_naive()
                    sess.commit()
                    sess.close()
                    continue
                # 不存在：插入新记录
                now = utcnow_naive()
                article = Article(
                    url=entry_url,
                    title=entry.get('title', ''),
                    source=name,
                    source_type='rss',
                    published=entry.get('published', ''),
                    summary=entry.get('summary', '')[:500],
                    first_fetched=now,
                    last_seen=now,
                )
                sess.add(article)
                sess.commit()
                sess.close()
            else:
                # 无 db_path 时走旧逻辑（兼容旧调用）
                pass

            new_entries.append({
                'source': name,
                'source_type': 'rss',
                'title': entry.get('title', ''),
                'url': entry_url,
                'published': entry.get('published', ''),
                'summary': entry.get('summary', '')[:500],
            })

        print(f"    -> 获取 {len(new_entries)} 条新条目")
        return new_entries
    except Exception as e:
        print(f"    -> 错误: {e}")
        return []


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