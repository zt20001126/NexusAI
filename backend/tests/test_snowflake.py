"""验证雪花 ID 生成器按 worker ID 共享实例。"""

from infra.snowflake import get_snowflake_generator


def test_default_and_explicit_zero_worker_share_generator() -> None:
    """省略 worker ID 与显式传入零必须使用同一生成器。"""
    default_generator = get_snowflake_generator()
    explicit_generator = get_snowflake_generator(0)

    assert default_generator is explicit_generator
    assert int(default_generator.next_id_string()) < int(explicit_generator.next_id_string())
