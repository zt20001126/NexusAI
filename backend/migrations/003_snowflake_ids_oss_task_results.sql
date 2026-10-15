-- 旧版运行：先执行 `python -m migrations.migrate_media_to_oss`，再执行本脚本。
-- 该脚本保留会话、消息和结果关系，把应用业务 ID 迁移为雪花 BIGINT。
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM agent_runs
        WHERE status IN ('running', 'waiting')
    ) THEN
        RAISE EXCEPTION '请先结束或取消运行中的智能体任务，再迁移雪花 ID';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'task_results'
          AND column_name = 'image_data'
    ) AND EXISTS (
        SELECT 1 FROM task_results WHERE image_data IS NOT NULL
    ) THEN
        RAISE EXCEPTION '请先将 task_results.image_data 转存到 OSS';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'task_results'
          AND column_name = 'image_url'
    ) AND EXISTS (
        SELECT 1
        FROM task_results
        WHERE image_url IS NOT NULL
          AND COALESCE(
              jsonb_typeof(result_data #> '{outputs,0,object_key}'),
              'null'
          ) <> 'string'
    ) THEN
        RAISE EXCEPTION '存在未转存的旧图片地址，请先将图片写入 OSS';
    END IF;

    IF to_regclass('public.message_attachments') IS NOT NULL
       AND EXISTS (SELECT 1 FROM message_attachments) THEN
        RAISE EXCEPTION '请先将 message_attachments 图片转存到 OSS';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM task_results AS results
        JOIN conversations AS conversations
          ON conversations.conversation_id = results.conversation_id
        WHERE results.user_id <> conversations.owner_id
    ) THEN
        RAISE EXCEPTION '任务结果用户与会话所有者不一致，不能自动迁移';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM agent_runs AS runs
        JOIN conversations AS conversations
          ON conversations.conversation_id = runs.conversation_id
        WHERE runs.agent_id <> conversations.agent_id
    ) OR EXISTS (
        SELECT 1
        FROM task_results AS results
        JOIN agent_runs AS runs ON runs.run_id = results.run_id
        WHERE results.agent_id <> runs.agent_id
    ) THEN
        RAISE EXCEPTION '会话、运行和任务结果的智能体标识不一致，不能自动迁移';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS user_identities (
    user_id BIGINT PRIMARY KEY,
    external_principal TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TEMP TABLE snowflake_id_migration_map (
    entity_type TEXT NOT NULL,
    legacy_id TEXT NOT NULL,
    snowflake_id BIGINT NOT NULL,
    PRIMARY KEY (entity_type, legacy_id),
    UNIQUE (snowflake_id)
) ON COMMIT DROP;

WITH base AS MATERIALIZED (
    SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::BIGINT
           - 1704067200000 AS elapsed_milliseconds
),
legacy_ids AS MATERIALIZED (
    SELECT 'conversation'::TEXT AS entity_type, conversation_id::TEXT AS legacy_id
    FROM conversations
    UNION
    SELECT 'run', run_id::TEXT FROM agent_runs
    UNION
    SELECT 'message', message_id::TEXT FROM messages
    UNION
    SELECT 'task_result', task_result_id::TEXT FROM task_results
    UNION
    SELECT 'task_result', metadata->>'task_result_id'
    FROM agent_runs
    WHERE metadata->>'task_result_id' IS NOT NULL
    UNION
    SELECT 'user', owner_id::TEXT FROM conversations
    UNION
    SELECT 'user', user_id::TEXT FROM task_results
    UNION
    SELECT 'message', message_id::TEXT FROM task_results WHERE message_id IS NOT NULL
),
ranked_ids AS (
    SELECT entity_type,
           legacy_id,
           row_number() OVER (ORDER BY entity_type, legacy_id) - 1 AS sequence_value
    FROM legacy_ids
),
allocated_ids AS (
    SELECT ranked_ids.entity_type,
           ranked_ids.legacy_id,
           (((base.elapsed_milliseconds + ranked_ids.sequence_value / 4096) << 22)
            | (1023::BIGINT << 12)
            | (ranked_ids.sequence_value % 4096))::BIGINT AS snowflake_id
    FROM ranked_ids CROSS JOIN base
)
INSERT INTO snowflake_id_migration_map (entity_type, legacy_id, snowflake_id)
SELECT entity_type, legacy_id, snowflake_id FROM allocated_ids;

DO $$
DECLARE
    unknown_agent TEXT;
    constraint_record RECORD;
    checkpoint_table TEXT;
BEGIN
    SELECT agent_code INTO unknown_agent
    FROM (
        SELECT agent_id::TEXT AS agent_code FROM conversations
        UNION SELECT agent_id::TEXT FROM agent_runs
        UNION SELECT agent_id::TEXT FROM task_results
    ) AS existing_agents
    WHERE agent_code NOT IN ('default', 'taobao_image')
    LIMIT 1;
    IF unknown_agent IS NOT NULL THEN
        RAISE EXCEPTION '未配置智能体雪花 ID：%', unknown_agent;
    END IF;

    FOR constraint_record IN
        SELECT conrelid::REGCLASS AS table_name, conname
        FROM pg_constraint
        WHERE contype = 'f'
          AND (
              conrelid IN (
                  'conversations'::REGCLASS,
                  'agent_runs'::REGCLASS,
                  'messages'::REGCLASS,
                  'task_results'::REGCLASS
              )
              OR confrelid IN (
                  'conversations'::REGCLASS,
                  'agent_runs'::REGCLASS,
                  'messages'::REGCLASS,
                  'task_results'::REGCLASS
              )
          )
    LOOP
        EXECUTE format(
            'ALTER TABLE %s DROP CONSTRAINT %I',
            constraint_record.table_name,
            constraint_record.conname
        );
    END LOOP;

    INSERT INTO user_identities (user_id, external_principal)
    SELECT snowflake_id, legacy_id
    FROM snowflake_id_migration_map
    WHERE entity_type = 'user'
    ON CONFLICT (external_principal) DO NOTHING;

    UPDATE conversations AS records
    SET conversation_id = ids.snowflake_id::TEXT,
        owner_id = users.snowflake_id::TEXT,
        agent_id = CASE records.agent_id
            WHEN 'default' THEN '132633958813786113'
            WHEN 'taobao_image' THEN '132633958813786114'
        END
    FROM snowflake_id_migration_map AS ids,
         snowflake_id_migration_map AS users
    WHERE ids.entity_type = 'conversation'
      AND ids.legacy_id = records.conversation_id
      AND users.entity_type = 'user'
      AND users.legacy_id = records.owner_id;

    UPDATE agent_runs AS records
    SET run_id = run_ids.snowflake_id::TEXT,
        conversation_id = conversations.snowflake_id::TEXT,
        agent_id = CASE records.agent_id
            WHEN 'default' THEN '132633958813786113'
            WHEN 'taobao_image' THEN '132633958813786114'
        END,
        metadata = CASE
            WHEN records.metadata ? 'task_result_id' THEN jsonb_set(
                records.metadata,
                '{task_result_id}',
                to_jsonb(results.snowflake_id::TEXT),
                false
            )
            ELSE records.metadata
        END
    FROM snowflake_id_migration_map AS run_ids,
         snowflake_id_migration_map AS conversations,
         snowflake_id_migration_map AS results
    WHERE run_ids.entity_type = 'run'
      AND run_ids.legacy_id = records.run_id
      AND conversations.entity_type = 'conversation'
      AND conversations.legacy_id = records.conversation_id
      AND results.entity_type = 'task_result'
      AND results.legacy_id = records.metadata->>'task_result_id';

    -- 没有 task_result_id 的运行仍需迁移主键、会话和智能体 ID。
    UPDATE agent_runs AS records
    SET run_id = run_ids.snowflake_id::TEXT,
        conversation_id = conversations.snowflake_id::TEXT,
        agent_id = CASE records.agent_id
            WHEN 'default' THEN '132633958813786113'
            WHEN 'taobao_image' THEN '132633958813786114'
        END
    FROM snowflake_id_migration_map AS run_ids,
         snowflake_id_migration_map AS conversations
    WHERE run_ids.entity_type = 'run'
      AND run_ids.legacy_id = records.run_id
      AND conversations.entity_type = 'conversation'
      AND conversations.legacy_id = records.conversation_id
      AND NOT (records.metadata ? 'task_result_id');

    UPDATE messages AS records
    SET message_id = message_ids.snowflake_id::TEXT,
        conversation_id = conversations.snowflake_id::TEXT,
        run_id = runs.snowflake_id::TEXT
    FROM snowflake_id_migration_map AS message_ids,
         snowflake_id_migration_map AS conversations,
         snowflake_id_migration_map AS runs
    WHERE message_ids.entity_type = 'message'
      AND message_ids.legacy_id = records.message_id
      AND conversations.entity_type = 'conversation'
      AND conversations.legacy_id = records.conversation_id
      AND runs.entity_type = 'run'
      AND runs.legacy_id = records.run_id;

    UPDATE messages AS records
    SET message_id = message_ids.snowflake_id::TEXT,
        conversation_id = conversations.snowflake_id::TEXT
    FROM snowflake_id_migration_map AS message_ids,
         snowflake_id_migration_map AS conversations
    WHERE message_ids.entity_type = 'message'
      AND message_ids.legacy_id = records.message_id
      AND conversations.entity_type = 'conversation'
      AND conversations.legacy_id = records.conversation_id
      AND records.run_id IS NULL;

    UPDATE task_results AS records
    SET task_result_id = result_ids.snowflake_id::TEXT,
        agent_id = CASE records.agent_id
            WHEN 'default' THEN '132633958813786113'
            WHEN 'taobao_image' THEN '132633958813786114'
        END,
        user_id = users.snowflake_id::TEXT,
        conversation_id = conversations.snowflake_id::TEXT,
        run_id = runs.snowflake_id::TEXT,
        message_id = messages.snowflake_id::TEXT
    FROM snowflake_id_migration_map AS result_ids,
         snowflake_id_migration_map AS users,
         snowflake_id_migration_map AS conversations,
         snowflake_id_migration_map AS runs,
         snowflake_id_migration_map AS messages
    WHERE result_ids.entity_type = 'task_result'
      AND result_ids.legacy_id = records.task_result_id
      AND users.entity_type = 'user'
      AND users.legacy_id = records.user_id
      AND conversations.entity_type = 'conversation'
      AND conversations.legacy_id = records.conversation_id
      AND runs.entity_type = 'run'
      AND runs.legacy_id = records.run_id
      AND messages.entity_type = 'message'
      AND messages.legacy_id = records.message_id;

    UPDATE task_results AS records
    SET task_result_id = result_ids.snowflake_id::TEXT,
        agent_id = CASE records.agent_id
            WHEN 'default' THEN '132633958813786113'
            WHEN 'taobao_image' THEN '132633958813786114'
        END,
        user_id = users.snowflake_id::TEXT,
        conversation_id = conversations.snowflake_id::TEXT,
        run_id = runs.snowflake_id::TEXT,
        message_id = NULL
    FROM snowflake_id_migration_map AS result_ids,
         snowflake_id_migration_map AS users,
         snowflake_id_migration_map AS conversations,
         snowflake_id_migration_map AS runs
    WHERE result_ids.entity_type = 'task_result'
      AND result_ids.legacy_id = records.task_result_id
      AND users.entity_type = 'user'
      AND users.legacy_id = records.user_id
      AND conversations.entity_type = 'conversation'
      AND conversations.legacy_id = records.conversation_id
      AND runs.entity_type = 'run'
      AND runs.legacy_id = records.run_id
      AND records.message_id IS NULL;

    FOREACH checkpoint_table IN ARRAY ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes']
    LOOP
        IF to_regclass(format('public.%I', checkpoint_table)) IS NOT NULL THEN
            EXECUTE format($migration$
                UPDATE %I AS checkpoint
                SET thread_id = identities.external_principal || ':' ||
                    CASE conversations.agent_id
                        WHEN '132633958813786113' THEN 'default'
                        WHEN '132633958813786114' THEN 'taobao_image'
                    END || ':' || ids.snowflake_id::TEXT
                FROM snowflake_id_migration_map AS ids
                JOIN conversations
                  ON conversations.conversation_id = ids.snowflake_id::TEXT
                JOIN user_identities AS identities
                  ON identities.user_id = conversations.owner_id::BIGINT
                WHERE ids.entity_type = 'conversation'
                  AND (
                      checkpoint.thread_id = identities.external_principal || ':' || ids.legacy_id
                      OR checkpoint.thread_id = identities.external_principal || ':' ||
                         CASE conversations.agent_id
                             WHEN '132633958813786113' THEN 'default'
                             WHEN '132633958813786114' THEN 'taobao_image'
                         END || ':' || ids.legacy_id
                  )
            $migration$, checkpoint_table);
        END IF;
    END LOOP;
END $$;

-- 002 将 agent_id 默认值设为文本；移除旧默认值后才能改为雪花 BIGINT。
ALTER TABLE conversations
    ALTER COLUMN agent_id DROP DEFAULT;
ALTER TABLE agent_runs
    ALTER COLUMN agent_id DROP DEFAULT;

ALTER TABLE conversations
    ALTER COLUMN conversation_id TYPE BIGINT USING conversation_id::BIGINT,
    ALTER COLUMN owner_id TYPE BIGINT USING owner_id::BIGINT,
    ALTER COLUMN agent_id TYPE BIGINT USING agent_id::BIGINT;
ALTER TABLE agent_runs
    ALTER COLUMN run_id TYPE BIGINT USING run_id::BIGINT,
    ALTER COLUMN conversation_id TYPE BIGINT USING conversation_id::BIGINT,
    ALTER COLUMN agent_id TYPE BIGINT USING agent_id::BIGINT;
ALTER TABLE messages
    ALTER COLUMN message_id TYPE BIGINT USING message_id::BIGINT,
    ALTER COLUMN conversation_id TYPE BIGINT USING conversation_id::BIGINT,
    ALTER COLUMN run_id TYPE BIGINT USING run_id::BIGINT;

ALTER TABLE task_results
    ADD COLUMN IF NOT EXISTS input_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    ALTER COLUMN task_result_id TYPE BIGINT USING task_result_id::BIGINT,
    ALTER COLUMN agent_id TYPE BIGINT USING agent_id::BIGINT,
    ALTER COLUMN user_id TYPE BIGINT USING user_id::BIGINT,
    ALTER COLUMN conversation_id TYPE BIGINT USING conversation_id::BIGINT,
    ALTER COLUMN run_id TYPE BIGINT USING run_id::BIGINT,
    ALTER COLUMN message_id TYPE BIGINT USING message_id::BIGINT;

ALTER TABLE task_results
    DROP COLUMN IF EXISTS image_url,
    DROP COLUMN IF EXISTS image_data,
    DROP COLUMN IF EXISTS mime_type,
    DROP COLUMN IF EXISTS width,
    DROP COLUMN IF EXISTS height,
    DROP COLUMN IF EXISTS provider_request_id,
    DROP COLUMN IF EXISTS error_code,
    DROP COLUMN IF EXISTS error_message;

DROP TABLE IF EXISTS message_attachments;

ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_owner
    FOREIGN KEY (owner_id) REFERENCES user_identities(user_id);
ALTER TABLE agent_runs
    ADD CONSTRAINT fk_agent_runs_conversation
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE;
ALTER TABLE messages
    ADD CONSTRAINT fk_messages_conversation
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_messages_run
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE SET NULL;
ALTER TABLE task_results
    ADD CONSTRAINT fk_task_results_user
    FOREIGN KEY (user_id) REFERENCES user_identities(user_id),
    ADD CONSTRAINT fk_task_results_conversation
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_task_results_run
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_task_results_message
    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE SET NULL;

COMMENT ON TABLE user_identities IS '可信外部主体与内部雪花用户 ID 的映射';
COMMENT ON TABLE task_results IS '所有智能体共享的任务结果及 OSS 对象元数据';
COMMENT ON COLUMN task_results.input_data IS '任务输入、参数和参考图 OSS 对象元数据';
COMMENT ON COLUMN task_results.result_data IS '生成结果 OSS 对象元数据及智能体扩展数据';

COMMIT;
