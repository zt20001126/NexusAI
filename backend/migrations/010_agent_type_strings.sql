-- 将智能体标识从静态雪花 ID 改为会话上的字符串枚举。
-- 依赖 009_task_results_compact_schema.sql 已执行。
BEGIN;

LOCK TABLE conversations, agent_runs IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM conversations
        WHERE agent_id IS NULL OR agent_id NOT IN (
            1874244142498832385,
            1874244142498832386,
            1874244142498832387,
            1874244142498832388,
            1874244142498832389,
            1874244142498832390,
            1874244142498832391
        )
    ) THEN
        RAISE EXCEPTION 'Cannot migrate a conversation with an unknown agent ID';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM agent_runs
        WHERE agent_id IS NULL OR agent_id NOT IN (
            1874244142498832385,
            1874244142498832386,
            1874244142498832387,
            1874244142498832388,
            1874244142498832389,
            1874244142498832390,
            1874244142498832391
        )
    ) THEN
        RAISE EXCEPTION 'Cannot migrate a run with an unknown agent ID';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM agent_runs AS runs
        JOIN conversations AS conversations
          ON conversations.conversation_id = runs.conversation_id
        WHERE runs.agent_id <> conversations.agent_id
    ) THEN
        RAISE EXCEPTION 'Conversation and run agents do not match';
    END IF;
END $$;

ALTER TABLE conversations RENAME COLUMN agent_id TO agent;
ALTER TABLE conversations
    ALTER COLUMN agent TYPE VARCHAR(64)
    USING CASE agent
        WHEN 1874244142498832385 THEN 'common_agent'
        WHEN 1874244142498832386 THEN 'image_agent'
        WHEN 1874244142498832387 THEN 'listing_agent'
        WHEN 1874244142498832388 THEN 'research_agent'
        WHEN 1874244142498832389 THEN 'labor_law_agent'
        WHEN 1874244142498832390 THEN 'literature_reader_agent'
        WHEN 1874244142498832391 THEN 'basic_conversation_agent'
    END;

ALTER TABLE conversations
    ADD CONSTRAINT ck_conversations_agent_type CHECK (
        agent IN (
            'common_agent',
            'basic_conversation_agent',
            'image_agent',
            'listing_agent',
            'research_agent',
            'labor_law_agent',
            'literature_reader_agent'
        )
    );

COMMENT ON COLUMN conversations.agent IS '会话所属智能体的字符串枚举值';

ALTER TABLE agent_runs DROP COLUMN agent_id;
ALTER TABLE task_results DROP COLUMN IF EXISTS agent_id;
DROP INDEX IF EXISTS idx_task_results_agent_created;

COMMIT;
