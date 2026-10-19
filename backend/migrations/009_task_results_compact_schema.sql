-- 任务结果表精简结构；本迁移会删除旧 task_results 中的全部数据。
BEGIN;

DROP TABLE task_results;

CREATE TABLE task_results (
    id BIGINT PRIMARY KEY,
    conversation_id BIGINT NOT NULL
        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    message_id BIGINT
        REFERENCES messages(message_id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'awaiting_input', 'running',
            'succeeded', 'failed', 'cancelled'
        )
    ),
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_results_conversation_created
    ON task_results (conversation_id, created_at);
CREATE INDEX idx_task_results_message
    ON task_results (message_id);

COMMENT ON TABLE task_results IS '所有智能体共享的任务结果及 OSS 对象元数据';
COMMENT ON COLUMN task_results.id IS '任务结果雪花 ID';
COMMENT ON COLUMN task_results.conversation_id IS '任务所属会话 ID';
COMMENT ON COLUMN task_results.message_id IS '任务结果关联的助手消息 ID';
COMMENT ON COLUMN task_results.status IS '任务生命周期状态';
COMMENT ON COLUMN task_results.input IS '任务输入、参数和参考图 OSS 对象元数据';
COMMENT ON COLUMN task_results.result IS '生成结果 OSS 对象元数据及智能体扩展数据';
COMMENT ON COLUMN task_results.created_at IS '任务结果创建时间';

COMMIT;
