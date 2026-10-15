"""将图片参数追问保存为统一结果状态并转为公共问题协议。"""

from langchain_core.tools import tool

from agent.persistence.interfaces import TaskResultStore
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from agent.schemas.tool_result import ToolResult
from agents.image_agent.constants import IMAGE_AGENT_ID, IMAGE_RESULT_TYPE
from agents.image_agent.schemas import ImageQuestionToolInput


def create_ask_image_parameters_tool(task_result_store: TaskResultStore):
    """创建捕获共享结果仓储的图片参数追问工具。"""

    @tool("ask_image_parameters", args_schema=ImageQuestionToolInput)
    def ask_image_parameters(
        questions: list[dict[str, object]],
        task_result_id: str,
        principal_id: str,
        conversation_id: str,
        run_id: str,
        prompt: str,
        attachment_ids: list[str],
        options: dict[str, object],
    ) -> str:
        """等待用户补充 TokenHub 文档中尚缺少的图片参数。"""
        task_result_store.save(
            TaskResultRecord(
                task_result_id=task_result_id,
                agent_id=IMAGE_AGENT_ID,
                user_id=principal_id,
                conversation_id=conversation_id,
                run_id=run_id,
                message_id=None,
                result_type=IMAGE_RESULT_TYPE,
                generation_status=TaskResultStatus.AWAITING_INPUT,
                input_data={
                    "prompt": prompt,
                    "parameters": options,
                    "reference_attachment_ids": attachment_ids,
                },
            )
        )
        return ToolResult(
            success=True,
            data={
                "questions": questions,
                "task_result": {
                    "task_result_id": task_result_id,
                    "agent_id": IMAGE_AGENT_ID,
                    "generation_status": TaskResultStatus.AWAITING_INPUT.value,
                },
            },
            code="QUESTION_REQUIRED",
            message="等待用户选择图片参数",
        ).model_dump_json()

    return ask_image_parameters
