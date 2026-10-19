"""向通用智能体提供项目中已注册的智能体目录。"""

from langchain_core.tools import tool

from agent.schemas.tool_result import ToolResult
from agents.registry import PROJECT_AGENT_DEFINITIONS


@tool("list_project_agents")
def list_project_agents() -> str:
    """列出 NexusAI 已注册的智能体及其用途和图片输入能力。"""
    agents = [
        {
            "agent": definition.agent,
            "name": definition.name,
            "description": definition.description,
            "supports_image_upload": definition.supports_image_upload,
        }
        for definition in PROJECT_AGENT_DEFINITIONS
    ]
    return ToolResult(
        success=True,
        data={"agents": agents},
        message="已读取项目智能体目录",
    ).model_dump_json()
