"""科研文献检索专用 REST 接口。"""

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_principal_id
from app.schemas.research import ResearchRequest

router = APIRouter(prefix="/api/v1/research", tags=["科研文献检索"])


def _success(data: Any) -> dict[str, Any]:
    """构造项目统一成功响应。"""
    return {"success": True, "data": data}


@router.post("/search")
async def search_research_literature(
    payload: ResearchRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """通过共享 Agent Runner 检索文献并返回结构化论文结果。"""
    result = await request.app.state.research_service.search(
        payload=payload,
        principal_id=principal_id,
    )
    return _success(result.model_dump(mode="json"))
