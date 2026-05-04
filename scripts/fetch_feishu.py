#!/usr/bin/env python3
"""飞书消息采集器"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_feishu():
    """采集飞书群消息"""
    config = load_config()
    feishu_config = config.get('sources', {}).get('feishu', {})

    chat_ids = feishu_config.get('chat_ids', [])
    print(f"[飞书采集] 共 {len(chat_ids)} 个群")

    if not chat_ids:
        print("  -> 未配置飞书群，跳过")
        return []

    # TODO: 实现飞书 API 调用
    # 需要：FEISHU_APP_ID, FEISHU_APP_SECRET
    print("  -> 飞书采集待实现，需要配置飞书应用凭证")
    return []


def main():
    entries = fetch_feishu()

    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'feishu_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"[飞书采集] 完成，共 {len(entries)} 条")


if __name__ == '__main__':
    main()
