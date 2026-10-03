-- 将旧的 Agent 元数据表迁移到会话、消息和运行三表结构。
-- LangGraph Checkpointer 自有表不会被此迁移修改。
BEGIN;

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF to_regclass('public.agent_conversations') IS NOT NULL THEN
        IF EXISTS (
            SELECT 1
            FROM agent_conversations AS old_conversations
            LEFT JOIN agent_runs AS runs
              ON runs.conversation_id = old_conversations.conversation_id
            WHERE COALESCE(
                NULLIF(old_conversations.metadata->>'principal_id', ''),
                NULLIF(runs.principal_id, '')
            ) IS NULL
        ) THEN
            RAISE EXCEPTION 'Cannot migrate a conversation without an owner';
        END IF;

        INSERT INTO conversations (
            conversation_id, owner_id, created_at, updated_at
        )
        SELECT old_conversations.conversation_id,
               COALESCE(
                   NULLIF(old_conversations.metadata->>'principal_id', ''),
                   MIN(runs.principal_id)
               ),
               old_conversations.updated_at,
               old_conversations.updated_at
        FROM agent_conversations AS old_conversations
        LEFT JOIN agent_runs AS runs
          ON runs.conversation_id = old_conversations.conversation_id
        GROUP BY old_conversations.conversation_id,
                 old_conversations.metadata,
                 old_conversations.updated_at
        ON CONFLICT (conversation_id) DO NOTHING;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'agent_runs'
          AND column_name = 'principal_id'
    ) THEN
        IF EXISTS (
            SELECT 1
            FROM agent_runs AS runs
            WHERE runs.principal_id IS NULL OR runs.principal_id = ''
        ) THEN
            RAISE EXCEPTION 'Cannot migrate a run without an owner';
        END IF;

        INSERT INTO conversations (
            conversation_id, owner_id
        )
        SELECT DISTINCT ON (runs.conversation_id)
               runs.conversation_id, runs.principal_id
        FROM agent_runs AS runs
        WHERE NOT EXISTS (
            SELECT 1 FROM conversations
            WHERE conversations.conversation_id = runs.conversation_id
        )
        ORDER BY runs.conversation_id, runs.run_id;

        IF EXISTS (
            SELECT 1
            FROM agent_runs AS runs
            JOIN conversations
              ON conversations.conversation_id = runs.conversation_id
            WHERE conversations.owner_id <> runs.principal_id
        ) THEN
            RAISE EXCEPTION 'Conversation and run owners do not match';
        END IF;

        ALTER TABLE agent_runs DROP COLUMN principal_id;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_agent_runs_conversation'
          AND conrelid = 'agent_runs'::regclass
    ) THEN
        ALTER TABLE agent_runs
            ADD CONSTRAINT fk_agent_runs_conversation
            FOREIGN KEY (conversation_id)
            REFERENCES conversations(conversation_id)
            ON DELETE CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES agent_runs(run_id) ON DELETE SET NULL,
    sequence BIGINT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conversation_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated
    ON conversations (owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence
    ON messages (conversation_id, sequence);

COMMENT ON TABLE conversations IS '智能体对话会话';
COMMENT ON TABLE messages IS '会话中的用户消息和助手回复';
COMMENT ON TABLE agent_runs IS '智能体运行状态与恢复信息';

DROP TABLE IF EXISTS agent_events;
DROP TABLE IF EXISTS agent_event_sequences;
DROP TABLE IF EXISTS agent_conversations;

COMMIT;
