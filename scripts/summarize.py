#!/usr/bin/env python3
"""摘要生成器 - 读取各采集器的缓存，生成 Markdown 笔记"""

import os
import sys
import json
import argparse
from datetime import datetime


def load_cache(category):
    """加载缓存文件"""
    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', f'{category}_cache.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def generate_markdown(date, rss_entries, web_entries, feishu_entries, email_entries):
    """生成 Markdown 文档"""

    md = f"""# 信息聚合日报 {date}

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""

    # RSS
    if rss_entries:
        md += "## RSS 订阅\n\n"
        for entry in rss_entries:
            md += f"""### [{entry['title']}]({entry['url']})

- 来源: {entry['source']}
- 摘要: {entry.get('summary', '')[:200]}...

"""
        md += "\n"

    # 网站
    if web_entries:
        md += "## 网站精选\n\n"
        for entry in web_entries:
            md += f"""### [{entry['title']}]({entry['url']})

- 来源: {entry['source']}
- 摘要: {entry.get('summary', '')[:200]}...

"""
        md += "\n"

    # 飞书
    if feishu_entries:
        md += "## 飞书群聊\n\n"
        for entry in feishu_entries:
            md += f"""### [{entry['title']}]({entry.get('url', '#')})

- 来源: {entry['source']}
- 摘要: {entry.get('summary', '')[:200]}...

"""
        md += "\n"

    # 邮件
    if email_entries:
        md += "## 邮件摘要\n\n"
        for entry in email_entries:
            md += f"""### {entry['title']}

- 发件人: {entry.get('sender', 'Unknown')}
- 摘要: {entry.get('summary', '')[:200]}...

"""
        md += "\n"

    # 空状态
    if not any([rss_entries, web_entries, feishu_entries, email_entries]):
        md += "_今日无新内容_\n\n"

    md += """---

*由 Octopus 信息聚合系统自动生成*
"""

    return md


def main():
    parser = argparse.ArgumentParser(description='生成每日摘要')
    parser.add_argument('--date', required=True, help='日期，格式 YYYY-MM-DD')
    parser.add_argument('--output', required=True, help='输出文件路径')
    args = parser.parse_args()

    print(f"[摘要生成] 生成日期: {args.date}")

    rss_entries = load_cache('rss')
    web_entries = load_cache('web')
    feishu_entries = load_cache('feishu')
    email_entries = load_cache('email')

    print(f"  RSS: {len(rss_entries)} 条")
    print(f"  网站: {len(web_entries)} 条")
    print(f"  飞书: {len(feishu_entries)} 条")
    print(f"  邮件: {len(email_entries)} 条")

    md = generate_markdown(args.date, rss_entries, web_entries, feishu_entries, email_entries)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(md)

    print(f"  -> 已写入: {args.output}")


if __name__ == '__main__':
    main()