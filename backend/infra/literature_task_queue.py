
from infra.celery_app import celery_app


class CeleryLiteratureTaskQueue:
    """通过现有 Redis Broker 提交异步文献入库任务。"""

    def enqueue(self, document_id: str) -> None:
        """发送仅包含文献 ID 的任务消息，不向 Broker 传输文件正文。"""
        celery_app.send_task(
            "app.service.literature_tasks.process_literature_document",
            args=[document_id],
        )
