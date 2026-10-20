"""编排智能体提交、后台 Worker、授权事件回放和取消。"""

import asyncio
from collections.abc import AsyncIterator
from collections.abc import Callable
from typing import Any

from agent.errors import (
    AgentRunAlreadyEndedError,
    AgentRunAmbiguousError,
    AgentRunNotFoundError,
    ConversationAccessDeniedError,
    AgentEventStreamExpiredError,
)
from agent.persistence.interfaces import ConversationStore, RunStore
from agent.runner import AgentRunner
from agent.schemas.run import RunRecord, RunStatus
from agent.streaming.events import (
    AgentEvent,
    AgentEventType,
    is_run_terminal_event_type,
)
from agent.streaming.publisher import EventPublisher


class AgentApplicationService:
    """负责运行状态流转；HTTP 监听器只读取 Redis，不拥有生成任务。"""

    def __init__(
        self,
        runner: AgentRunner,
        publisher: EventPublisher,
        *,
        conversation_store: ConversationStore | None = None,
        run_store: RunStore | None = None,
        event_store: Any | None = None,
        task_queue: Any | None = None,
    ) -> None:
        """注入 Runner 和共享持久化/任务基础设施。"""
        self._runner = runner
        self._publisher = publisher
        self._conversation_store = conversation_store
        self._run_store = run_store
        self._event_store = event_store
        self._task_queue = task_queue

    async def chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        principal_id: str,
        attachment_ids: list[str] | None = None,
        graph_context: dict[str, Any] | None = None,
    ) -> list[AgentEvent]:
        """执行兼容的非流式对话并收集事件。"""
        events = self._runner.stream_chat(
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
            attachment_ids=attachment_ids,
            graph_context=graph_context,
        )
        return await self._publisher.publish_all(events)

    def stream_chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        principal_id: str,
        attachment_ids: list[str] | None = None,
        graph_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """保留旧式内联流接口，供既有离线调用及测试适配。"""
        events = self._runner.stream_chat(
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
            attachment_ids=attachment_ids,
            graph_context=graph_context,
        )
        return self._publisher.with_heartbeat(events)

    def submit_chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        principal_id: str,
        request_id: str,
        attachment_ids: list[str] | None = None,
        graph_context: dict[str, Any] | None = None,
        before_enqueue: Callable[[RunRecord], None] | None = None,
    ) -> tuple[RunRecord, AsyncIterator[AgentEvent]]:
        """准备运行、确保任务已派发，并返回共享事件流。

        Step 1: 由 Runner 校验会话/附件并按 request_id 复用运行。
        Step 2: 只将未启动的运行投递到独立 Worker 队列。
        Step 3: 当前请求作为 Redis Stream 读取器连接；断开不会触发 Runner 取消。
        """
        record = self._runner.prepare_chat(
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
            attachment_ids=attachment_ids,
            graph_context=graph_context,
            request_id=request_id,
        )
        if before_enqueue is not None:
            before_enqueue(record)
        if record.status == RunStatus.QUEUED:
            if self._task_queue is None:
                raise RuntimeError("智能体后台队列尚未组装")
            self._task_queue.enqueue(record.agent.value, record.run_id)
        return record, self.listen(
            conversation_id=record.conversation_id,
            principal_id=principal_id,
            run_id=record.run_id,
            after=None,
        )

    def submit_resume(
        self,
        *,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str,
        request_id: str,
        after: str | None,
    ) -> tuple[RunRecord, AsyncIterator[AgentEvent]]:
        """将追问恢复也作为后台任务执行，并从旧游标继续同一 run 流。"""
        record = self._runner.prepare_resume(
            conversation_id=conversation_id,
            run_id=run_id,
            answers=answers,
            principal_id=principal_id,
            request_id=request_id,
        )
        cursor = after
        if self._event_store is not None:
            latest_id = self._event_store.latest_id(conversation_id, run_id)
            # 恢复请求从既有 waiting 终止事件之后开始；幂等重试时 latest_id
            # 也可能已经包含本轮新事件，避免重放旧 question.required 并提前结束。
            cursor = latest_id
            try:
                self._event_store.validate_cursor(
                    conversation_id,
                    run_id,
                    after,
                    allow_missing_at_latest=True,
                )
            except AgentEventStreamExpiredError:
                # 答案已校验并持久化，旧事件可由会话历史恢复。
                pass
            self._event_store.validate_cursor(
                conversation_id,
                run_id,
                cursor,
                allow_missing_at_latest=True,
            )
        if record.status == RunStatus.QUEUED:
            if self._task_queue is None:
                raise RuntimeError("智能体后台队列尚未组装")
            self._task_queue.enqueue(record.agent.value, record.run_id)
        return record, self.listen(
            conversation_id=conversation_id,
            principal_id=principal_id,
            run_id=run_id,
            after=cursor,
            allow_missing_at_latest=True,
        )

    async def execute_worker(self, run_id: str) -> None:
        """在 Celery Worker 中执行 Runner，并先持久化每个事件再供客户端读取。"""
        if self._event_store is None:
            raise RuntimeError("智能体事件存储尚未组装")
        async for event in self._runner.execute_prepared(run_id):
            await asyncio.to_thread(self._event_store.append, event)

    def listen(
        self,
        *,
        conversation_id: str,
        principal_id: str,
        run_id: str | None,
        after: str | None,
        ensure_queued: bool = False,
        allow_missing_at_latest: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        """先做会话和运行授权，再返回可回放事件读取器。"""
        if self._conversation_store is None or self._run_store is None or self._event_store is None:
            raise RuntimeError("智能体会话监听服务尚未组装")
        # 授权顺序固定：任何 Redis Stream 查询之前先确认会话归属。
        conversation = self._conversation_store.get(conversation_id)
        if conversation is None or conversation.get("principal_id") != principal_id:
            raise ConversationAccessDeniedError()

        if run_id is None:
            active = [
                record for record in self._run_store.list_active(principal_id)
                if record.conversation_id == conversation_id
            ]
            if len(active) != 1:
                if len(active) > 1:
                    raise AgentRunAmbiguousError()
                raise AgentRunNotFoundError()
            record = active[0]
        else:
            record = self._run_store.get(run_id)
        if (
            record is None
            or record.conversation_id != conversation_id
            or record.principal_id != principal_id
            or record.agent != conversation.get("agent")
        ):
            raise AgentRunNotFoundError()

        if ensure_queued and record.status == RunStatus.QUEUED and self._task_queue is not None:
            # 刷新后访问仍处于 queued 的 run 时补投递；Worker claim 会合并重复投递。
            self._task_queue.enqueue(record.agent.value, record.run_id)

        latest_id = self._event_store.latest_id(conversation_id, record.run_id)
        terminal_status = record.status in {
            RunStatus.WAITING,
            RunStatus.COMPLETED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }
        if terminal_status and (
            (latest_id is None and after in {None, "0-0"})
            or (latest_id is not None and after is not None
                and _event_cursor(after) >= _event_cursor(latest_id))
        ):
            raise AgentRunAlreadyEndedError()
        if terminal_status and latest_id is None and after not in {None, "0-0"}:
            raise AgentEventStreamExpiredError()

        self._event_store.validate_cursor(
            conversation_id,
            record.run_id,
            after,
            allow_missing_at_latest=allow_missing_at_latest,
        )
        if terminal_status:
            last_event_type = self._event_store.last_event_type(
                conversation_id, record.run_id
            )
            if not (
                is_run_terminal_event_type(last_event_type)
                or last_event_type == AgentEventType.QUESTION_REQUIRED
            ):
                # Redis 事件写入失败时，Runner 仍可能已保存终态；避免连接空转，
                # 让客户端明确退回数据库历史消息。
                raise AgentRunAlreadyEndedError()

        return self._event_store.listen(
            conversation_id=conversation_id,
            run_id=record.run_id,
            after=after,
            terminal_status=record.status.value,
            allow_missing_at_latest=allow_missing_at_latest,
        )

    def active_runs(self, principal_id: str) -> list[dict[str, Any]]:
        """返回可信主体的后台活动会话及其最后事件游标。"""
        if self._run_store is None or self._event_store is None:
            raise RuntimeError("智能体活动会话服务尚未组装")
        records = self._run_store.list_active(principal_id)
        return [
            {
                "conversation_id": record.conversation_id,
                "run_id": record.run_id,
                "agent": record.agent.value,
                "status": record.status.value,
                "last_event_id": self._event_store.latest_id(
                    record.conversation_id, record.run_id
                ),
            }
            for record in records
        ]

    def run_status(
        self,
        *,
        conversation_id: str,
        principal_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """按会话归属读取运行状态；对越权和不存在统一返回安全错误。"""
        if self._conversation_store is None or self._run_store is None or self._event_store is None:
            raise RuntimeError("智能体运行状态服务尚未组装")
        conversation = self._conversation_store.get(conversation_id)
        if conversation is None or conversation.get("principal_id") != principal_id:
            raise ConversationAccessDeniedError()
        record = (
            self._run_store.get(run_id)
            if run_id is not None
            else self._run_store.get_latest_for_conversation(conversation_id, principal_id)
        )
        if (
            record is None
            or record.conversation_id != conversation_id
            or record.principal_id != principal_id
            or record.agent != conversation.get("agent")
        ):
            raise AgentRunNotFoundError()
        return {
            "conversation_id": record.conversation_id,
            "run_id": record.run_id,
            "status": record.status.value,
            "last_event_id": self._event_store.latest_id(conversation_id, record.run_id),
            "error": record.metadata.get("error_summary"),
        }

    def resume(
        self,
        *,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """兼容现有追问恢复入口，继续复用 Runner 校验和图 Checkpoint。"""
        events = self._runner.resume(
            conversation_id=conversation_id,
            run_id=run_id,
            answers=answers,
            principal_id=principal_id,
        )
        return self._publisher.with_heartbeat(events)

    def cancel(self, *, run_id: str, principal_id: str) -> None:
        """校验运行归属后向共享取消信号发出停止请求。"""
        self._runner.cancel(run_id=run_id, principal_id=principal_id)


class AgentSessionApplicationService:
    """跨智能体聚合会话监听、活动会话和运行状态查询。"""

    def __init__(
        self,
        *,
        conversation_store: ConversationStore,
        run_store: RunStore,
        event_store: Any,
        agent_services: dict[str, AgentApplicationService],
    ) -> None:
        """注入共享运行存储及按会话智能体类型建立的应用服务。"""
        self._conversation_store = conversation_store
        self._run_store = run_store
        self._event_store = event_store
        self._agent_services = agent_services

    def active_runs(self, principal_id: str) -> list[dict[str, Any]]:
        """返回用户全部 queued/running 会话，支持多会话并行执行。"""
        return [
            {
                "conversation_id": record.conversation_id,
                "run_id": record.run_id,
                "agent": record.agent.value,
                "status": record.status.value,
                "last_event_id": self._event_store.latest_id(
                    record.conversation_id, record.run_id
                ),
            }
            for record in self._run_store.list_active(principal_id)
        ]

    def listen(
        self,
        *,
        conversation_id: str,
        principal_id: str,
        run_id: str | None,
        after: str | None,
        allow_missing_at_latest: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        """先确认会话归属，再委托对应智能体的授权监听器。"""
        conversation = self._conversation_store.get(conversation_id)
        if conversation is None or conversation.get("principal_id") != principal_id:
            raise ConversationAccessDeniedError()
        agent = conversation.get("agent")
        service = self._agent_services.get(str(agent))
        if service is None:
            raise AgentRunNotFoundError()
        return service.listen(
            conversation_id=conversation_id,
            principal_id=principal_id,
            run_id=run_id,
            after=after,
            ensure_queued=True,
            allow_missing_at_latest=allow_missing_at_latest,
        )

    def status(
        self,
        *,
        conversation_id: str,
        principal_id: str,
        run_id: str | None,
    ) -> dict[str, Any]:
        """校验会话所有者后查询该智能体的单轮状态。"""
        conversation = self._conversation_store.get(conversation_id)
        if conversation is None or conversation.get("principal_id") != principal_id:
            raise ConversationAccessDeniedError()
        service = self._agent_services.get(str(conversation.get("agent")))
        if service is None:
            raise AgentRunNotFoundError()
        return service.run_status(
            conversation_id=conversation_id,
            principal_id=principal_id,
            run_id=run_id,
        )


def _event_cursor(event_id: str) -> tuple[int, int]:
    """将已校验的 Redis Stream ID 转为可比较游标。"""
    first, _, second = event_id.partition("-")
    return int(first), int(second or 0)
