"""数据库管理 — SQLite + SQLAlchemy ORM"""

import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Article(Base):
    """文章记录表 — URL 唯一，用于去重"""
    __tablename__ = 'articles'

    url = Column(String(2048), primary_key=True)
    title = Column(String(1024), nullable=False)
    source = Column(String(256), nullable=False)
    source_type = Column(String(32))  # 'rss' / 'web' / 'feishu' / 'email'
    published = Column(String(256), default='')
    summary = Column(Text, default='')
    first_fetched = Column(DateTime, default=utcnow_naive)
    last_seen = Column(DateTime, default=utcnow_naive)


class DailyEntry(Base):
    """日报条目表 — 记录每天写了哪些文章"""
    __tablename__ = 'daily_entries'

    date = Column(String(10), primary_key=True)  # YYYY-MM-DD
    url = Column(String(2048), primary_key=True)
    commentary = Column(Text, default='')


_engine = None
_Session = None


def init(db_path: str):
    """初始化数据库（创建 engine + 建表）"""
    global _engine, _Session
    _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    _Session = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)


def get_session():
    """获取数据库会话（延迟初始化）"""
    global _Session
    if _Session is None:
        db_path = os.path.join(os.path.dirname(__file__), '..', 'output', 'octopus.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        init(db_path)
    return _Session()
