-- 用户积分余额与积分明细；现有账号统一从 0 分开始，不发放注册赠分。
BEGIN;

CREATE TABLE IF NOT EXISTS user_credits (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    balance BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE user_credits IS '用户积分余额';
COMMENT ON COLUMN user_credits.user_id IS '积分所有者的内部用户 ID';
COMMENT ON COLUMN user_credits.balance IS '当前可用积分余额';
COMMENT ON COLUMN user_credits.version IS '余额单调递增版本，用于 Redis 更新排序';
COMMENT ON COLUMN user_credits.updated_at IS '余额最近变更时间';

INSERT INTO user_credits (user_id, balance, version)
SELECT user_id, 0, 0 FROM users
ON CONFLICT (user_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS credit_entries (
    event_key TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    run_id BIGINT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('registration_grant', 'message_debit', 'run_refund')),
    delta BIGINT NOT NULL,
    balance_after BIGINT NOT NULL CHECK (balance_after >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_credit_entries_kind_delta CHECK (
        (kind = 'registration_grant' AND delta = 100) OR
        (kind = 'message_debit' AND delta = -1) OR
        (kind = 'run_refund' AND delta = 1)
    )
);
COMMENT ON TABLE credit_entries IS '用户积分变更不可变明细';
COMMENT ON COLUMN credit_entries.event_key IS '业务事件幂等键';
COMMENT ON COLUMN credit_entries.user_id IS '积分所有者的内部用户 ID';
COMMENT ON COLUMN credit_entries.run_id IS '触发扣费或退款的运行雪花 ID';
COMMENT ON COLUMN credit_entries.kind IS '积分变更类型';
COMMENT ON COLUMN credit_entries.delta IS '积分变更数量';
COMMENT ON COLUMN credit_entries.balance_after IS '本次变更后的积分余额';
COMMENT ON COLUMN credit_entries.created_at IS '明细创建时间';

CREATE INDEX IF NOT EXISTS idx_credit_entries_user_created
    ON credit_entries (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_credit_entries_run_kind
    ON credit_entries (run_id, kind);

COMMIT;
