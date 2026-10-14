"""在数据库字段迁移前，将旧 BYTEA 图片转存到阿里云 OSS。"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from infra.aliyun_oss import AliyunOSSImageStorage
from infra.settings import AppSettings
from infra.snowflake import get_snowflake_generator


def migrate_media() -> dict[str, int]:
    """将旧结果图和参考图转存 OSS，成功后清除数据库中的二进制副本。"""
    settings = AppSettings()
    if not settings.database_url:
        raise RuntimeError("必须配置 DATABASE_URL")
    if not settings.aliyun_oss_configured:
        raise RuntimeError("必须先配置完整的阿里云 OSS 参数")

    storage = AliyunOSSImageStorage(
        settings,
        get_snowflake_generator(settings.snowflake_worker_id),
    )
    counts = {"task_results": 0, "message_attachments": 0}
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        _migrate_task_result_images(connection, storage, counts)
        _migrate_reference_images(connection, storage, counts)
    return counts


def _migrate_task_result_images(
    connection: psycopg.Connection[Any],
    storage: AliyunOSSImageStorage,
    counts: dict[str, int],
) -> None:
    """转存已有生成图，并把对象键及图片元数据写入 result_data JSONB。"""
    with connection.cursor() as read_cursor:
        read_cursor.execute(
            """
            SELECT task_result_id, user_id, result_data, image_data,
                   mime_type, width, height, provider_request_id
            FROM task_results
            WHERE image_data IS NOT NULL
            ORDER BY created_at
            """
        )
        while rows := read_cursor.fetchmany(20):
            for row in rows:
                stored = storage.migrate_legacy_result(
                    str(row["user_id"]),
                    str(row["task_result_id"]),
                    row["image_data"],
                    row["mime_type"],
                )
                result_data = dict(row["result_data"] or {})
                result_data["outputs"] = [
                    {
                        "object_key": stored.object_key,
                        "mime_type": stored.mime_type,
                        "file_size": stored.file_size,
                        "width": row["width"],
                        "height": row["height"],
                    }
                ]
                provider_data = result_data.get("provider")
                if not isinstance(provider_data, dict):
                    provider_data = {}
                    result_data["provider"] = provider_data
                if row["provider_request_id"]:
                    provider_data["request_id"] = row["provider_request_id"]
                connection.execute(
                    """
                    UPDATE task_results
                    SET result_data = %s, image_data = NULL
                    WHERE task_result_id = %s
                    """,
                    (Jsonb(result_data), row["task_result_id"]),
                )
                counts["task_results"] += 1


def _migrate_reference_images(
    connection: psycopg.Connection[Any],
    storage: AliyunOSSImageStorage,
    counts: dict[str, int],
) -> None:
    """转存附件表中的图片；引用 ID 保持不变，已有运行可继续读取。"""
    with connection.cursor() as read_cursor:
        read_cursor.execute(
            """
            SELECT attachment_id, user_id, file_name, mime_type, image_data
            FROM message_attachments
            ORDER BY created_at
            """
        )
        while rows := read_cursor.fetchmany(20):
            for row in rows:
                storage.migrate_legacy_reference(
                    str(row["user_id"]),
                    str(row["attachment_id"]),
                    row["file_name"],
                    row["mime_type"],
                    row["image_data"],
                )
                connection.execute(
                    "DELETE FROM message_attachments WHERE attachment_id = %s",
                    (row["attachment_id"],),
                )
                counts["message_attachments"] += 1


if __name__ == "__main__":
    print(migrate_media())
