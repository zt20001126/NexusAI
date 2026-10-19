"""将 Listing 追问和成功内容保存到共享任务结果表。"""

from langchain_core.tools import tool

from agent.persistence.interfaces import TaskResultStore
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from agent.schemas.tool_result import ToolResult
from agents.listing_agent.constants import (
    LISTING_AGENT,
    LISTING_RESULT_TYPE,
    LISTING_SAVE_TOOL_NAME,
    LISTING_VERSION_COUNT,
)
from agents.listing_agent.schemas import (
    AskListingQuestionsInput,
    ListingImageAnalysis,
    SaveListingResultInput,
)


def create_listing_task_result_tools(task_result_store: TaskResultStore):
    """使用注入的共享任务结果仓储创建 Listing 工具。"""

    @tool("ask_listing_questions", args_schema=AskListingQuestionsInput)
    def ask_listing_questions(
        questions: list[dict[str, object]],
        task_result_id: str,
        principal_id: str,
        conversation_id: str,
        run_id: str,
        original_request: str,
        attachment_ids: list[str],
        image_analysis: ListingImageAnalysis,
        product_facts: dict[str, object],
        confirmed_answers: dict[str, object],
    ) -> str:
        """保存等待商家核实的 Listing 输入，并返回当前完整问题批次。"""
        task_result_store.save(
            TaskResultRecord(
                task_result_id=task_result_id,
                agent=LISTING_AGENT,
                user_id=principal_id,
                conversation_id=conversation_id,
                run_id=run_id,
                message_id=None,
                result_type=LISTING_RESULT_TYPE,
                generation_status=TaskResultStatus.AWAITING_INPUT,
                input_data={
                    "original_request": original_request,
                    "attachment_ids": attachment_ids,
                    "image_analysis": image_analysis.model_dump(mode="json"),
                    "product_facts": product_facts,
                    "confirmed_answers": confirmed_answers,
                },
            )
        )
        return ToolResult(
            success=True,
            data={
                "questions": questions,
                "task_result": {
                    "task_result_id": task_result_id,
                    "agent": LISTING_AGENT,
                    "result_type": LISTING_RESULT_TYPE,
                    "generation_status": TaskResultStatus.AWAITING_INPUT.value,
                },
            },
            code="QUESTION_REQUIRED",
            message="等待商家核实商品信息",
        ).model_dump_json()

    @tool(LISTING_SAVE_TOOL_NAME, args_schema=SaveListingResultInput)
    def save_listing_result(
        task_result_id: str,
        principal_id: str,
        conversation_id: str,
        run_id: str,
        original_request: str,
        attachment_ids: list[str],
        confirmed_answers: dict[str, object],
        listing_result: dict[str, object],
    ) -> str:
        """保存全部三个经 Pydantic 校验的 Listing 版本。"""
        result_data = SaveListingResultInput.model_validate(
            {
                "task_result_id": task_result_id,
                "principal_id": principal_id,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "original_request": original_request,
                "attachment_ids": attachment_ids,
                "confirmed_answers": confirmed_answers,
                "listing_result": listing_result,
            }
        )
        payload = result_data.listing_result.model_dump(mode="json")
        task_result_store.save(
            TaskResultRecord(
                task_result_id=task_result_id,
                agent=LISTING_AGENT,
                user_id=principal_id,
                conversation_id=conversation_id,
                run_id=run_id,
                message_id=None,
                result_type=LISTING_RESULT_TYPE,
                generation_status=TaskResultStatus.SUCCEEDED,
                input_data={
                    "original_request": original_request,
                    "attachment_ids": attachment_ids,
                    "confirmed_answers": confirmed_answers,
                },
                result_data=payload,
            )
        )
        return ToolResult(
            success=True,
            data={
                "summary": f"已生成并保存 {LISTING_VERSION_COUNT} 个 Listing 版本。",
                "task_result": {
                    "task_result_id": task_result_id,
                    "agent": LISTING_AGENT,
                    "result_type": LISTING_RESULT_TYPE,
                    "generation_status": TaskResultStatus.SUCCEEDED.value,
                },
            },
            message="Listing 已生成",
        ).model_dump_json()

    return ask_listing_questions, save_listing_result
