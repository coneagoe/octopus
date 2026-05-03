#!/usr/bin/env python3
"""摘要生成器 - 读取各采集器的缓存，生成 Markdown 笔记"""

import os
import sys
import json
import argparse
import requests
import re
from datetime import datetime


def strip_html(text):
    """移除 HTML 标签和一些常见的残留噪音"""
    if not text:
        return ''
    # 先移除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 清理 &lt; &gt; 等 HTML 实体
    text = re.sub(r'&[a-z]+;', ' ', text)
    # 移除末尾的推广信息（如 #欢迎关注微信...）
    text = re.sub(r'#欢迎关注[^\n]*$', '', text)
    # 清理多余空白
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"


def load_cache(category):
    """加载缓存文件"""
    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', f'{category}_cache.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def generate_commentary(title, summary, source, api_key):
    """调用 MiniMax AI 生成一句话点评"""
    prompt = f"""你是一个精炼的投资分析师。读完文章后，先给出明确判断（利多/利空/中性），再用一段话说明理由，重点关注：
1. 这个消息对投资市场的影响
2. 是否有商业或投机机会（赛道/公司/时机）
3. 相关A股联想（如涉及，给出股票代码或名称）
4. 风险提示（如有）
格式：【利多/利空/中性】+ 理由，150字以内。

来源: {source}
标题: {title}
摘要: {summary[:300]}

直接输出，不要前缀。"""

    try:
        resp = requests.post(
            MINIMAX_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "MiniMax-Text-01",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.7
            },
            timeout=15
        )
        resp.raise_for_status()
        result = resp.json()
        commentary = result['choices'][0]['message']['content'].strip()
        return commentary
    except Exception as e:
        print(f"    [AI 失败] {e}")
        return "（AI 点评生成失败）"


def generate_markdown(date, entries_by_source, api_key):
    """生成 Markdown 文档"""

    md = f"""# 信息聚合日报 {date}

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""

    total = 0

    # RSS
    rss_entries = entries_by_source.get('rss', [])
    if rss_entries:
        md += "## RSS 订阅\n\n"
        for entry in rss_entries:
            total += 1
            commentary = generate_commentary(
                entry.get('title', ''),
                entry.get('summary', ''),
                entry.get('source', ''),
                api_key
            )
            md += f"""### [{entry['title']}]({entry['url']})

- 来源: {entry['source']}
- 摘要: {strip_html(entry.get('summary', ''))[:200]}
- 点评: {commentary}

"""
        md += "\n"

    # 网站
    web_entries = entries_by_source.get('web', [])
    if web_entries:
        md += "## 网站精选\n\n"
        for entry in web_entries:
            total += 1
            commentary = generate_commentary(
                entry.get('title', ''),
                entry.get('summary', ''),
                entry.get('source', ''),
                api_key
            )
            md += f"""### [{entry['title']}]({entry['url']})

- 来源: {entry['source']}
- 摘要: {strip_html(entry.get('summary', ''))[:200]}
- 点评: {commentary}

"""
        md += "\n"

    # 飞书
    feishu_entries = entries_by_source.get('feishu', [])
    if feishu_entries:
        md += "## 飞书群聊\n\n"
        for entry in feishu_entries:
            total += 1
            md += f"""### [{entry['title']}]({entry.get('url', '#')})

- 来源: {entry['source']}
- 摘要: {strip_html(entry.get('summary', ''))[:200]}
- 点评: （待实现）

"""
        md += "\n"

    # 邮件
    email_entries = entries_by_source.get('email', [])
    if email_entries:
        md += "## 邮件摘要\n\n"
        for entry in email_entries:
            total += 1
            md += f"""### {entry['title']}

- 发件人: {entry.get('sender', 'Unknown')}
- 摘要: {strip_html(entry.get('summary', ''))[:200]}
- 点评: （待实现）

"""
        md += "\n"

    # 空状态
    if total == 0:
        md += "_今日无新内容_\n\n"

    md += f"""---

*由 Octopus 信息聚合系统自动生成 · 共 {total} 条内容*

"""

    return md


def main():
    parser = argparse.ArgumentParser(description='生成每日摘要')
    parser.add_argument('--date', required=True, help='日期，格式 YYYY-MM-DD')
    parser.add_argument('--output', required=True, help='输出文件路径')
    args = parser.parse_args()

    api_key = os.environ.get('MINIMAX_API_KEY', '')
    if not api_key:
        print("[错误] MINIMAX_API_KEY 环境变量未设置")
        sys.exit(1)

    print(f"[摘要生成] 生成日期: {args.date}")

    rss_entries = load_cache('rss')
    web_entries = load_cache('web')
    feishu_entries = load_cache('feishu')
    email_entries = load_cache('email')

    print(f"  RSS: {len(rss_entries)} 条")
    print(f"  网站: {len(web_entries)} 条")
    print(f"  飞书: {len(feishu_entries)} 条")
    print(f"  邮件: {len(email_entries)} 条")

    entries_by_source = {
        'rss': rss_entries,
        'web': web_entries,
        'feishu': feishu_entries,
        'email': email_entries
    }

    md = generate_markdown(args.date, entries_by_source, api_key)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(md)

    print(f"  -> 已写入: {args.output}")


if __name__ == '__main__':
    main()