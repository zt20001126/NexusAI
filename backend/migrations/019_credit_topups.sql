BEGIN;

ALTER TABLE credit_entries
    DROP CONSTRAINT IF EXISTS ck_credit_entries_kind_delta;
ALTER TABLE credit_entries
    ADD CONSTRAINT ck_credit_entries_kind_delta CHECK (
        (kind = 'registration_grant' AND delta = 100) OR
        (kind = 'message_debit' AND delta = -1) OR
        (kind = 'run_refund' AND delta = 1) OR
        (kind = 'top_up' AND delta > 0)
    );

CREATE TABLE IF NOT EXISTS credit_topups (
    top_up_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency ~ '^[a-z]{3}$'),
    amount BIGINT NOT NULL CHECK (amount > 0),
    stripe_amount BIGINT NOT NULL CHECK (stripe_amount > 0),
    stripe_session_id TEXT NULL,
    checkout_url TEXT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'failed', 'expired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_credit_topups_user_request UNIQUE (user_id, request_id),
    CONSTRAINT uq_credit_topups_stripe_session UNIQUE (stripe_session_id)
);
COMMENT ON TABLE credit_topups IS 'Stripe 积分充值尝试';
COMMENT ON COLUMN credit_topups.amount IS '充值金额主单位，同时为到账积分数';
COMMENT ON COLUMN credit_topups.stripe_amount IS '按 Stripe 币种最小单位表示的收款金额';
CREATE INDEX IF NOT EXISTS idx_credit_topups_user_created
    ON credit_topups (user_id, created_at);

COMMIT;
