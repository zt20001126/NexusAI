-- 将消息正文和上传图片引用合并到 JSON context，并改用创建时间分页。
-- 只用于仍含 content、sequence、run_id 的已有 messages 表。
BEGIN;

ALTER TABLE messages
    ADD COLUMN context JSONB NOT NULL DEFAULT '{"blocks": []}'::jsonb;

UPDATE messages
SET context = jsonb_build_object(
    'blocks', jsonb_build_array(jsonb_build_object('type', 'text', 'text', content))
);

WITH first_user_messages AS (
    SELECT DISTINCT ON (run_id) message_id, run_id
    FROM messages
    WHERE role = 'user' AND run_id IS NOT NULL
    ORDER BY run_id, sequence, message_id
), image_blocks AS (
    SELECT first_message.message_id,
           jsonb_agg(
               jsonb_build_object('type', 'image', 'attachment_id', image.attachment_id)
               ORDER BY image.ordinality
           ) AS blocks
    FROM first_user_messages AS first_message
    JOIN agent_runs AS run ON run.run_id = first_message.run_id
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
            WHEN jsonb_typeof(run.metadata->'attachment_ids') = 'array'
            THEN run.metadata->'attachment_ids'
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS image(attachment_id, ordinality)
    GROUP BY first_message.message_id
)
UPDATE messages AS message
SET context = jsonb_set(
    message.context,
    '{blocks}',
    message.context->'blocks' || image_blocks.blocks
)
FROM image_blocks
WHERE message.message_id = image_blocks.message_id;

ALTER TABLE messages
    DROP CONSTRAINT IF EXISTS uq_messages_conversation_sequence,
    DROP CONSTRAINT IF EXISTS messages_conversation_id_sequence_key,
    DROP CONSTRAINT IF EXISTS fk_messages_run;

DROP INDEX IF EXISTS idx_messages_conversation_sequence;

ALTER TABLE messages
    DROP COLUMN IF EXISTS attachment_ids,
    DROP COLUMN content,
    DROP COLUMN sequence,
    DROP COLUMN run_id;

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created_id
    ON messages (conversation_id, created_at DESC, message_id DESC);

COMMIT;
