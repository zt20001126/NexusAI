"""声明应用数据库 ORM 模型共享的 SQLAlchemy 元数据基类。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """应用持久化模型的声明式基类，供建表和迁移工具读取元数据。"""
