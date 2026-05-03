#!/usr/bin/env python3
"""网站抓取器"""

import requests
from bs4 import BeautifulSoup
import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def fetch_web(url, name, selector='article'):
    """抓取单个网页"""
    print(f"  抓取: {name} ({url})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Octopus/1.0; +https://github.com/coneagoe/octopus)'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        articles = []

        # 尝试提取文章列表
        for item in soup.select(selector)[:10]:
            title_elem = item.find(['h1', 'h2', 'h3'])
            link_elem = item.find('a', href=True)
            summary_elem = item.find('p')

            if title_elem:
                articles.append({
                    'source': name,
                    'source_type': 'web',
                    'title': title_elem.get_text(strip=True),
                    'url': link_elem['href'] if link_elem else url,
                    'summary': summary_elem.get_text(strip=True)[:500] if summary_elem else '',
                })

        # 如果 selector 没找到，回退到整页提取
        if not articles:
            title = soup.find('title')
            articles.append({
                'source': name,
                'source_type': 'web',
                'title': title.get_text(strip=True) if title else name,
                'url': url,
                'summary': '',
            })

        print(f"    -> 获取 {len(articles)} 条")
        return articles
    except Exception as e:
        print(f"    -> 错误: {e}")
        return []


def main():
    config = load_config()
    all_entries = []

    web_sources = config.get('sources', {}).get('websites', [])
    print(f"[网站抓取] 共 {len(web_sources)} 个源")

    for source in web_sources:
        entries = fetch_web(
            source['url'],
            source.get('name', source['url']),
            source.get('selector', 'article')
        )
        all_entries.extend(entries)

    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'web_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"[网站抓取] 完成，共 {len(all_entries)} 条")


if __name__ == '__main__':
    main()