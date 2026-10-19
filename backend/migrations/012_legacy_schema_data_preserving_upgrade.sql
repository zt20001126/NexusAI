-- 将仍使用旧列名和雪花 Agent ID 的数据库升级到当前模型，并保留任务结果数据。
-- 适用于 task_results 仍有 task_result_id/generation_status 的数据库；
-- 不要先执行会清空 task_results 的 009 迁移。
BEGIN;

LOCK TABLE conversations, agent_runs, task_results IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'conversations'
          AND column_name = 'agent_id'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'agent_runs'
          AND column_name = 'agent_id'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'task_results'
          AND column_name = 'task_result_id'
    ) THEN
        RAISE EXCEPTION 'Database is not at the expected legacy schema; inspect migrations before upgrading';
    END IF;

    IF EXISTS (
        SELECT 1 FROM conversations
        WHERE agent_id IS NULL OR agent_id NOT IN (
            132633958813786113, 132633958813786114,
            132633958813786115, 132633958813786116,
            132633958813786117, 132633958813786118,
            132633958813786119,
            1874244142498832385, 1874244142498832386,
            1874244142498832387, 1874244142498832388,
            1874244142498832389, 1874244142498832390,
            1874244142498832391
        )
    ) THEN
        RAISE EXCEPTION 'Cannot migrate a conversation with an unknown agent ID';
    END IF;

    IF EXISTS (
        SELECT 1 FROM agent_runs
        WHERE agent_id IS NULL OR agent_id NOT IN (
            132633958813786113, 132633958813786114,
            132633958813786115, 132633958813786116,
            132633958813786117, 132633958813786118,
            132633958813786119,
            1874244142498832385, 1874244142498832386,
            1874244142498832387, 1874244142498832388,
            1874244142498832389, 1874244142498832390,
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

    IF EXISTS (
        SELECT 1
        FROM task_results AS results
        JOIN conversations AS conversations
          ON conversations.conversation_id = results.conversation_id
        WHERE results.user_id <> conversations.owner_id
           OR results.agent_id <> conversations.agent_id
    ) THEN
        RAISE EXCEPTION 'Task result owner or agent does not match its conversation';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM task_results AS results
        JOIN agent_runs AS runs ON runs.run_id = results.run_id
        WHERE results.conversation_id <> runs.conversation_id
           OR results.agent_id <> runs.agent_id
    ) THEN
        RAISE EXCEPTION 'Task result run does not match its conversation';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM task_results AS results
        JOIN messages AS messages ON messages.message_id = results.message_id
        WHERE results.conversation_id <> messages.conversation_id
    ) THEN
        RAISE EXCEPTION 'Task result message does not match its conversation';
    END IF;

    IF EXISTS (
        SELECT 1 FROM task_results
        WHERE generation_status NOT IN (
            'pending', 'awaiting_input', 'running',
            'succeeded', 'failed', 'cancelled'
        )
    ) THEN
        RAISE EXCEPTION 'Cannot migrate a task result with an unknown status';
    END IF;

    IF EXISTS (
        SELECT 1 FROM agent_runs
        WHERE status NOT IN ('queued', 'running', 'waiting', 'completed', 'cancelled', 'failed')
    ) THEN
        RAISE EXCEPTION 'Cannot migrate a run with an unknown status';
    END IF;
END $$;

ALTER TABLE conversations RENAME COLUMN agent_id TO agent;
ALTER TABLE conversations
    ALTER COLUMN agent TYPE VARCHAR(64)
    USING CASE agent
        WHEN 132633958813786113 THEN 'common_agent'
        WHEN 132633958813786114 THEN 'image_agent'
        WHEN 132633958813786115 THEN 'listing_agent'
        WHEN 132633958813786116 THEN 'research_agent'
        WHEN 132633958813786117 THEN 'labor_law_agent'
        WHEN 132633958813786118 THEN 'literature_reader_agent'
        WHEN 132633958813786119 THEN 'basic_conversation_agent'
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

DROP INDEX IF EXISTS idx_task_results_agent_created;
DROP INDEX IF EXISTS idx_task_results_run;
DROP INDEX IF EXISTS idx_task_results_user_created;
ALTER TABLE task_results DROP CONSTRAINT IF EXISTS task_results_generation_status_check;
ALTER TABLE task_results RENAME COLUMN task_result_id TO id;
ALTER TABLE task_results RENAME COLUMN generation_status TO status;
ALTER TABLE task_results RENAME COLUMN input_data TO input;
ALTER TABLE task_results RENAME COLUMN result_data TO result;
ALTER TABLE task_results
    DROP COLUMN agent_id,
    DROP COLUMN user_id,
    DROP COLUMN run_id,
    DROP COLUMN result_type,
    DROP COLUMN updated_at;
ALTER TABLE task_results ALTER COLUMN input SET DEFAULT '{}'::jsonb;
ALTER TABLE task_results ALTER COLUMN result SET DEFAULT '{}'::jsonb;
ALTER TABLE task_results
    ADD CONSTRAINT ck_task_results_status CHECK (
        status IN (
            'pending', 'awaiting_input', 'running',
            'succeeded', 'failed', 'cancelled'
        )
    );
CREATE INDEX IF NOT EXISTS idx_task_results_conversation_created
    ON task_results (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_results_message
    ON task_results (message_id);
COMMENT ON TABLE task_results IS '所有智能体共享的任务结果及 OSS 对象元数据';
COMMENT ON COLUMN task_results.id IS '任务结果雪花 ID';
COMMENT ON COLUMN task_results.conversation_id IS '任务所属会话 ID';
COMMENT ON COLUMN task_results.message_id IS '任务结果关联的助手消息 ID';
COMMENT ON COLUMN task_results.status IS '任务生命周期状态';
COMMENT ON COLUMN task_results.input IS '任务输入、参数和参考图 OSS 对象元数据';
COMMENT ON COLUMN task_results.result IS '生成结果 OSS 对象元数据及智能体扩展数据';
COMMENT ON COLUMN task_results.created_at IS '任务结果创建时间';

ALTER TABLE agent_runs DROP COLUMN agent_id;
ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS ck_agent_runs_status;
ALTER TABLE agent_runs
    ADD CONSTRAINT ck_agent_runs_status
    CHECK (status IN ('queued', 'running', 'waiting', 'completed', 'cancelled', 'failed'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_request_id
    ON agent_runs ((metadata->>'request_key'))
    WHERE metadata ? 'request_key';
COMMENT ON INDEX uq_agent_runs_request_id IS '防止同一聊天提交请求创建重复运行';

COMMIT;
