#!/usr/bin/env python3
"""RSS 采集器"""

import json
import os

import feedparser

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_rss(url, name):
    """抓取单个 RSS 源"""
    print(f"  抓取: {name} ({url})")
    try:
        feed = feedparser.parse(url)
        entries = []
        for entry in feed.entries[:10]:  # 最新10条
            entries.append({
                'source': name,
                'source_type': 'rss',
                'title': entry.get('title', ''),
                'url': entry.get('link', ''),
                'published': entry.get('published', ''),
                'summary': entry.get('summary', '')[:500],
            })
        print(f"    -> 获取 {len(entries)} 条")
        return entries
    except Exception as e:
        print(f"    -> 错误: {e}")
        return []


def main():
    config = load_config()
    all_entries = []

    rss_sources = config.get('sources', {}).get('rss', [])
    print(f"[RSS 采集] 共 {len(rss_sources)} 个源")

    for source in rss_sources:
        entries = fetch_rss(source['url'], source.get('name', source['url']))
        all_entries.extend(entries)

    # 保存到临时文件，供 summarize.py 读取
    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'rss_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"[RSS 采集] 完成，共 {len(all_entries)} 条")


if __name__ == '__main__':
    main()
