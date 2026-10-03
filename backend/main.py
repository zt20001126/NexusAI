"""Uvicorn 默认入口：`uvicorn main:app --reload`。"""

from app.main import app

__all__ = ["app"]

