#!/usr/bin/env python3
"""邮件采集器"""

import email
import imaplib
import json
import os
from email.header import decode_header

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')


def load_config():
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def decode_str(s):
    """解码 email 头"""
    if not s:
        return ''
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)


def fetch_email():
    """采集邮件"""
    config = load_config()
    email_config = config.get('sources', {}).get('email', {})

    if not email_config:
        print("[邮件采集] 未配置，跳过")
        return []

    imap_host = email_config.get('imap')
    folder = email_config.get('folder', 'INBOX')
    keywords = email_config.get('keywords', [])

    print(f"[邮件采集] 连接 {imap_host}")

    try:
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(email_config.get('username'), email_config.get('password'))
        mail.select(folder)

        # 搜索最新邮件
        status, messages = mail.search(None, 'ALL')
        if status != 'OK' or not messages:
            return []
        mail_ids = messages[0].split()[-20:]  # 最新20封

        entries = []
        for mail_id in mail_ids:
            status, msg_data = mail.fetch(mail_id, '(RFC822)')
            if status != 'OK' or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            raw_msg = msg_data[0][1]
            if not isinstance(raw_msg, bytes):
                continue
            msg = email.message_from_bytes(raw_msg)

            subject = decode_str(msg['Subject'])
            sender = decode_str(msg.get('From', ''))
            date = msg.get('Date', '')

            # 简单关键词过滤
            if keywords and not any(k.lower() in subject.lower() for k in keywords):
                continue

            # 提取正文
            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == 'text/plain':
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body = payload.decode('utf-8', errors='replace')
                            break
            else:
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body = payload.decode('utf-8', errors='replace')

            entries.append({
                'source': 'email',
                'source_type': 'email',
                'title': subject,
                'url': '',
                'summary': body[:500],
                'sender': sender,
                'date': date,
            })

        mail.logout()
        print(f"  -> 获取 {len(entries)} 封邮件")
        return entries

    except Exception as e:
        print(f"  -> 错误: {e}")
        return []


def main():
    entries = fetch_email()

    cache_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'email_cache.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"[邮件采集] 完成，共 {len(entries)} 条")


if __name__ == '__main__':
    main()
