"""OpenAlex Works API 的异步 HTTPX 客户端。"""

import asyncio
from typing import Any

import httpx

from infra.settings import AppSettings
from agents.research_agent.constants import RESEARCH_MAX_BACKOFF_SECONDS

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_SELECT_FIELDS = (
    "id,title,publication_year,publication_date,authorships,primary_location,"
    "best_oa_location,abstract_inverted_index,doi,cited_by_count,language"
)
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})


class OpenAlexError(Exception):
    """可安全转换为业务失败状态的 OpenAlex 错误。"""


class OpenAlexClient:
    """固定访问 OpenAlex Works API，并限制超时、重试和响应形状。"""

    def __init__(
        self,
        settings: AppSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """注入已校验的运行配置和可选 HTTPX 测试传输。"""
        self._settings = settings
        self._transport = transport

    async def search_works(
        self,
        *,
        query: str,
        per_page: int,
        year_from: int | None,
        year_to: int | None,
        language: str | None,
        sort: str,
    ) -> list[dict[str, Any]]:
        """执行一次文本检索并在限定范围内处理暂时性失败。"""
        parameters: dict[str, str | int] = {
            "search": query,
            "per_page": per_page,
            "select": OPENALEX_SELECT_FIELDS,
        }
        filters = _build_filters(year_from, year_to, language)
        if filters:
            parameters["filter"] = ",".join(filters)
        sort_parameter = _sort_parameter(sort)
        if sort_parameter is not None:
            parameters["sort"] = sort_parameter
        headers = {"Accept": "application/json"}
        api_key = self._settings.openalex_api_key.get_secret_value().strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(
            timeout=self._settings.openalex_timeout_seconds,
            transport=self._transport,
        ) as client:
            for attempt in range(self._settings.openalex_max_retries + 1):
                try:
                    response = await client.get(
                        OPENALEX_WORKS_URL,
                        params=parameters,
                        headers=headers,
                    )
                except httpx.RequestError:
                    if attempt >= self._settings.openalex_max_retries:
                        raise OpenAlexError("OpenAlex 暂时无法连接") from None
                    await self._wait_before_retry(attempt)
                    continue

                if response.status_code in RETRYABLE_HTTP_STATUSES:
                    if attempt >= self._settings.openalex_max_retries:
                        raise OpenAlexError("OpenAlex 暂时无法完成检索")
                    await self._wait_before_retry(attempt, response)
                    continue
                if response.is_error:
                    raise OpenAlexError("OpenAlex 拒绝了检索请求")
                try:
                    payload = response.json()
                except ValueError:
                    raise OpenAlexError("OpenAlex 返回了无法识别的数据") from None
                if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                    raise OpenAlexError("OpenAlex 返回了无法识别的数据")
                return [
                    item
                    for item in payload["results"]
                    if isinstance(item, dict)
                ]

        raise OpenAlexError("OpenAlex 暂时无法完成检索")

    async def _wait_before_retry(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> None:
        """采用有上限的指数退避，并尊重有效的 Retry-After 秒数。"""
        base_delay = self._settings.openalex_retry_delay_seconds
        retry_after = response.headers.get("Retry-After") if response is not None else None
        try:
            requested_delay = float(retry_after) if retry_after is not None else None
        except ValueError:
            requested_delay = None
        exponential_delay = base_delay * (2**attempt)
        delay = min(
            max(requested_delay if requested_delay is not None else exponential_delay, 0),
            RESEARCH_MAX_BACKOFF_SECONDS,
        )
        if delay:
            await asyncio.sleep(delay)


def _build_filters(
    year_from: int | None,
    year_to: int | None,
    language: str | None,
) -> list[str]:
    """生成 OpenAlex 支持的年份与语言过滤表达式。"""
    filters: list[str] = []
    if year_from is not None and year_to is not None:
        filters.append(f"publication_year:{year_from}-{year_to}")
    elif year_from is not None:
        filters.append(f"from_publication_date:{year_from}-01-01")
    elif year_to is not None:
        filters.append(f"to_publication_date:{year_to}-12-31")
    if language:
        filters.append(f"language:{language}")
    return filters


def _sort_parameter(sort: str) -> str | None:
    """把公开排序枚举映射到 OpenAlex Works 排序字段。"""
    if sort == "citation_count":
        return "cited_by_count:desc"
    if sort == "publication_date":
        return "publication_date:desc"
    return None
