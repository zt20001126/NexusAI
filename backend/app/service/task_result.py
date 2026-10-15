"""按可信主体读取需要完整 JSON 内容的任务结果。"""

from agent.persistence.interfaces import TaskResultStore
from agents.listing_agent.constants import LISTING_AGENT_ID, LISTING_RESULT_TYPE
from agents.research_agent.constants import RESEARCH_AGENT_ID, RESEARCH_RESULT_TYPE
from app.schemas.task_result import TaskResultDetail


class TaskResultApplicationService:
    """隔离 Router 与任务结果持久化记录，并限制对外读取类型。"""

    def __init__(self, task_result_store: TaskResultStore) -> None:
        """注入统一任务结果存储协议。"""
        self._task_result_store = task_result_store

    def get_listing_result(
        self,
        *,
        task_result_id: str,
        principal_id: str,
    ) -> TaskResultDetail | None:
        """只向所有者返回 Listing 类型任务的 JSON 结果。"""
        record = self._task_result_store.get_owned(task_result_id, principal_id)
        if record is None or record.result_type != LISTING_RESULT_TYPE:
            return None
        return TaskResultDetail(
            task_result_id=record.task_result_id,
            agent_id=record.agent_id,
            result_type=record.result_type,
            generation_status=record.generation_status.value,
            result_data=record.result_data,
        )

    def get_research_result(
        self,
        *,
        task_result_id: str,
        principal_id: str,
    ) -> TaskResultDetail | None:
        """只向所有者返回 Research Agent 的标准化论文结果。"""
        record = self._task_result_store.get_owned(task_result_id, principal_id)
        if (
            record is None
            or record.agent_id != RESEARCH_AGENT_ID
            or record.result_type != RESEARCH_RESULT_TYPE
        ):
            return None
        return TaskResultDetail(
            task_result_id=record.task_result_id,
            agent_id=record.agent_id,
            result_type=record.result_type,
            generation_status=record.generation_status.value,
            result_data=record.result_data,
        )

    def get_task_result(
        self,
        *,
        task_result_id: str,
        principal_id: str,
    ) -> TaskResultDetail | None:
        """返回当前允许公开的业务任务结果类型。"""
        record = self._task_result_store.get_owned(task_result_id, principal_id)
        if record is None:
            return None
        is_listing = (
            record.agent_id == LISTING_AGENT_ID
            and record.result_type == LISTING_RESULT_TYPE
        )
        is_research = (
            record.agent_id == RESEARCH_AGENT_ID
            and record.result_type == RESEARCH_RESULT_TYPE
        )
        if not is_listing and not is_research:
            return None
        return TaskResultDetail(
            task_result_id=record.task_result_id,
            agent_id=record.agent_id,
            result_type=record.result_type,
            generation_status=record.generation_status.value,
            result_data=record.result_data,
        )
