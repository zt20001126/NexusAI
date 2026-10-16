"""Celery 应用配置，文献任务通过 Redis Broker 分发且不保存结果后端。"""

from celery import Celery

from infra.settings import AppSettings


_settings = AppSettings()
celery_app = Celery(
    "nexusai",
    broker=_settings.celery_broker_url,
    include=["app.service.literature_tasks"],
)
celery_app.conf.update(
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
)

