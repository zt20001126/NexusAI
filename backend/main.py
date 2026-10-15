"""Uvicorn 默认入口：`uvicorn main:app --reload`。"""

from bootstrap.application import app

__all__ = ["app"]

