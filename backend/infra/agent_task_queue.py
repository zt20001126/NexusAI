"""将智能体运行记录派发到独立 Celery 队列。"""

from agent.errors import AgentTaskQueueUnavailableError
from infra.celery_app import celery_app


class CeleryAgentTaskQueue:
    """仅向 Worker 发送稳定标识，不在 Broker 中复制用户消息正文。"""

    def enqueue(self, agent: str, run_id: str) -> str:
        """提交指定运行；Worker 从 PostgreSQL 读取输入和恢复元数据。"""
        try:
            result = celery_app.send_task(
                "app.service.agent_tasks.execute_agent_run",
                args=[agent, run_id],
                queue="agents",
            )
            return str(result.id)
        except Exception as error:
            raise AgentTaskQueueUnavailableError() from error


class AgentTaskQueue:
    """Agent 任务提交协议，便于将队列适配器注入应用服务。"""

    def enqueue(self, agent: str, run_id: str) -> str: ...
