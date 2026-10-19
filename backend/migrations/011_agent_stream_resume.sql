-- 允许运行先以 queued 状态入库，并以 request_id 防止 HTTP 重试创建重复运行。
BEGIN;

ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS ck_agent_runs_status;
ALTER TABLE agent_runs
    ADD CONSTRAINT ck_agent_runs_status
    CHECK (status IN ('queued', 'running', 'waiting', 'completed', 'cancelled', 'failed'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_request_id
    ON agent_runs ((metadata->>'request_key'))
    WHERE metadata ? 'request_key';

COMMENT ON INDEX uq_agent_runs_request_id IS '防止同一聊天提交请求创建重复运行';

COMMIT;
