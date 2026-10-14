"""通过 TokenHub 生图并将图片对象持久化到阿里云 OSS。"""

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

from agent.constants import MAX_REFERENCE_IMAGE_COUNT
from agent.errors import AttachmentAccessDeniedError
from agent.persistence.interfaces import AttachmentStore, TaskResultStore
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from agent.schemas.tool_result import ToolResult
from agents.image_generation.constants import (
    IMAGE_AGENT_ID,
    IMAGE_PROMPT_MAX_LENGTH,
    IMAGE_RESULT_TYPE,
    IMAGE_RESULT_URL_PREFIX,
)
from agents.image_generation.providers.result_downloader import ImageResultDownloader
from agents.image_generation.providers.tokenhub_client import (
    TokenHubImageClient,
    TokenHubImageError,
)
from agents.image_generation.schemas import GenerateImageToolInput
from infra.object_storage import ObjectStorageError, StoredImageObject
from infra.settings import AppSettings

logger = logging.getLogger(__name__)


def create_generate_image_tool(
    settings: AppSettings,
    image_client: TokenHubImageClient,
    downloader: ImageResultDownloader,
    task_result_store: TaskResultStore,
    attachment_store: AttachmentStore,
):
    """创建捕获 TokenHub、OSS 和统一结果仓储的图片生成工具。"""

    @tool("generate_image", args_schema=GenerateImageToolInput)
    async def generate_image(
        task_result_id: str,
        principal_id: str,
        conversation_id: str,
        run_id: str,
        prompt: str,
        size: str | None = None,
        generate_max_pixels: int | None = None,
        resize_max_pixels: int | None = None,
        seed: int | None = None,
        footnote: str | None = None,
        use_search_tool: bool = False,
        attachment_ids: list[str] | None = None,
    ) -> str:
        """生成电商图片，保存输入元数据和 OSS 对象键，不将图片字节写入数据库。"""
        resolved_attachment_ids = attachment_ids or []
        tool_input = GenerateImageToolInput(
            task_result_id=task_result_id,
            principal_id=principal_id,
            conversation_id=conversation_id,
            run_id=run_id,
            prompt=prompt[:IMAGE_PROMPT_MAX_LENGTH],
            size=size,
            generate_max_pixels=generate_max_pixels,
            resize_max_pixels=resize_max_pixels,
            seed=seed,
            footnote=footnote,
            use_search_tool=use_search_tool,
            attachment_ids=resolved_attachment_ids,
        )
        generation_options = tool_input.options()
        input_data: dict[str, Any] = {
            "prompt": tool_input.prompt,
            "parameters": generation_options.model_dump(exclude_none=True),
            "reference_attachment_ids": resolved_attachment_ids,
        }

        task_result_store.save(
            TaskResultRecord(
                task_result_id=task_result_id,
                agent_id=IMAGE_AGENT_ID,
                user_id=principal_id,
                conversation_id=conversation_id,
                run_id=run_id,
                message_id=None,
                result_type=IMAGE_RESULT_TYPE,
                generation_status=TaskResultStatus.RUNNING,
                input_data=input_data,
            )
        )

        try:
            references = await asyncio.to_thread(
                attachment_store.list_for_generation,
                resolved_attachment_ids,
                principal_id,
                conversation_id,
            )
            if (
                len(references) > MAX_REFERENCE_IMAGE_COUNT
                or any(
                    item.file_size > settings.image_upload_max_bytes
                    for item in references
                )
            ):
                raise AttachmentAccessDeniedError()
            input_data["reference_images"] = [
                {
                    "object_key": item.object_key,
                    "file_name": item.file_name,
                    "mime_type": item.mime_type,
                    "file_size": item.file_size,
                }
                for item in references
            ]
            task_result_store.save(
                TaskResultRecord(
                    task_result_id=task_result_id,
                    agent_id=IMAGE_AGENT_ID,
                    user_id=principal_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    message_id=None,
                    result_type=IMAGE_RESULT_TYPE,
                    generation_status=TaskResultStatus.RUNNING,
                    input_data=input_data,
                )
            )

            provider_result = await image_client.generate(
                prompt=tool_input.prompt,
                reference_images=[(item.mime_type, item.image_data) for item in references],
                options=generation_options,
                session_id=conversation_id,
            )
            image_data, mime_type = await downloader.download(provider_result.image_url)
            stored_image: StoredImageObject = await asyncio.to_thread(
                attachment_store.save_result,
                principal_id,
                task_result_id,
                image_data,
                mime_type,
            )
            output = {
                "object_key": stored_image.object_key,
                "mime_type": stored_image.mime_type,
                "file_size": stored_image.file_size,
                "width": provider_result.width,
                "height": provider_result.height,
            }
            result_data = {
                "outputs": [output],
                "provider": {
                    "model": provider_result.provider_model,
                    "request_id": provider_result.request_id,
                    "usage_total_tokens": provider_result.metadata.get(
                        "usage_total_tokens"
                    ),
                },
            }
            task_result_store.save(
                TaskResultRecord(
                    task_result_id=task_result_id,
                    agent_id=IMAGE_AGENT_ID,
                    user_id=principal_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    message_id=None,
                    result_type=IMAGE_RESULT_TYPE,
                    generation_status=TaskResultStatus.SUCCEEDED,
                    input_data=input_data,
                    result_data=result_data,
                )
            )
            stable_image_url = f"{IMAGE_RESULT_URL_PREFIX}/{task_result_id}/image"
            task_result_data = {
                "task_result_id": task_result_id,
                "agent_id": IMAGE_AGENT_ID,
                "generation_status": TaskResultStatus.SUCCEEDED.value,
                "image_url": stable_image_url,
                **{key: value for key, value in output.items() if key != "object_key"},
            }
            return ToolResult(
                success=True,
                data={"summary": "商品图片已生成并保存。", "task_result": task_result_data},
            ).model_dump_json()
        except TokenHubImageError as error:
            logger.warning(
                "图片生成失败 task_result_id=%s code=%s request_id=%s",
                task_result_id,
                error.code,
                error.request_id,
            )
            task_result_store.set_status(
                task_result_id,
                principal_id,
                TaskResultStatus.FAILED,
            )
            return _failure(error.code, error.public_message, task_result_id)
        except AttachmentAccessDeniedError:
            task_result_store.set_status(
                task_result_id,
                principal_id,
                TaskResultStatus.FAILED,
            )
            return _failure(
                "ATTACHMENT_ACCESS_DENIED",
                "上传图片不可访问，请重新上传后再试。",
                task_result_id,
            )
        except ObjectStorageError:
            logger.exception("图片 OSS 保存失败 task_result_id=%s", task_result_id)
            task_result_store.set_status(
                task_result_id,
                principal_id,
                TaskResultStatus.FAILED,
            )
            return _failure(
                "IMAGE_STORAGE_FAILED",
                "图片暂时无法保存，请稍后重试。",
                task_result_id,
            )

    return generate_image


def _failure(code: str, message: str, task_result_id: str) -> str:
    """构造本轮可见的错误响应；失败详情不写入任务结果数据库。"""
    return ToolResult(
        success=False,
        data={
            "summary": message,
            "task_result": {
                "task_result_id": task_result_id,
                "agent_id": IMAGE_AGENT_ID,
                "generation_status": TaskResultStatus.FAILED.value,
            },
        },
        code=code,
        message=message,
    ).model_dump_json()
