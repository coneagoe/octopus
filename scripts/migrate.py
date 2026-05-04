"""一次性迁移脚本 — 将现有 JSON cache 迁移到 SQLite"""

import json
import os

from scripts.db import init, get_session, Article, utcnow_naive

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')
CACHE_FILES = {
    'rss': 'rss_cache.json',
    'web': 'web_cache.json',
    'feishu': 'feishu_cache.json',
    'email': 'email_cache.json',
}


def load_cache_json(path: str) -> list:
    """加载 JSON cache 文件"""
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def migrate_entries(entries: list, db_path: str) -> int:
    """将条目列表迁移到 DB，返回新增条目数"""
    init(db_path)
    sess = get_session()
    count = 0
    now = utcnow_naive()
    for entry in entries:
        url = entry.get('url', '')
        if not url:
            continue
        existing = sess.get(Article, url)
        if existing:
            existing.last_seen = now
        else:
            article = Article(
                url=url,
                title=entry.get('title', ''),
                source=entry.get('source', ''),
                source_type=entry.get('source_type', 'rss'),
                published=entry.get('published', ''),
                summary=entry.get('summary', ''),
                first_fetched=now,
                last_seen=now,
            )
            sess.add(article)
            count += 1
    sess.commit()
    sess.close()
    return count


def migrate_from_output_dir(db_path: str) -> int:
    """迁移 output/ 下所有 JSON cache 到 DB，返回新增条目数"""
    total = 0
    for source_type, filename in CACHE_FILES.items():
        path = os.path.join(OUTPUT_DIR, filename)
        entries = load_cache_json(path)
        for entry in entries:
            entry['source_type'] = source_type
        count = migrate_entries(entries, db_path)
        print(f"  [{source_type}] 迁移 {count} 条新条目（{len(entries)} 总条目）")
        total += count
    return total


def main():
    db_path = os.path.join(OUTPUT_DIR, 'octopus.db')
    print(f"[迁移] JSON cache → SQLite: {db_path}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    count = migrate_from_output_dir(db_path)
    print(f"[迁移] 完成，共 {count} 条新文章")


if __name__ == '__main__':
    main()
