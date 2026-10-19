-- 将消息 JSON 内容字段统一命名为 content，不改写字段值。
BEGIN;

ALTER TABLE messages RENAME COLUMN context TO content;
COMMENT ON COLUMN messages.content IS '按顺序保存文字、图片引用和问题答案的 JSON 内容块';

COMMIT;
