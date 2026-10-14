-- 多智能体任务结果与图片附件；可在已有 001 schema 上重复执行。
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'default';

CREATE TABLE IF NOT EXISTS task_results (
    task_result_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    message_id TEXT REFERENCES messages(message_id) ON DELETE SET NULL,
    result_type TEXT NOT NULL,
    generation_status TEXT NOT NULL CHECK (
        generation_status IN (
            'pending', 'awaiting_input', 'running',
            'succeeded', 'failed', 'cancelled'
        )
    ),
    result_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    image_url TEXT,
    image_data BYTEA,
    mime_type TEXT,
    width INTEGER,
    height INTEGER,
    provider_request_id TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_results_user_created
    ON task_results (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_results_conversation_created
    ON task_results (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_results_run
    ON task_results (run_id);
CREATE INDEX IF NOT EXISTS idx_task_results_agent_created
    ON task_results (agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_results_message
    ON task_results (message_id);

CREATE TABLE IF NOT EXISTS message_attachments (
    attachment_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    message_id TEXT REFERENCES messages(message_id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size BIGINT NOT NULL CHECK (file_size > 0),
    image_data BYTEA NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('staged', 'attached')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
);

CREATE INDEX IF NOT EXISTS idx_message_attachments_user_status
    ON message_attachments (user_id, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_message_attachments_message
    ON message_attachments (message_id);

COMMENT ON TABLE task_results IS '所有智能体共享的业务结果及生成图片';
COMMENT ON TABLE message_attachments IS '聊天消息上传的参考图片附件';
