"""构建只读读取已保存简历的求职助手工具。"""

from collections.abc import Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agent.schemas.tool_result import ToolResult
from agents.job_agent.resume_snapshot import (
    JOB_RESUME_UNAVAILABLE_TOOL_CODE,
    JobResumeSnapshot,
)


def create_read_saved_resume_tool(
    reader: Callable[[str], JobResumeSnapshot],
) -> BaseTool:
    """将后端主体感知读取器封装为无参数模型工具。"""

    @tool("read_saved_resume")
    def read_saved_resume(config: RunnableConfig) -> str:
        """读取数据库中已保存的求职相关简历事实，不返回联系方式或照片。"""

        configurable = config.get("configurable", {})
        principal_id = configurable.get("principal_id")
        if not isinstance(principal_id, str) or not principal_id:
            return ToolResult(
                success=False,
                code=JOB_RESUME_UNAVAILABLE_TOOL_CODE,
                message="当前账号简历暂时无法读取。",
            ).model_dump_json()
        snapshot = reader(principal_id)
        return ToolResult(
            success=snapshot.status != "unavailable",
            data=snapshot.model_dump(mode="json"),
            code=(
                "OK"
                if snapshot.status != "unavailable"
                else JOB_RESUME_UNAVAILABLE_TOOL_CODE
            ),
            message=(
                "已读取简历状态。"
                if snapshot.status != "unavailable"
                else "已保存简历暂时无法读取。"
            ),
        ).model_dump_json()

    return read_saved_resume

